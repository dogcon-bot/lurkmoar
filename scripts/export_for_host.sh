#!/usr/bin/env bash
# Build a slim deploy/ tree for PythonAnywhere (or any host that only serves).
# Run from repo root or any cwd; paths are resolved relative to this script.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${ROOT}/deploy"
STAMP="$(date -u +%Y-%m-%dT%H:%MZ)"

echo "Lurkmoar export_for_host → ${DEST}"
rm -rf "${DEST}"
mkdir -p "${DEST}/data" "${DEST}/templates" "${DEST}/static" "${DEST}/scripts"

# App + deps (no outbound ingest on host)
cp -a "${ROOT}/app.py" "${DEST}/"
cp -a "${ROOT}/requirements.txt" "${DEST}/"
cp -a "${ROOT}/Procfile" "${DEST}/" 2>/dev/null || true
cp -a "${ROOT}/templates/." "${DEST}/templates/"
cp -a "${ROOT}/static/." "${DEST}/static/"

# JSON the Flask app reads (ingest runs off-box before this)
if [[ -f "${ROOT}/data/listings.json" ]]; then
  cp -a "${ROOT}/data/listings.json" "${DEST}/data/"
else
  echo '[]' > "${DEST}/data/listings.json"
fi
if [[ -f "${ROOT}/data/radar.json" ]]; then
  cp -a "${ROOT}/data/radar.json" "${DEST}/data/"
else
  echo '[]' > "${DEST}/data/radar.json"
fi

# Docs only — do not ship radar_ingest.py to free PA (it needs outbound HTTP)
cp -a "${ROOT}/scripts/sync_data_note.md" "${DEST}/scripts/"
cp -a "${ROOT}/README.md" "${DEST}/" 2>/dev/null || true

# Marker so ops know this tree is serve-only
cat > "${DEST}/DEPLOY_MARKER.txt" << MARK
Lurkmoar serve-only export
Built: ${STAMP} UTC
Upload this folder to PythonAnywhere (or similar).
Do NOT run scripts/radar_ingest.py on free PA — run off-box, then re-export/upload data/*.json.
See scripts/sync_data_note.md and README (PythonAnywhere section).
MARK

echo "Done. Upload deploy/ to the host (WSGI: app:app)."
echo "  data/listings.json and data/radar.json included."
ls -la "${DEST}" "${DEST}/data"
