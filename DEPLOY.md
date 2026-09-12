# Lurkmoar — deploy notes

Updated: 2026-09-11 ~5:15 PM PT

## Preferred free host: PythonAnywhere

Free PA = **subdomain only** (`username.pythonanywhere.com`), **no custom domain**, renew monthly.
**Ingest off-box**; webapp only reads `data/*.json`. See README → **PythonAnywhere (free) deploy**
and `scripts/sync_data_note.md`. Build upload tree: `./scripts/export_for_host.sh`.

---


## Public HTTPS URL (live now)

**https://hey-mathematics-neighbor-customized.trycloudflare.com**

- Serves the Flask board (/, /radar, /post) over HTTPS.
- Backed by Cloudflare **quick tunnel** → box `127.0.0.1:8787`.
- **No Cloudflare / Render / Fly login used** (account-less quick tunnel).

### GoDaddy forward target

Point lurkmoar.com (and www) **forwarding / domain forward** at:

```
https://hey-mathematics-neighbor-customized.trycloudflare.com
```

Parent flips this in GoDaddy browser UI — do **not** change DNS from this box.

**Caveat:** quick-tunnel hostnames are **ephemeral**. If cloudflared or the Flask process restarts, the `*.trycloudflare.com` URL **changes**. Re-read `data/public-url.txt` or `/tmp/lurkmoar-cloudflared.log` after a restart, then update GoDaddy forward.

---

## What’s running on the box

| Piece | Detail |
|-------|--------|
| Flask | `PID` in `data/server.pid` — `.venv/bin/python app.py` on `0.0.0.0:8787` |
| Tunnel | `PID` in `data/cloudflared.pid` — `cloudflared tunnel --url http://127.0.0.1:8787` |
| Flask log | `/tmp/lurkmoar.log` |
| Tunnel log | `/tmp/lurkmoar-cloudflared.log` |
| Current URL file | `data/public-url.txt` |

Health:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8787/
curl -s -o /dev/null -w '%{http_code}\n' "$(cat data/public-url.txt)/"
```

---

## How to redeploy / restart (this box)

```bash
cd /workspace/lurkmoar

# 1) Flask
pkill -f '/workspace/lurkmoar/app.py' || true
nohup .venv/bin/python app.py > /tmp/lurkmoar.log 2>&1 &
echo $! > data/server.pid

# 2) Cloudflare quick tunnel (new URL each start)
pkill -f 'cloudflared tunnel --url http://127.0.0.1:8787' || true
nohup cloudflared tunnel --url http://127.0.0.1:8787 > /tmp/lurkmoar-cloudflared.log 2>&1 &
echo $! > data/cloudflared.pid
sleep 5
grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/lurkmoar-cloudflared.log | head -1 | tee data/public-url.txt
```

Then update GoDaddy forward to the new URL.

---

## Durable host (preferred long-term) — blocked on Leon login

Box has **no** Render / Fly.io / Railway / GitHub CLI auth. Port **8787 is not open** on the box public IP (`54.198.11.244`), so A-record → box will not work without firewall/SG changes.

Scaffolding already in-repo for Render free Web Service:

- `Procfile` — `gunicorn -b 0.0.0.0:$PORT -w 2 app:app`
- `render.yaml` — free plan blueprint
- `requirements.txt` — flask + gunicorn

### Next step for parent (Leon signs in)

1. **Render (recommended):** open https://dashboard.render.com/login  
   - New → Web Service (or Blueprint with `render.yaml`)  
   - Connect a GitHub repo containing `/workspace/lurkmoar` **or** deploy from CLI after `render login`  
   - Build: `pip install -r requirements.txt`  
   - Start: `gunicorn -b 0.0.0.0:$PORT -w 2 app:app`  
   - Note: free disk is ephemeral — posts to `data/*.json` reset on redeploy unless you add a disk or external store.

2. **Fly.io:** https://fly.io/app/sign-in → `fly launch` from app dir after CLI auth.

3. **Railway:** https://railway.app/login → new Python service from repo.

4. **Named Cloudflare tunnel (stable subdomain):** https://dash.cloudflare.com/login → Zero Trust → Tunnels → create named tunnel, then `cloudflared tunnel run` with a config that keeps the same hostname. Still needs Leon’s Cloudflare account.

Until one of those is authenticated on this box, keep using the trycloudflare URL above and refresh GoDaddy when the hostname rotates.

### Parent helpers

- `request_user_form` / `request_box_help`: have Leon complete Render login at https://dashboard.render.com/login (or Cloudflare at https://dash.cloudflare.com/login for a named tunnel), then re-run deploy.

---

## Out of scope here

- GoDaddy DNS / forwarding changes (parent browser).
- Stolen or scraped credentials — none used.
