"""DATA-018 GERS capture path against a fake in-memory S3 (needs pinned pyarrow).

Ordinary CI has no Arrow, so this is skipped there. It exists so the one-shot
real run is not the first time the Arrow glue executes.
"""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest
import urllib.parse
import uuid

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    ARROW = pa.__version__ == '21.0.0'
except ImportError:  # pragma: no cover - ordinary offline CI
    ARROW = False

from benchmarks.third_release_rehearsal import RELEASE, stac_pair

S3 = 'https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/'


def _parquet(rows_by_group):
    schema = pa.schema([
        ('id', pa.string()),
        ('bbox', pa.struct([('xmin', pa.float32()), ('xmax', pa.float32()),
                            ('ymin', pa.float32()), ('ymax', pa.float32())])),
        ('columns_changed', pa.list_(pa.string())),
    ])
    sink = BytesIO()
    with pq.ParquetWriter(sink, schema, write_statistics=True) as writer:
        for rows in rows_by_group:
            writer.write_table(pa.Table.from_pylist(rows, schema=schema))
    return sink.getvalue()


def _rows(prefix, n, x, y):
    return [{'id': str(uuid.uuid5(uuid.NAMESPACE_URL, f'{prefix}/{i}')),
             'bbox': {'xmin': x, 'xmax': x, 'ymin': y, 'ymax': y}, 'columns_changed': None}
            for i in range(n)]


class FakeResponse:
    def __init__(self, url, body, status=200, headers=None):
        self._url, self.body, self.status = url, body, status
        self.headers = {'Content-Length': str(len(body)), **(headers or {})}

    def geturl(self):
        return self._url

    def read(self, n=-1):
        return self.body if n is None or n < 0 else self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@unittest.skipUnless(ARROW, 'pinned pyarrow==21.0.0 not installed')
class FakeS3Capture(unittest.TestCase):
    def setUp(self):
        self.root, self.cat = stac_pair()
        # Karakoy cell centre inside; second group far away and must not be read.
        self.objects = {}
        for kind in ('added', 'removed'):
            key = f'changelog/{RELEASE}/theme=places/type=place/change_type={kind}/part-00000-x.parquet'
            self.objects[key] = _parquet([_rows(kind + 'in', 5, 28.975, 41.024),
                                          _rows(kind + 'out', 7, 10.0, 50.0)])
        self.requests = []

    def fake_open(self, opener, request, *args, **kwargs):
        url = request.full_url
        self.requests.append(url)
        if url == 'https://stac.overturemaps.org/catalog.json':
            return FakeResponse(url, self.root)
        if url == f'https://stac.overturemaps.org/{RELEASE}/catalog.json':
            return FakeResponse(url, self.cat)
        if url.startswith(S3 + '?'):
            prefix = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['prefix'][0]
            contents = ''.join(f'<Contents><Key>{k}</Key><ETag>"etag"</ETag><Size>{len(v)}</Size>'
                               f'<LastModified>2026-10-21T00:00:00Z</LastModified></Contents>'
                               for k, v in self.objects.items() if k.startswith(prefix))
            xml = ('<?xml version="1.0" encoding="UTF-8"?><ListBucketResult '
                   'xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                   f'<Prefix>{prefix}</Prefix><IsTruncated>false</IsTruncated>{contents}</ListBucketResult>')
            return FakeResponse(url, xml.encode())
        key = url[len(S3):]
        body = self.objects[key]
        start, end = map(int, request.get_header('Range')[len('bytes='):].split('-'))
        chunk = body[start:end + 1]
        return FakeResponse(url, chunk, 206, {'Content-Range': f'bytes {start}-{end}/{len(body)}',
                                              'ETag': '"etag"'})

    def test_bounded_capture_then_offline_compare_inputs(self):
        from scripts.capture_third_release import run_gers
        with TemporaryDirectory() as t, patch('urllib.request.OpenerDirector.open',
                                              autospec=True, side_effect=self.fake_open):
            out = Path(t) / 'gers'
            receipt = run_gers(RELEASE, out)
            events = json.loads((out / 'gers_regional_events.json').read_bytes())
        self.assertEqual(receipt['status'], 'REGIONAL_ROWS_CAPTURED_NOT_COMPLETE_ID_UNION', receipt)
        self.assertEqual(receipt['plan']['selected_row_groups'], 2)
        self.assertEqual(receipt['plan']['excluded_row_groups'], 2)
        self.assertEqual(receipt['scanned_rows'], 10)
        self.assertEqual(len(events), 10)
        self.assertEqual({e['change_type'] for e in events}, {'added', 'removed'})
        self.assertLessEqual(receipt['event_body_bytes'], 16 * 1024 * 1024)
        self.assertEqual(receipt['chain']['status'], 'CONSECUTIVE_PAIR')
        from kepcore.overture_third_release import PROTOCOL_SHA256
        self.assertEqual(receipt['protocol_sha256'], PROTOCOL_SHA256)

    def test_nan_bbox_in_a_selected_group_makes_the_capture_incomplete(self):
        from scripts.capture_third_release import run_gers
        key = f'changelog/{RELEASE}/theme=places/type=place/change_type=added/part-00000-x.parquet'
        bad = _rows('nan', 1, 28.975, 41.024)
        bad[0]['bbox']['xmin'] = float('nan')
        self.objects[key] = _parquet([_rows('addedin', 5, 28.975, 41.024) + bad,
                                      _rows('addedout', 7, 10.0, 50.0)])
        with TemporaryDirectory() as t, patch('urllib.request.OpenerDirector.open',
                                              autospec=True, side_effect=self.fake_open):
            receipt = run_gers(RELEASE, Path(t) / 'gers')
        self.assertEqual(receipt['status'], 'INCOMPLETE_EVENT_CAPTURE')
        self.assertEqual(receipt['failure_type'], 'ValueError')
        self.assertIn('bbox', receipt['failure_detail'])

    def test_wrong_stac_latest_stops_before_any_s3_read(self):
        from scripts.capture_third_release import run_gers
        self.root, _ = stac_pair(release='2026-10-28.0')
        with TemporaryDirectory() as t, patch('urllib.request.OpenerDirector.open',
                                              autospec=True, side_effect=self.fake_open):
            with self.assertRaises(ValueError):
                run_gers(RELEASE, Path(t) / 'gers')
        self.assertFalse(any(u.startswith(S3) for u in self.requests))


if __name__ == '__main__':
    unittest.main()
