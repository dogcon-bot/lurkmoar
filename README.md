# Lurkmoar MVP

Classic **Nissan / Honda** niche classifieds board + **Deal Radar** tab.

Categories: `Z` · `S-chassis` · `old Honda` · `Wanted` · `For Sale`

Stack: Python 3 + Flask, JSON file storage (`data/listings.json`, `data/radar.json`).
No payments, no FB Marketplace scrape, no mobile-repair content.

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
| `app.py` | Flask app: board, post form, detail, radar |
| `data/listings.json` | Classifieds (5 SAMPLE seeds) |
| `data/radar.json` | Deal Radar rows (placeholder; bots append later) |
| `templates/` | HTML |
| `static/style.css` | Dark niche-board UI |
| `APPLY` | Ports + start command for ops |
| `run.sh` | Convenience launcher |

## Point a GoDaddy domain later

Flask already binds `0.0.0.0:8787`. When DNS is ready:

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

Static-only alternative: export later if you drop the post form; for now Flask is the durable path.

## Radar bots (later)

Append objects to `data/radar.json` (or add a small POST API). Schema:

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

## Out of scope (MVP)

- Payments / checkout  
- Facebook Marketplace scraping  
- Mobile phone repair content  
