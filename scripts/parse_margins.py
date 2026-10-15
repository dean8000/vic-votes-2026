#!/usr/bin/env python3
"""Parse 2022 Victorian state election district results from Wikipedia HTML.

Extracts two-party-preferred (TPP) or two-candidate-preferred (TCP) margins
for all 88 Legislative Assembly districts and writes a margins.json file.
"""
from __future__ import annotations

import html as _h
import json
import re
import sys
from pathlib import Path

INPUT = Path("/tmp/vic2022_results.html")
OUTPUT = Path("/Users/dean/Dev/vote/assets/data/margins.json")

EXPECTED_DISTRICTS = [
    "Albert Park", "Ashwood", "Bass", "Bayswater", "Bellarine", "Benambra",
    "Bendigo East", "Bendigo West", "Bentleigh", "Berwick", "Box Hill",
    "Brighton", "Broadmeadows", "Brunswick", "Bulleen", "Bundoora", "Carrum",
    "Caulfield", "Clarinda", "Cranbourne", "Croydon", "Dandenong", "Eildon",
    "Eltham", "Essendon", "Eureka", "Euroa", "Evelyn", "Footscray", "Frankston",
    "Geelong", "Gippsland East", "Gippsland South", "Glen Waverley",
    "Greenvale", "Hastings", "Hawthorn", "Ivanhoe", "Kalkallo", "Kew",
    "Kororoit", "Lara", "Laverton", "Lowan", "Macedon", "Malvern", "Melbourne",
    "Melton", "Mildura", "Mill Park", "Monbulk", "Mordialloc", "Mornington",
    "Morwell", "Mulgrave", "Murray Plains", "Narracan", "Narre Warren North",
    "Narre Warren South", "Nepean", "Niddrie", "Northcote", "Oakleigh",
    "Ovens Valley", "Pakenham", "Pascoe Vale", "Point Cook", "Polwarth",
    "Prahran", "Preston", "Richmond", "Ringwood", "Ripon", "Rowville",
    "Sandringham", "Shepparton", "South Barwon", "South-West Coast",
    "St Albans", "Sunbury", "Sydenham", "Tarneit", "Thomastown", "Warrandyte",
    "Wendouree", "Werribee", "Williamstown", "Yan Yean",
]

# Canonical party label used in the output (shortened/standardised).
PARTY_CANONICAL = {
    "Labor VIC": "Labor",
    "Labor": "Labor",
    "Liberal VIC": "Liberal",
    "Liberal": "Liberal",
    "Nationals VIC": "National",
    "National": "National",
    "Nationals": "National",
    "Greens VIC": "Greens",
    "Greens": "Greens",
    "Independent": "Independent",
}


def canon_party(raw: str) -> str:
    raw = raw.strip()
    if raw in PARTY_CANONICAL:
        return PARTY_CANONICAL[raw]
    # strip wiki link brackets
    stripped = re.sub(r"\[\[([^|\]]+\|)?([^\]]+)\]\]", r"\2", raw)
    stripped = stripped.strip()
    return PARTY_CANONICAL.get(stripped, stripped)


def parse_pct(s: str) -> float:
    """Parse '55.2' or '-5.0' or '−5.0' etc into float."""
    if s is None:
        return None
    s = s.strip().replace(",", "")
    # unify minus signs: unicode minus (U+2212), en-dash (U+2013), em-dash
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    if s in ("", "N/A", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        # might have a trailing %
        s2 = s.rstrip("%").strip()
        try:
            return float(s2)
        except ValueError:
            return None


def safety_band(margin: float) -> str:
    if margin < 6.0:
        return "marginal"
    if margin < 10.0:
        return "fairly safe"
    if margin < 20.0:
        return "safe"
    return "very safe"


def extract_district_data_mw(html: str, district_id: str) -> dict:
    """Find the first <table> with a data-mw attribute after the h3 anchor
    for the given district, parse the JSON, and return it."""
    anchor = f'id="{district_id}"'
    i = html.find(anchor)
    if i < 0:
        raise ValueError(f"Anchor {anchor} not found")
    # Find the next data-mw= attribute (on the table that follows the h3).
    # Allow single quotes around the attribute value.
    m = re.search(r"data-mw='([^']+)'", html[i:])
    if not m:
        raise ValueError(f"No data-mw after {anchor}")
    raw = _h.unescape(m.group(1))
    return json.loads(raw)


def process_district(name: str, data: dict) -> dict:
    """From the parsed data-mw template list, extract winner/TPP info."""
    parts = data.get("parts", [])
    templates = []
    for part in parts:
        if isinstance(part, dict) and "template" in part:
            t = part["template"]
            tname = t["target"]["wt"].strip()
            tparams = {
                k: (v.get("wt") if isinstance(v, dict) else v)
                for k, v in t.get("params", {}).items()
            }
            templates.append((tname, tparams))

    # Locate the outcome template (hold / gain).
    outcome_idx = None
    outcome_name = None
    outcome_params = None
    for idx, (tn, tp) in enumerate(templates):
        if tn.startswith("Election box hold") or tn.startswith("Election box gain"):
            outcome_idx = idx
            outcome_name = tn
            outcome_params = tp
            break
    if outcome_params is None:
        raise ValueError(f"{name}: no hold/gain template found")

    winner_party_raw = outcome_params.get("winner", "")
    winner_party = canon_party(winner_party_raw)
    swing = parse_pct(outcome_params.get("swing", ""))

    # Choose the final-round pair: prefer 2cp (TCP) over 2pp.
    # Find the LAST 2cp or 2pp marker, then take the two candidate rows
    # immediately following it (and before the hold/gain).
    marker_idx = None
    marker_kind = None
    for idx in range(outcome_idx - 1, -1, -1):
        tn, _ = templates[idx]
        if tn == "Election box 2cp":
            marker_idx = idx
            marker_kind = "2cp"
            break
        if tn == "Election box 2pp":
            marker_idx = idx
            marker_kind = "2pp"
            break
    if marker_idx is None:
        raise ValueError(f"{name}: no 2pp/2cp marker found")

    # Collect candidate-AU-party rows between the marker and the outcome.
    pair = []
    for idx in range(marker_idx + 1, outcome_idx):
        tn, tp = templates[idx]
        if tn.startswith("Election box candidate AU party"):
            pair.append(tp)

    if len(pair) < 2:
        raise ValueError(
            f"{name}: expected 2 candidate rows after {marker_kind}, got {len(pair)}"
        )

    # Take the first two (usually there are exactly two).
    cand_a, cand_b = pair[0], pair[1]
    pct_a = parse_pct(cand_a.get("percentage"))
    pct_b = parse_pct(cand_b.get("percentage"))
    party_a = canon_party(cand_a.get("party", ""))
    party_b = canon_party(cand_b.get("party", ""))

    # Pick the winner row by matching party. Fall back to higher pct if the
    # outcome winner party label does not match either row.
    if party_a == winner_party:
        tpp_winner_pct, tpp_loser_pct = pct_a, pct_b
        tpp_opponent = party_b
    elif party_b == winner_party:
        tpp_winner_pct, tpp_loser_pct = pct_b, pct_a
        tpp_opponent = party_a
    else:
        # Fallback: higher pct is the winner.
        if pct_a >= pct_b:
            tpp_winner_pct, tpp_loser_pct = pct_a, pct_b
            tpp_opponent = party_b
            winner_party = party_a
        else:
            tpp_winner_pct, tpp_loser_pct = pct_b, pct_a
            tpp_opponent = party_a
            winner_party = party_b

    margin = round(tpp_winner_pct - 50.0, 2)

    out = {
        "winner": winner_party,
        "tpp_winner_pct": tpp_winner_pct,
        "tpp_loser_pct": tpp_loser_pct,
        "tpp_opponent": tpp_opponent,
        "margin": margin,
        "safety": safety_band(margin),
        "basis": marker_kind.upper(),  # "2PP" or "2CP"
    }
    if swing is not None:
        out["swing"] = swing
    return out


def main() -> int:
    html = INPUT.read_text(encoding="utf-8")

    # Build id -> display name map from the expected list.
    id_to_name = {name.replace(" ", "_").replace("-", "-"): name for name in EXPECTED_DISTRICTS}

    results: dict[str, dict] = {}
    errors: list[tuple[str, str]] = []

    for district in EXPECTED_DISTRICTS:
        district_id = district.replace(" ", "_")
        try:
            data = extract_district_data_mw(html, district_id)
            entry = process_district(district, data)
            results[district.upper()] = entry
        except Exception as e:  # noqa: BLE001
            errors.append((district, str(e)))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")

    print(f"Captured {len(results)} / {len(EXPECTED_DISTRICTS)} districts")
    if errors:
        print("Errors:")
        for d, e in errors:
            print(f"  - {d}: {e}")
    # Sample
    print("\nSample entries:")
    import random
    sample_keys = random.sample(list(results.keys()), min(5, len(results)))
    for k in sample_keys:
        print(f"  {k}: {results[k]}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
