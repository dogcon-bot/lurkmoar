# Lurkmoar MVP

Classic **Nissan / Honda** niche classifieds board + **Deal Radar** tab.

Categories: `Z` · `S-chassis` · `old Honda` · `Wanted` · `For Sale`

Stack: Python 3 + Flask, JSON file storage (`data/listings.json`, `data/radar.json`).
No payments, no FB Marketplace scrape, no mobile-repair content.

## Architecture (PythonAnywhere-friendly)

| Piece | Where it runs | Network |
|-------|---------------|---------|
| **Flask webapp** (`app.py`) | Host (PA free / box) | **Serve only** — reads `data/*.json`, no outbound scrape |
| **Deal Radar ingest** (`scripts/radar_ingest.py`) | **Off-box** (Jobs Desk box / bots) | Outbound to BaT, CL RSS, etc. |
| **JSON sync** | After ingest | Commit/upload `data/radar.json` (+ `listings.json`) to host |

Free PythonAnywhere **allowlists outbound HTTP**. Keep scraping on the box; push JSON to the deploy tree. Details: [`scripts/sync_data_note.md`](scripts/sync_data_note.md).

## Quick start (this box)

```bash
cd /workspace/lurkmoar
python3 -m venv .venv          # once
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Open: **http://127.0.0.1:8787/** (or the box host on port **8787**)

Alternate: `./run.sh`

## What’s included

| Path | Purpose |
|------|---------|
| `app.py` | Flask app: board, post form, detail, radar (**reads JSON only**) |
| `data/listings.json` | Classifieds (SAMPLE seeds; host may also accept `/post`) |
| `data/radar.json` | Deal Radar rows (bots append via **off-box** ingest) |
| `scripts/radar_ingest.py` | Off-box public-feed ingest → `radar.json` |
| `scripts/sync_data_note.md` | How to sync JSON onto the host after ingest |
| `scripts/export_for_host.sh` | Copies app + `data/` into `deploy/` for PA upload |
| `templates/` | HTML |
| `static/style.css` | Dark niche-board UI |
| `APPLY` | Ports + start command for ops |
| `run.sh` | Convenience launcher |

## PythonAnywhere (free) deploy

Target: **`username.pythonanywhere.com`** subdomain only.

Constraints (free tier):

- **No custom domain** on free (paid for that).
- Account / free web app needs **monthly renewal** (PA free accounts expire if not renewed).
- **Outbound HTTP is allowlisted** — do **not** run `radar_ingest.py` on PA; run it on the Jobs Desk box (or another machine with open egress), then upload/commit JSON.
- Flask should **mostly serve** static templates + local JSON.

### Upload / WSGI

1. On the box, refresh radar data and build a uploadable tree:
   ```bash
   cd /workspace/lurkmoar
   .venv/bin/python scripts/radar_ingest.py
   ./scripts/export_for_host.sh
   ```
2. Upload `deploy/` contents to your PA home (e.g. `~/lurkmoar/`).
3. Web tab → Add a new web app → **Manual configuration** → Python 3.x.
4. Source code / working directory: `~/lurkmoar` (or wherever you uploaded).
5. WSGI file: import the Flask app, e.g.
   ```python
   import sys
   path = "/home/YOURUSER/lurkmoar"
   if path not in sys.path:
       sys.path.append(path)
   from app import app as application
   ```
6. Install deps in a PA virtualenv or via the Web tab Consoles:
   `pip install --user -r requirements.txt` (flask; gunicorn optional on PA).
7. Reload the web app. Visit `https://YOURUSER.pythonanywhere.com/`.

### Refresh Deal Radar on PA

```
run ingest on box → commit/upload data/radar.json (+ listings.json) to host → Reload
```

Same flow is documented in [`scripts/sync_data_note.md`](scripts/sync_data_note.md).

## Deal Radar ingest (bots — off-box)

Append/dedupe into `data/radar.json` with the bot script (stdlib only — no extra pip deps):

```bash
cd /workspace/lurkmoar
.venv/bin/python scripts/radar_ingest.py
```

Cron-friendly; safe to re-run. Behavior:

- **Sources (legal public only):** Bring a Trailer public make/model pages; Craigslist RSS search feeds when the host allows them; best-effort public forum classified indexes.
- **Niche filter:** classic Z / S-chassis / old Honda keywords only.
- **Respectful:** custom User-Agent, ~2.5s pause between requests, soft-fail on 403/timeout (does not wipe existing rows).
- **Dedupe:** by listing URL (and id); refreshes `seen_at` / price on match.
- **Out of scope:** Facebook Marketplace scrape.
- **Host:** Flask never calls these URLs — only reads the JSON you sync.

Schema for each row:

```json
{
  "id": "unique",
  "source": "bot-name",
  "title": "...",
  "category": "Z",
  "price": "$…",
  "url": "https://…",
  "notes": "",
  "seen_at": "2026-09-11T12:00:00Z",
  "sample": false
}
```

## Point a domain later (paid host / VPS — not free PA)

Flask already binds `0.0.0.0:8787`. Free PythonAnywhere does **not** support custom domains; use GoDaddy → VPS/nginx or a paid plan when ready:

1. **DNS (GoDaddy)**  
   - A record → your VPS / box public IP, **or**  
   - CNAME → a hostname you already control.

2. **Reverse proxy (recommended)** on the same Linux host:

   ```nginx
   # /etc/nginx/sites-available/lurkmoar
   server {
     listen 80;
     server_name lurkmoar.com www.lurkmoar.com;  # your domain

     location / {
       proxy_pass http://127.0.0.1:8787;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
     }
   }
   ```

   Then: `sudo ln -s ...sites-available/lurkmoar ...sites-enabled/` and reload nginx.
   Add HTTPS with Certbot (`certbot --nginx`) when ready.

3. **Keep the app up** with systemd or a process manager:

   ```ini
   # /etc/systemd/system/lurkmoar.service (sketch)
   [Service]
   WorkingDirectory=/workspace/lurkmoar
   ExecStart=/workspace/lurkmoar/.venv/bin/python app.py
   Restart=on-failure
   ```

4. **Security before public**  
   - Change `app.secret_key` in `app.py`  
   - Do not expose debug mode  
   - Back up `data/*.json`

See also `DEPLOY.md` for ephemeral tunnel notes on this box.

## Out of scope (MVP)

- Payments / checkout  
- Facebook Marketplace scraping  
- Mobile phone repair content  
- Running Deal Radar scrape **on** free PythonAnywhere  
