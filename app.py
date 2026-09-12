#!/usr/bin/env python3
"""Lurkmoar MVP — classic Nissan/Honda niche classifieds + Deal Radar.

Serve-only for free hosts (e.g. PythonAnywhere): this app reads/writes local
``data/*.json`` only. It never fetches remote URLs. Deal Radar ingest runs
off-box via ``scripts/radar_ingest.py``; sync JSON onto the host (see
``scripts/sync_data_note.md``).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
LISTINGS_PATH = DATA / "listings.json"
RADAR_PATH = DATA / "radar.json"

CATEGORIES = [
    "Z",
    "S-chassis",
    "old Honda",
    "Wanted",
    "For Sale",
]

app = Flask(__name__)
app.secret_key = "lurkmoar-dev-only-change-in-prod"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def load_listings() -> list:
    return load_json(LISTINGS_PATH, [])


def save_listings(listings: list) -> None:
    save_json(LISTINGS_PATH, listings)


def load_radar() -> list:
    return load_json(RADAR_PATH, [])


@app.route("/")
def index():
    listings = load_listings()
    category = request.args.get("category", "").strip()
    if category and category in CATEGORIES:
        listings = [L for L in listings if L.get("category") == category]
    # newest first
    listings = sorted(listings, key=lambda x: x.get("created_at", ""), reverse=True)
    return render_template(
        "index.html",
        listings=listings,
        categories=CATEGORIES,
        active_category=category,
        page="board",
    )


@app.route("/post", methods=["GET", "POST"])
def post():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        category = (request.form.get("category") or "").strip()
        price = (request.form.get("price") or "").strip()
        location = (request.form.get("location") or "").strip()
        contact = (request.form.get("contact") or "").strip()
        body = (request.form.get("body") or "").strip()

        errors = []
        if not title:
            errors.append("Title is required.")
        if category not in CATEGORIES:
            errors.append("Pick a valid category.")
        if not body:
            errors.append("Description is required.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "post.html",
                categories=CATEGORIES,
                form=request.form,
                page="post",
            )

        listing = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "category": category,
            "price": price or "Contact",
            "location": location or "—",
            "contact": contact or "—",
            "body": body,
            "sample": False,
            "created_at": _utc_now(),
        }
        listings = load_listings()
        listings.append(listing)
        save_listings(listings)
        flash("Listing posted.", "ok")
        return redirect(url_for("index"))

    return render_template(
        "post.html",
        categories=CATEGORIES,
        form={},
        page="post",
    )


@app.route("/listing/<listing_id>")
def listing_detail(listing_id: str):
    listings = load_listings()
    item = next((L for L in listings if L.get("id") == listing_id), None)
    if not item:
        flash("Listing not found.", "error")
        return redirect(url_for("index"))
    return render_template(
        "detail.html",
        listing=item,
        categories=CATEGORIES,
        page="board",
    )


@app.route("/radar")
def radar():
    rows = load_radar()
    rows = sorted(rows, key=lambda x: x.get("seen_at", ""), reverse=True)
    return render_template(
        "radar.html",
        rows=rows,
        categories=CATEGORIES,
        page="radar",
    )


if __name__ == "__main__":
    DATA.mkdir(parents=True, exist_ok=True)
    if not LISTINGS_PATH.exists():
        save_listings([])
    if not RADAR_PATH.exists():
        save_radar = save_json  # noqa: F841 — keep radar seed separate
        save_json(RADAR_PATH, [])
    # Bind all interfaces so reverse proxy / domain can reach it later
    app.run(host="0.0.0.0", port=8787, debug=False)
