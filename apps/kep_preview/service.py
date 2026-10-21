"""Local preview facade over KEP Core; no source fetches or model calls.

The text box is a deliberately bounded Turkish filter parser, not an LLM.
Unknown words and ambiguous constraints stop a query instead of weakening it.
Only the existing seven-landmark excerpt is exposed through this preview;
the research Overture archives and pending source registry are not loaded.
"""
from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path
import re
import sys
from typing import Any

_LAB_ROOT = Path(__file__).resolve().parents[2] / "labs" / "core"
if str(_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_LAB_ROOT))

from kepcore.core import IST, Query, decide, fold, load_catalog  # noqa: E402
from kepcore.model_boundary import context_for_model  # noqa: E402


CENTER = {"lat": 41.02563232, "lon": 28.97415319}
_CATEGORIES = (
    {"id": "discover", "label": "Keşif", "color": "#16b9a6"},
    {"id": "food", "label": "Yemek", "color": "#ed9857"},
    {"id": "events", "label": "Etkinlik", "color": "#a282ed"},
    {"id": "services", "label": "Hizmet", "color": "#8c96a6"},
)
_CATEGORY_IDS = {item["id"] for item in _CATEGORIES}
_PLACE_CATEGORIES = {
    "discover": {"museum", "heritage", "park"},
    "food": {"food", "restaurant", "cafe"},
    "services": {"service", "salon"},
}
_PLACE_CATEGORY_PARENTS = {"museum": "discover", "restaurant": "food", "cafe": "food"}
_MODES = {"work", "roam", "balanced", "silent"}
_FILTER_FIELDS = {"category", "place_category", "radius_km", "open_now", "quiet", "budget", "mode", "at"}
_META = {
    "research_only": True,
    "model_used": False,
    "traffic_live": False,
    "source_fetches": 0,
    "consumer_publish": False,
}
_NOTICE = (
    "7 İstanbul mekânından oluşan araştırma kataloğu. Konumlar yaklaşık; "
    "güncel fiyat, açık olma durumu ve kalabalık doğrulanmadı."
)


def _now_iso() -> str:
    return datetime.now(IST).replace(microsecond=0).isoformat()


def _object(value: Any, fields: set[str], name: str) -> dict:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValueError(f"{name} bir JSON nesnesi olmalı.")
    unknown = set(value) - fields
    if unknown:
        raise ValueError(f"{name} desteklenmeyen alan içeriyor: {', '.join(sorted(unknown))}.")
    return value


def _number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} sayı olmalı.")
    # Compare integers before conversion; a JSON integer can exceed float range.
    if not low <= value <= high or not math.isfinite(value):
        raise ValueError(f"{name} {low:g} ile {high:g} arasında olmalı.")
    return float(value)


def _filters(payload: Any) -> dict:
    payload = _object(payload, _FILTER_FIELDS, "Filtreler")
    out = {
        "category": "discover", "place_category": None, "radius_km": 1.0, "open_now": False,
        "quiet": False, "budget": None, "mode": "balanced", "at": _now_iso(),
    }
    out.update(payload)
    if not isinstance(out["category"], str) or out["category"] not in _CATEGORY_IDS:
        raise ValueError("Kategori keşif, yemek, etkinlik veya hizmet olmalı.")
    subtype = out["place_category"]
    if subtype is not None and (
        not isinstance(subtype, str) or _PLACE_CATEGORY_PARENTS.get(subtype) != out["category"]
    ):
        raise ValueError("Yer türü kategoriyle uyumlu museum, restaurant, cafe veya null olmalı.")
    if not isinstance(out["mode"], str) or out["mode"] not in _MODES:
        raise ValueError("Kullanıcı modu geçersiz.")
    for name in ("open_now", "quiet"):
        if type(out[name]) is not bool:
            raise ValueError(f"{name} true veya false olmalı.")
    out["radius_km"] = _number(out["radius_km"], "Yarıçap", 0.1, 20)
    if out["budget"] is not None:
        out["budget"] = _number(out["budget"], "Bütçe", 0, 1_000_000)
    at = out["at"]
    if not isinstance(at, str) or len(at) > 64 or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?", at
    ):
        raise ValueError("Zaman YYYY-MM-DDTHH:MM biçiminde olmalı; saat dilimi yoksa İstanbul kullanılır.")
    try:
        parsed = datetime.fromisoformat(at.replace("Z", "+00:00"))
        parsed = parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Sorgu zamanı geçersiz.") from exc
    out["at"] = parsed.isoformat()
    return out


def _catalog_for(category: str, records: list[dict]) -> list[dict]:
    if category == "events":
        return [r for r in records if r.get("kind") == "event"]
    accepted = _PLACE_CATEGORIES[category]
    return [r for r in records if r.get("kind") == "place" and r.get("category") in accepted]


def _reply(action: str, selected: list[dict], reasons: list[str], category: str) -> str:
    if selected:
        return (
            f"Galata çevresinde koşullarına uyan {len(selected)} konum kaydı buldum. "
            "Mesafeler kuş uçuşu; güncel açık olma durumu ve fiyatlar teyit edilmedi."
        )
    labels = []
    if any("PRICE" in r or r == "CURRENCY_CONVERSION_REQUIRED" for r in reasons):
        labels.append("fiyat")
    if any("OPENING" in r or r == "SOURCE_FRESHNESS_UNVERIFIED" for r in reasons):
        labels.append("çalışma saatleri ve güncellik")
    if any("CROWD" in r for r in reasons):
        labels.append("kalabalık")
    if action in {"REFRESH", "CLARIFY"}:
        fields = ", ".join(labels) or "istenen koşullar"
        return f"{fields.capitalize()} için gerekli kanıt eksik. Bu koşulları karşılayan bir yer öneremiyorum."
    category_label = next(c["label"] for c in _CATEGORIES if c["id"] == category)
    return (
        f"{category_label} kategorisinde bu koşullara uyan araştırma kaydı yok. "
        "Bu, çevrede gerçek seçenek bulunmadığı anlamına gelmez."
    )


def _discover(filters: dict) -> dict:
    catalog = _catalog_for(filters["category"], load_catalog())
    query = Query(
        city="İstanbul", kind="event" if filters["category"] == "events" else "place",
        category=filters["place_category"], at=filters["at"], budget=filters["budget"],
        lat=CENTER["lat"], lon=CENTER["lon"], radius_km=filters["radius_km"],
        open_now=filters["open_now"], quiet=filters["quiet"], mode=filters["mode"], limit=7,
    )
    decision = decide(catalog, query)
    context = context_for_model(decision)
    result = decision.to_dict()
    # Never serialize rejected records/IDs or widen Core's selected set.
    result["blocked_count"] = len(result.pop("blocked"))
    by_id = {r["id"]: r for r in catalog}
    for row in result["selected"]:
        original = by_id[row["id"]]
        row.update(
            lat=original.get("lat"), lon=original.get("lon"), category=original.get("category"),
            source_observed_at=original.get("source_observed_at"),
            acquired_date=original.get("acquired_date"), license=original.get("license"),
            source_label={"wikidata": "Wikidata", "wikipedia": "Wikipedia"}.get(
                original.get("source_id"), original.get("source_id", "Kaynak")
            ),
            live_verified=False,
            source_note="Topluluk kaynaklı yaklaşık konum; güncel giriş noktası doğrulanmadı.",
        )
    return {
        "query": dict(filters), "decision": result,
        "reply": _reply(result["action"], result["selected"], result["reasons"], filters["category"]),
        "clarifications": [],
        "meta": dict(_META, snapshot_hash=context["snapshot_hash"]),
    }


def discover(payload: Any) -> dict:
    """Run an explicitly structured, validated discovery query through Core."""
    return _discover(_filters(payload))


def bootstrap() -> dict:
    initial = discover({})
    catalog = load_catalog()
    categories = []
    for item in _CATEGORIES:
        subset = _catalog_for(item["id"], catalog)
        decision = decide(subset, Query(city="İstanbul", at=initial["query"]["at"], limit=50))
        categories.append(dict(item, count=len(decision.selected)))
    return {
        "meta": dict(
            _META, label="Araştırma önizlemesi", notice=_NOTICE,
            at=initial["query"]["at"], location_label="Galata, İstanbul", center=dict(CENTER),
            reference="10 Ekim 2026 tarihli kaynak alıntıları · Wikimedia katkıda bulunanlar",
            catalog_count=7,
        ),
        "categories": categories, "initial": initial,
    }


def _clarify(filters: dict, message: str, unsupported: list[str], *, route: str | None = None) -> dict:
    interpretation = {"applied_constraints": [], "unsupported_constraints": unsupported}
    if route:
        interpretation["route_to"] = route
    return {
        "query": dict(filters), "decision": None, "reply": message,
        "clarifications": [message], "interpretation": interpretation, "meta": dict(_META),
    }


def chat(payload: Any) -> dict:
    """Translate a small documented phrase vocabulary; abstain on everything else.

    No token is discarded merely because it is inconvenient for discovery. A
    cuisine, unknown location, time, comparison or negation therefore produces
    clarification rather than an apparently successful but weakened query.
    """
    payload = _object(payload, {"message", "filters"}, "İstek")
    raw = payload.get("message")
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 1000:
        raise ValueError("Mesaj 1 ile 1000 karakter arasında olmalı.")
    inherited = _filters(payload.get("filters", {}))
    filters = dict(inherited)
    text = fold(raw.strip()).replace("’", "'").replace("‘", "'")
    if re.search(r"\b(?:plan(?:la|im|imi|lamak)?|gunumu|maslak|levent|zorlu|toplanti|trafik)\b", text):
        return _clarify(
            inherited,
            "Çok duraklı plan ve yol süresi için Günüm bölümünü kullan. Bu keşif kutusu Galata çevresindeki yerleri filtreler.",
            ["gün planı veya başka konum"], route="plan",
        )
    if re.search(r"\b(?:yakinimda|konumum|bulundugum)\b", text):
        return _clarify(
            inherited, "Konumunu almadım. Bu önizleme Galata merkezli; 'Galata çevresinde yer bul' diyebilirsin.",
            ["kullanıcının konumu"],
        )
    applied: list[str] = []
    browse_request = bool(re.search(r"\b(?:bul|goster|oner|yer(?:ler|leri)?|mekan(?:lar|lari)?|kesif|muze(?:ler|leri)?)\b", text))

    def consume(pattern: str, label: str | None = None) -> list[re.Match]:
        nonlocal text
        matches = list(re.finditer(pattern, text))
        if matches:
            text = re.sub(pattern, " ", text)
            if label:
                applied.append(label)
        return matches

    # Numeric formats are deliberately narrow: 1.000 TL is not guessed as 1 or 1000.
    number = r"(?<![\w.,])([0-9]+(?:[.,][0-9]{1,2})?)(?![\d.,])"
    # An upper-bound phrase belongs to its supported numeric unit. Removing
    # it as filler would silently drop a result-count constraint such as
    # 'en fazla bir müze'.
    upper_bound = r"(?:\ben\s+fazla\s+)?"
    radii = consume(upper_bound + number + r"\s*(?:km|kilometre)\b", "Yarıçap")
    budgets = consume(upper_bound + number + r"\s*(?:tl\b|lira\b|₺)", "Bütçe")
    for matches, field in ((radii, "radius_km"), (budgets, "budget")):
        values = {float(m.group(1).replace(",", ".")) for m in matches}
        if len(values) > 1:
            return _clarify(inherited, "Birden fazla farklı sınır gördüm. Tek bir km ve tek bir TL sınırı yaz.", [field])
        if values:
            filters[field] = values.pop()

    category_hits: set[str] = set()
    for category, pattern in (
        ("discover", r"\b(?:kesif|gezilecek)\b"),
        ("food", r"\byemek\b"),
        ("events", r"\b(?:etkinlik(?:ler|leri)?)\b"),
        ("services", r"\b(?:hizmet(?:ler|leri)?)\b"),
    ):
        if consume(pattern):
            category_hits.add(category)
    subtypes = []
    for subtype, category, label, pattern in (
        ("museum", "discover", "Müze", r"\bmuze(?:ler|leri)?\b"),
        ("restaurant", "food", "Restoran", r"\brestoran(?:lar|lari)?\b"),
        ("cafe", "food", "Kafe", r"\bkafe(?:ler|leri)?\b"),
    ):
        if consume(pattern):
            category_hits.add(category)
            subtypes.append(subtype)
            applied.append(label)
    if len(subtypes) > 1:
        return _clarify(inherited, "Tek bir yer türü seçebilir misin? Örneğin yalnız müze veya yalnız kafe.", ["birden fazla yer türü"])
    if len(category_hits) > 1:
        return _clarify(inherited, "Bu önizlemede bir seferde tek kategori seçebilirim. Keşif, yemek, etkinlik veya hizmetten birini yaz.", ["birden fazla kategori"])
    if category_hits:
        filters["category"] = next(iter(category_hits))
        # An explicit broad category resets the subtype; radius/filter-only
        # follow-ups inherit it through the same public query contract.
        filters["place_category"] = subtypes[0] if subtypes else None
        applied.append(next(c["label"] for c in _CATEGORIES if c["id"] == filters["category"]))

    for mode, pattern in (
        ("work", r"\bis mod(?:u|unda|una)\b"),
        ("roam", r"\bgezinti mod(?:u|unda|una)\b"),
        ("balanced", r"\bdengeli mod(?:u|unda|una)\b"),
        ("silent", r"\bsessiz mod(?:u|unda|una)\b"),
    ):
        if consume(pattern):
            if any(x.startswith("Mod:") for x in applied):
                return _clarify(inherited, "Tek bir kullanıcı modu seçebilir misin?", ["birden fazla mod"])
            filters["mode"] = mode
            applied.append("Mod: " + mode)

    if consume(r"\b(?:sakin|az kalabalik|kalabalik olmasin)\b", "Sakinlik"):
        filters["quiet"] = True
    if consume(r"\b(?:(?:simdi|su an)\s+)?acik\b", "Açık olma"):
        filters["open_now"] = True
        if re.search(r"\b(?:simdi|su an)\b", fold(raw)):
            filters["at"] = _now_iso()
    consume(r"\bgalata(?:'?(?:da|de|nin|ya|yi))?\b", "Galata merkezi")
    # Keep the ordinary indefinite phrase in 'sakin bir yer bul'; do not
    # erase standalone number words or negation tokens such as 'ne ... ne'.
    consume(r"\bbir\s+(?=(?:yer|mekan)\b)")
    # These words carry no additional supported constraint; all remaining text
    # must be empty, so e.g. 'ucuz', 'vegan', 'yarın', 'hariç' cannot disappear.
    consume(
        r"\b(?:hey|kep|merhaba|lutfen|kanka|bana|benim|yer|yerler|yerleri|mekan|mekanlar|mekanlari|"
        r"goster|bul|oner|ariyorum|istiyorum|olsun|ve|ile|icinde|cevresinde|yakininda|yakindaki|"
        r"etraf(?:inda|indaki)|icin|olan|olarak|misin|musun|var|neler|altinda|"
        r"butce|butcem|butceyle|butcemle|yaricapinda)\b"
    )
    remainder = re.sub(r"[\s,;.!?]+", " ", text).strip()
    if remainder:
        return _clarify(
            inherited,
            "İsteğinin tamamını desteklediğim filtrelere çeviremedim. Galata çevresi, kategori, km, TL, şimdi açık ve sakinlik için kısa bir cümle kullanabilirsin.",
            [remainder[:160]],
        )
    if not applied and not browse_request:
        return _clarify(inherited, "Galata çevresinde ne arıyorsun? Örneğin '1 km içinde müze bul' yazabilirsin.", ["keşif isteği eksik"])
    try:
        filters = _filters(filters)
    except ValueError as exc:
        return _clarify(inherited, str(exc), ["filtre sınırı"])
    response = _discover(filters)
    response["interpretation"] = {
        "applied_constraints": applied, "unsupported_constraints": [],
        "place_category": filters["place_category"],
        "parser": "bounded_turkish_filters_v1",
    }
    return response
