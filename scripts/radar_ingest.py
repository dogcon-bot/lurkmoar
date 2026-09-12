#!/usr/bin/env python3
"""Lurkmoar Deal Radar ingest — OFF-BOX only (Jobs Desk box / bots).

Run this where outbound HTTP is allowed. Do **not** run on free
PythonAnywhere (allowlisted egress). After ingest, sync ``data/radar.json``
(and optionally ``data/listings.json``) onto the host — see
``scripts/sync_data_note.md`` or ``./scripts/export_for_host.sh``.

Sources (respectful, rate-limited, fail-soft):
  - Bring a Trailer public make/model listing pages
  - Craigslist public RSS search feeds (when available)
  - Optional public forum classified index pages (best-effort)

NO Facebook Marketplace. Classic Nissan/Honda niche only:
  Z · S-chassis · old Honda (+ Wanted / For Sale when clearly parts/wanted)

Usage (from repo root or anywhere):
  /workspace/lurkmoar/.venv/bin/python scripts/radar_ingest.py
  # or:
  cd /workspace/lurkmoar && .venv/bin/python -m scripts.radar_ingest

Appends/dedupes into data/radar.json matching README schema.
The Flask app (app.py) only *reads* that file — no scrape from the webapp.
"""

from __future__ import annotations

import hashlib
import html as htmlmod
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent.parent
RADAR_PATH = BASE / "data" / "radar.json"

USER_AGENT = (
    "LurkmoarDealRadar/0.1 (+https://lurkmoar.local; "
    "classic Nissan/Honda niche board; respectful bot; contact ops@lurkmoar.local)"
)
REQUEST_PAUSE_SEC = 2.5
HTTP_TIMEOUT = 25
MAX_PER_SOURCE = 8

# Public BaT make/model index pages (HTML listing cards).
BAT_PAGES = [
    ("https://bringatrailer.com/datsun/240z/", "Z"),
    ("https://bringatrailer.com/datsun/260z/", "Z"),
    ("https://bringatrailer.com/datsun/280z/", "Z"),
    ("https://bringatrailer.com/nissan/300zx/", "Z"),
    ("https://bringatrailer.com/nissan/240sx/", "S-chassis"),
    ("https://bringatrailer.com/nissan/silvia/", "S-chassis"),
    ("https://bringatrailer.com/honda/crx/", "old Honda"),
    ("https://bringatrailer.com/honda/prelude/", "old Honda"),
    ("https://bringatrailer.com/acura/integra/", "old Honda"),
]

# Craigslist metros + niche queries → category. RSS when CL allows it.
CL_METROS = [
    "seattle",
    "portland",
    "sfbay",
    "losangeles",
    "sandiego",
    "phoenix",
    "denver",
    "chicago",
]
CL_QUERIES = [
    ("240z", "Z"),
    ("280z", "Z"),
    ("300zx", "Z"),
    ("240sx", "S-chassis"),
    ("s13 silvia", "S-chassis"),
    ("honda crx", "old Honda"),
    ("civic ef", "old Honda"),
    ("integra gs-r", "old Honda"),
]

# Best-effort public classified indexes (HTML). Fail soft if blocked/redirected.
FORUM_PAGES = [
    (
        "https://www.zcar.com/forums/classifieds.20/",
        "Z",
        "zcar-classifieds",
        [
            r"240z",
            r"260z",
            r"280z",
            r"300zx",
            r"fairlady",
            r"\bz31\b",
            r"\bz32\b",
        ],
    ),
]

NICHE_TITLE_RE = re.compile(
    r"(240z|260z|280z|300zx|350z|fairlady|z31|z32|"
    r"240sx|s13|s14|s15|silvia|180sx|200sx|"
    r"crx|civic\s*(ef|eg|ek|em)|integra|prelude|s2000|"
    r"b16|b18|ka24|sr20|rb20|rb25|l24|l28)",
    re.I,
)

PARTS_HINT_RE = re.compile(
    r"\b(parts?|carburetor|manifold|intake|turbo|ecu|wheels?|seat|"
    r"interior|engine\s+only|transmission\s+only|soft top)\b",
    re.I,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch_text(url: str) -> tuple[str | None, str | None]:
    """Return (body, error_message). Soft-fail on block/timeout."""
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/html, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read()
            charset = "utf-8"
            ctype = resp.headers.get("Content-Type", "")
            m = re.search(r"charset=([\w-]+)", ctype, re.I)
            if m:
                charset = m.group(1)
            return raw.decode(charset, "replace"), None
    except HTTPError as e:
        return None, f"HTTP {e.code} for {url}"
    except URLError as e:
        return None, f"URL error for {url}: {e.reason}"
    except Exception as e:  # noqa: BLE001 — ingest must never crash the batch
        return None, f"{type(e).__name__} for {url}: {e}"


def load_radar() -> list:
    if not RADAR_PATH.exists():
        return []
    try:
        with RADAR_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_radar(rows: list) -> None:
    RADAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RADAR_PATH.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
        f.write("\n")


def stable_id(source: str, url: str, title: str) -> str:
    key = f"{source}|{url}|{title}".encode("utf-8")
    return "rad_" + hashlib.sha1(key).hexdigest()[:10]


def clean_text(s: str) -> str:
    s = htmlmod.unescape(s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def looks_niche(title: str, url: str = "") -> bool:
    blob = f"{title} {url}"
    return bool(NICHE_TITLE_RE.search(blob))


def category_for(title: str, hint: str | None = None) -> str:
    t = title.lower()
    if PARTS_HINT_RE.search(t) and not re.search(
        r"\b(240z|260z|280z|300zx|240sx|crx|integra|prelude)\b.*\b(parts?)\b",
        t,
    ):
        # standalone parts lots → For Sale; full cars stay in chassis cats
        if re.search(
            r"^(?=.*(carb|manifold|turbo|ecu|wheels|seats?))(?!.*(19\d{2}|20\d{2}).*(z|sx|crx|civic|integra))",
            t,
        ):
            return "For Sale"
    if re.search(r"\b(wanted|looking for|wtb)\b", t):
        return "Wanted"
    if hint in {"Z", "S-chassis", "old Honda", "Wanted", "For Sale"}:
        # refine parts on a model page
        if PARTS_HINT_RE.search(t) and not re.search(
            r"\b(19\d{2}|20\d{2})\b.*(240z|260z|280z|300zx|240sx|crx|civic|integra|prelude)",
            t,
            re.I,
        ):
            if not re.search(
                r"\b(19\d{2}|20\d{2})\s+(datsun|nissan|honda|acura)\b", t, re.I
            ):
                return "For Sale"
        return hint
    if re.search(r"240z|260z|280z|300zx|fairlady|z31|z32|350z", t):
        return "Z"
    if re.search(r"240sx|s13|s14|s15|silvia|180sx", t):
        return "S-chassis"
    if re.search(r"crx|civic|integra|prelude|s2000|honda|acura", t):
        return "old Honda"
    return hint or "For Sale"


def make_row(
    *,
    source: str,
    title: str,
    category: str,
    price: str,
    url: str,
    notes: str,
    sample: bool = False,
) -> dict:
    title = clean_text(title)
    price = clean_text(price) or "—"
    url = clean_text(url)
    notes = clean_text(notes)
    return {
        "id": stable_id(source, url, title),
        "source": source,
        "title": title,
        "category": category,
        "price": price,
        "url": url,
        "notes": notes,
        "seen_at": utc_now(),
        "sample": sample,
    }


def parse_bat_page(body: str, category_hint: str) -> list[dict]:
    rows: list[dict] = []
    # Card pattern: image-overlay link with title, then bid-formatted nearby.
    for m in re.finditer(
        r'<a class="image-overlay" href="(https://bringatrailer\.com/listing/[^"]+)" '
        r'title="([^"]+)"',
        body,
    ):
        url, title = m.group(1), clean_text(m.group(2))
        if not looks_niche(title, url) and category_hint not in {
            "Z",
            "S-chassis",
            "old Honda",
        }:
            continue
        # Prefer year+model cars; still allow clear niche titles
        snippet = body[m.start() : m.start() + 2200]
        bid_m = re.search(
            r'class="bid-formatted[^"]*"[^>]*>\s*([^<]+)',
            snippet,
            re.I,
        )
        price = clean_text(bid_m.group(1)) if bid_m else "—"
        if price and not price.startswith("$") and "USD" in price.upper():
            # "USD $25,000" → "$25,000"
            am = re.search(r"\$[\d,]+", price)
            if am:
                price = am.group(0)
        excerpt_m = re.search(
            r'class="item-excerpt"[^>]*>(.*?)</div>',
            snippet,
            re.I | re.S,
        )
        notes = clean_text(re.sub(r"<[^>]+>", " ", excerpt_m.group(1)))[:180] if excerpt_m else "BaT public listing"
        if not notes:
            notes = "BaT public listing"
        cat = category_for(title, category_hint)
        rows.append(
            make_row(
                source="bringatrailer",
                title=title,
                category=cat,
                price=price,
                url=url,
                notes=notes,
            )
        )
        if len(rows) >= MAX_PER_SOURCE:
            break
    return rows


def parse_cl_rss(body: str, category_hint: str, metro: str) -> list[dict]:
    rows: list[dict] = []
    try:
        # CL RSS sometimes has no default namespace; sometimes does.
        root = ET.fromstring(body)
    except ET.ParseError:
        return rows

    # Find items regardless of namespace
    items = root.findall(".//item")
    if not items:
        # namespaced
        items = [
            el
            for el in root.iter()
            if el.tag.endswith("item") or el.tag == "item"
        ]

    def child_text(item: ET.Element, name: str) -> str:
        for ch in item:
            local = ch.tag.split("}")[-1] if "}" in ch.tag else ch.tag
            if local == name:
                return clean_text(ch.text or "")
        return ""

    for item in items:
        title = child_text(item, "title")
        link = child_text(item, "link")
        desc = child_text(item, "description")
        if not title or not link:
            continue
        if not looks_niche(title, link):
            continue
        price_m = re.search(r"\$[\d,]+", title) or re.search(r"\$[\d,]+", desc)
        price = price_m.group(0) if price_m else "—"
        # Strip trailing price from title if present: "240z - $5000 (seattle)"
        title_clean = re.sub(r"\s*[-–—]?\s*\$[\d,]+.*$", "", title).strip() or title
        rows.append(
            make_row(
                source=f"craigslist-{metro}",
                title=title_clean,
                category=category_for(title_clean, category_hint),
                price=price,
                url=link,
                notes=(clean_text(re.sub(r"<[^>]+>", " ", desc))[:160] or f"CL {metro} RSS"),
            )
        )
        if len(rows) >= MAX_PER_SOURCE:
            break
    return rows


def parse_forum_index(
    body: str,
    final_hint: str,
    source: str,
    title_patterns: list[str],
    base_url: str,
) -> list[dict]:
    rows: list[dict] = []
    pat = re.compile("|".join(title_patterns), re.I)
    # Generic thread/listing anchors
    for m in re.finditer(
        r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,120})</a>',
        body,
        re.I,
    ):
        href, title = m.group(1), clean_text(m.group(2))
        if not pat.search(title):
            continue
        if href.startswith("#") or "javascript:" in href.lower():
            continue
        url = urljoin(base_url, href)
        # skip nav chrome
        if urlparse(url).path.count("/") < 2 and "thread" not in url.lower():
            # still allow classified thread urls
            if not re.search(r"(thread|listing|classified|showthread)", url, re.I):
                continue
        rows.append(
            make_row(
                source=source,
                title=title,
                category=category_for(title, final_hint),
                price="—",
                url=url,
                notes="Public forum classified index",
            )
        )
        if len(rows) >= MAX_PER_SOURCE:
            break
    return rows


def ingest_bat() -> list[dict]:
    found: list[dict] = []
    for url, hint in BAT_PAGES:
        log(f"  BAT fetch {url}")
        body, err = fetch_text(url)
        time.sleep(REQUEST_PAUSE_SEC)
        if err or not body:
            log(f"    soft-fail: {err or 'empty body'}")
            continue
        rows = parse_bat_page(body, hint)
        log(f"    parsed {len(rows)} niche listing(s)")
        found.extend(rows)
    return found


def ingest_craigslist() -> list[dict]:
    found: list[dict] = []
    # Limit total CL requests per run to stay polite
    budget = 12
    for metro in CL_METROS:
        for query, hint in CL_QUERIES:
            if budget <= 0:
                return found
            q = quote_plus(query)
            url = f"https://{metro}.craigslist.org/search/cta?query={q}&format=rss"
            log(f"  CL RSS {metro} q={query!r}")
            body, err = fetch_text(url)
            time.sleep(REQUEST_PAUSE_SEC)
            budget -= 1
            if err or not body:
                log(f"    soft-fail: {err or 'empty body'}")
                # If metro is hard-blocked, skip remaining queries for this metro
                if err and ("HTTP 403" in err or "HTTP 410" in err or "HTTP 404" in err):
                    break
                continue
            if "<rss" not in body[:500].lower() and "<rdf" not in body[:500].lower():
                log("    soft-fail: response not RSS")
                break
            rows = parse_cl_rss(body, hint, metro)
            log(f"    parsed {len(rows)} niche item(s)")
            found.extend(rows)
    return found


def ingest_forums() -> list[dict]:
    found: list[dict] = []
    for url, hint, source, patterns in FORUM_PAGES:
        log(f"  Forum fetch {url}")
        body, err = fetch_text(url)
        time.sleep(REQUEST_PAUSE_SEC)
        if err or not body:
            log(f"    soft-fail: {err or 'empty body'}")
            continue
        rows = parse_forum_index(body, hint, source, patterns, url)
        log(f"    parsed {len(rows)} candidate link(s)")
        found.extend(rows)
    return found


def dedupe_merge(existing: list, incoming: list[dict]) -> tuple[list, int]:
    """Merge by url (preferred) or id. Refresh seen_at on URL match; keep non-sample."""
    by_url: dict[str, int] = {}
    by_id: dict[str, int] = {}
    out = list(existing)
    for i, row in enumerate(out):
        u = (row.get("url") or "").strip()
        if u:
            by_url[u] = i
        rid = row.get("id")
        if rid:
            by_id[rid] = i

    added = 0
    for row in incoming:
        url = (row.get("url") or "").strip()
        rid = row.get("id")
        idx = by_url.get(url) if url else None
        if idx is None and rid in by_id:
            idx = by_id[rid]
        if idx is not None:
            prev = out[idx]
            # Don't overwrite a curated sample with empty live miss; do refresh live rows
            if prev.get("sample") and not row.get("sample"):
                out[idx] = row
            elif not prev.get("sample"):
                merged = dict(prev)
                merged.update({k: row[k] for k in ("title", "price", "notes", "category", "seen_at") if row.get(k)})
                merged["url"] = url or prev.get("url", "")
                merged["source"] = row.get("source") or prev.get("source")
                merged["sample"] = False
                out[idx] = merged
            continue
        out.append(row)
        added += 1
        if url:
            by_url[url] = len(out) - 1
        if rid:
            by_id[rid] = len(out) - 1
    return out, added


def drop_placeholder_samples(rows: list) -> list:
    """Remove thin placeholder seed once real (or richer) rows exist."""
    real = [r for r in rows if not r.get("sample")]
    if not real:
        return rows
    return [
        r
        for r in rows
        if not (
            r.get("sample")
            and (
                "placeholder" in (r.get("title") or "").lower()
                or (r.get("id") == "rad001")
            )
        )
    ]


def main(argv: Iterable[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    log(f"Lurkmoar Deal Radar ingest → {RADAR_PATH}")
    log("Niche: Z / S-chassis / old Honda — public feeds only (no FB Marketplace)")

    incoming: list[dict] = []
    log("Bring a Trailer (public pages)…")
    incoming.extend(ingest_bat())
    log("Craigslist RSS (public; fail-soft if blocked)…")
    incoming.extend(ingest_craigslist())
    log("Public forum classified indexes (best-effort)…")
    incoming.extend(ingest_forums())

    # Dedupe within this run by URL
    seen_urls: set[str] = set()
    unique: list[dict] = []
    for row in incoming:
        u = row.get("url") or ""
        if u and u in seen_urls:
            continue
        if u:
            seen_urls.add(u)
        unique.append(row)

    existing = load_radar()
    merged, added = dedupe_merge(existing, unique)
    merged = drop_placeholder_samples(merged)
    # Stable-ish order: newest seen_at first
    merged.sort(key=lambda r: r.get("seen_at") or "", reverse=True)
    save_radar(merged)

    live = sum(1 for r in unique if not r.get("sample"))
    log(f"Done. Fetched {live} live niche hit(s); appended {added} new row(s); radar total {len(merged)}.")
    if live == 0:
        log("No live hits this run (sources blocked or empty). radar.json left empty-safe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
