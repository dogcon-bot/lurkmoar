# Sync Deal Radar JSON onto the host (PythonAnywhere free)

**Architecture:** Free PythonAnywhere allowlists outbound HTTP. The webapp must **serve** files, not scrape. Run ingest **off-box** (Jobs Desk box / bots), then push JSON into the deploy tree that PA only reads.

## Path (canonical)

```
Jobs Desk box / bots
        │
        │  python scripts/radar_ingest.py
        ▼
  data/radar.json   (+ optional data/listings.json backup)
        │
        │  commit, upload, or ./scripts/export_for_host.sh
        ▼
  PythonAnywhere webapp (Flask)
        │
        │  load_json(data/*.json) only — no outbound fetch
        ▼
  /radar and board UI
```

## Steps

1. **On the box (or any machine with outbound HTTP):**
   ```bash
   cd /workspace/lurkmoar   # or your clone
   .venv/bin/python scripts/radar_ingest.py
   ```
   This updates `data/radar.json` in place (dedupe by URL).

2. **Get JSON onto the host** (pick one):
   - **Git:** commit `data/radar.json` (and `data/listings.json` if you want board seeds/backups), pull/upload on PA.
   - **Manual upload:** PA Files tab → upload into the webapp’s `data/` directory.
   - **Export bundle:** `./scripts/export_for_host.sh` → upload contents of `deploy/` to PA.

3. **On PA:** reload the web app (Web tab → Reload). Flask re-reads JSON on each request; no restart required for data-only updates if files are overwritten in place, but Reload is safest after a full upload.

## Do not

- Run `scripts/radar_ingest.py` on free PythonAnywhere (outbound to BaT/CL will fail or violate allowlist assumptions).
- Add `urllib` / `requests` fetchers to `app.py`.

## Files the host must have

| File | Written by | Read by |
|------|------------|---------|
| `data/radar.json` | off-box ingest | Flask `/radar` |
| `data/listings.json` | users via `/post` on host, or off-box seed/sync | Flask board |

See README → **PythonAnywhere (free) deploy**.
