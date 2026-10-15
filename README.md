# Victoria votes 2026

An independent, non-partisan explainer of the 28 November 2026 Victorian state election: how voting works, the two houses, preferences vs proportional representation, 2022 margins + 2026 projections, candidate lists, and an interactive map of your district & region.

**No build step.** All pages are static HTML with vanilla JS. Open `index.html` directly or serve the folder with any static web server.

## Run locally

```sh
python3 -m http.server --bind 127.0.0.1 8765
# then open http://127.0.0.1:8765
```

## Deploy

Any static host works — the site is just files. Fast options:

- **Netlify Drop** — zip the folder (`zip -r vote-site.zip . -x '*.git*' -x '__pycache__/*' -x '*.pyc'`), drop at [app.netlify.com/drop](https://app.netlify.com/drop). Instant URL, no account needed for a draft.
- **Cloudflare Pages** — `npx wrangler pages deploy .` (needs Cloudflare auth).
- **GitHub Pages** — push repo + enable Pages. Note: path-prefix hosting breaks absolute `/assets/` paths; use the custom domain or a repo named `<user>.github.io`.

## Data refresh

Data lives in `assets/data/`. Scripts in `scripts/` rebuild each file from Wikipedia / VEC:

- `scripts/parse_candidates.py` → `candidates.json` (2026 candidates by district + region)
- `scripts/scrape_bios.py` → `bios.json` (Wikipedia bios for ~600 members/candidates)
- `scripts/parse_margins.py` → `margins.json` (2022 TPP)
- `scripts/parse_margins_2018.py` → `margins_2018.json` (2018 TPP for trajectory)
- Boundary GeoJSONs re-downloadable from Vicmap Admin WFS.

## Licence & attribution

- Boundaries: © State of Victoria (Vicmap Admin), CC BY 4.0
- Representative + candidate data: Wikipedia (CC BY-SA)
- Independent civic-info resource. Authoritative source for all election matters: [Victorian Electoral Commission](https://www.vec.vic.gov.au).
