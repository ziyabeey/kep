"""Read-only historical Overture S3 existence probe, not a data download.

A listed/headable Parquet object proves only that ONE exact old-release object
is publicly reachable at probe time. It does not prove all objects or a whole
Istanbul regional query will be available, nor that any POI exists in reality.
Never accepts host/release/prefix from models or users.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import quote, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from xml.etree import ElementTree as ET
import re

BUCKET = 'overturemaps-us-west-2'
REGION = 'us-west-2'
S3_BASE = f'https://{BUCKET}.s3.{REGION}.amazonaws.com'
PINNED_PREFIX = 'release/2026-08-19.0/theme=places/type=place/'
MAX_LIST_BYTES = 24_000
MAX_KEY_LEN = 380


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def list_url() -> str:
    return S3_BASE + '/?' + urlencode((('list-type', '2'), ('prefix', PINNED_PREFIX), ('max-keys', '1')))


def _tag(e: ET.Element, local: str):
    for child in e:
        if child.tag.rsplit('}', 1)[-1] == local:
            return child.text
    return None


def _children(e: ET.Element, local: str):
    return [node for node in e if node.tag.rsplit('}', 1)[-1] == local]


def parse_public_listing(body: bytes) -> dict:
    """Parse ListObjectsV2 and reject wrong prefix, truncation and fake keys."""
    if not isinstance(body, bytes) or not 0 < len(body) <= MAX_LIST_BYTES:
        raise ValueError('Missing or oversized S3 prefix listing')
    if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
        raise ValueError('XML entities are forbidden in S3 metadata')
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError('Invalid S3 listing XML') from exc
    if root.tag.rsplit('}', 1)[-1] != 'ListBucketResult':
        raise ValueError('Expected S3 ListBucketResult')
    if _tag(root, 'Name') != BUCKET or _tag(root, 'Prefix') != PINNED_PREFIX:
        raise ValueError('Unexpected bucket or historical release prefix')
    if _tag(root, 'KeyCount') != '1' or _tag(root, 'MaxKeys') != '1':
        raise ValueError('Expected exactly one bounded historical S3 listing')
    entries = _children(root, 'Contents')
    if len(entries) != 1:
        raise ValueError('No Parquet object listed for this historical release')
    entry = entries[0]
    key = _tag(entry, 'Key')
    if not isinstance(key, str) or not key.startswith(PINNED_PREFIX) or len(key) > MAX_KEY_LEN:
        raise ValueError('Listed object outside the exact historical release')
    filename = key[len(PINNED_PREFIX):]
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.parquet', filename):
        raise ValueError('Unexpected Parquet object name')
    try:
        size = int(_tag(entry, 'Size'))
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid historical S3 object length') from exc
    if size <= 0:
        raise ValueError('Historical S3 object is empty')
    etag = _tag(entry, 'ETag')
    if not isinstance(etag, str) or not re.fullmatch(r'"[0-9a-fA-F]{32}(?:-\d+)?"', etag):
        raise ValueError('Invalid S3 object ETag')
    when = _tag(entry, 'LastModified')
    if not isinstance(when, str):
        raise ValueError('Missing S3 last-modified metadata')
    try:
        parsed = datetime.fromisoformat(when.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('Invalid S3 last-modified time') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.date().isoformat() < '2026-08-19':
        raise ValueError('Unexpected S3 object timestamp')
    return {'key': key, 'size_bytes': size, 'etag': etag,
            'last_modified': when, 'listing_sha256': sha256(body).hexdigest()}


def _get_bounded(url: str, *, method: str, max_bytes: int) -> tuple[int, dict, bytes]:
    if method not in {'GET', 'HEAD'}:
        raise ValueError('Unexpected HTTP method')
    req = Request(url, headers={'User-Agent': 'KEP-Historical-Release-Preflight/1.0'}, method=method)
    with build_opener(_NoRedirect).open(req, timeout=15) as response:
        if response.geturl() != url or response.status != 200:
            raise ValueError('Unexpected public S3 response or redirect')
        body = response.read(max_bytes + 1) if method == 'GET' else b''
        if len(body) > max_bytes:
            raise ValueError('Historical listing exceeded size cap')
        return response.status, {k.lower(): v for k,v in response.headers.items()}, body


def confirm_public_parquet_object(*, request_fn=None, checked_at: str | None = None) -> dict:
    """Run bounded GET ListObjectsV2 then HEAD one object, with mockable transport."""
    request_fn = request_fn or _get_bounded
    status,_,body = request_fn(list_url(), method='GET', max_bytes=MAX_LIST_BYTES)
    if status != 200:
        raise ValueError('Historical S3 listing unavailable')
    listed = parse_public_listing(body)
    object_url = S3_BASE + '/' + quote(listed['key'], safe='/=-_.')
    status,headers,_ = request_fn(object_url, method='HEAD', max_bytes=0)
    if status != 200:
        raise ValueError('Historical S3 object HEAD request failed')
    try:
        size = int(headers.get('content-length', ''))
    except ValueError as exc:
        raise ValueError('Object HEAD has no valid byte length') from exc
    if size != listed['size_bytes']:
        raise ValueError('S3 listing and HEAD lengths differ')
    if headers.get('etag') != listed['etag']:
        raise ValueError('S3 listing and HEAD ETags differ')
    at = checked_at or datetime.now(timezone.utc).isoformat()
    when = datetime.fromisoformat(at.replace('Z', '+00:00'))
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError('Preflight timestamp must include timezone')
    return {
        'study': 'KEP-DATA-008',
        'exact_release': '2026-08-19.0',
        'checked_at': at,
        'object_key': listed['key'],
        'object_size_bytes': size,
        's3_etag_not_content_sha256': listed['etag'],
        'listing_sha256': listed['listing_sha256'],
        'public_prefix_listed': True,
        'one_parquet_head_verified': True,
        'all_release_parts_verified': False,
        'regional_istanbul_download_completed': False,
        'consumer_publish_approved': False,
        's3_prefix': PINNED_PREFIX,
    }
