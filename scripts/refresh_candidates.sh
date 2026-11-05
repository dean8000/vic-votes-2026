#!/usr/bin/env bash
# One-shot refresh: fetch Wikipedia candidate page, re-parse, re-scrape party bios, rebuild projections.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "[1/4] Downloading Wikipedia candidate list…"
curl -sL --max-time 60 \
  "https://en.wikipedia.org/wiki/Candidates_of_the_2026_Victorian_state_election" \
  -o /tmp/vic_candidates.html

echo "[2/4] Parsing candidates…"
python3 "$ROOT/scripts/parse_candidates.py"

echo "[3/4] Refreshing polling…"
python3 "$ROOT/scripts/refresh_polling.py"

echo "[4/5] Refreshing candidate bios (ABC + party sites)…"
python3 "$ROOT/scripts/scrape_party_bios.py" >/dev/null

echo "[5/6] Rebuilding projections from current swing…"
python3 "$ROOT/scripts/rebuild_projections.py"

echo "[6/8] Rebuilding battlegrounds (curated flip/toss-up categories)…"
python3 "$ROOT/scripts/build_battlegrounds.py"

echo "[7/8] Refreshing VEC early voting centres…"
python3 "$ROOT/scripts/build_voting_centres.py" || echo "(skipped — openpyxl not installed or VEC unreachable)"

echo "[8/8] Updating last-refresh snapshot…"
python3 "$ROOT/scripts/generate_refresh_summary.py"

echo "Done."
