#!/usr/bin/env python3
"""Parse 2018 Victorian state election district results from Wikipedia HTML.

Extracts two-party-preferred (TPP) or two-candidate-preferred (TCP) margins
for Legislative Assembly districts and writes a margins_2018.json file keyed
by the 88 current (post-2021 redistribution) district names.

For current districts that did not exist in 2018 (i.e. created in the 2021
redistribution), the entry is written as null rather than fabricated.
"""
from __future__ import annotations

import html as _h
import json
import re
import sys
from pathlib import Path

INPUT = Path("/tmp/vic2018_results.html")
MEMBERS = Path("/Users/dean/Dev/vote/assets/data/members.json")
OUTPUT = Path("/Users/dean/Dev/vote/assets/data/margins_2018.json")


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
    stripped = re.sub(r"\[\[([^|\]]+\|)?([^\]]+)\]\]", r"\2", raw)
    stripped = stripped.strip()
    return PARTY_CANONICAL.get(stripped, stripped)


def parse_pct(s: str):
    if s is None:
        return None
    s = s.strip().replace(",", "")
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    if s in ("", "N/A", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
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


def display_name_from_key(key: str) -> str:
    """Convert 'SOUTH-WEST COAST' -> 'South-West Coast', etc."""
    parts = []
    for word in key.split(" "):
        if "-" in word:
            parts.append("-".join(w.capitalize() for w in word.split("-")))
        else:
            parts.append(word.capitalize())
    return " ".join(parts)


def extract_district_data_mw(html: str, district_id: str) -> dict:
    anchor = f'id="{district_id}"'
    i = html.find(anchor)
    if i < 0:
        raise ValueError(f"Anchor {anchor} not found")
    m = re.search(r"data-mw='([^']+)'", html[i:])
    if not m:
        raise ValueError(f"No data-mw after {anchor}")
    raw = _h.unescape(m.group(1))
    return json.loads(raw)


def process_district(name: str, data: dict) -> dict:
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

    outcome_idx = None
    outcome_params = None
    for idx, (tn, tp) in enumerate(templates):
        if tn.startswith("Election box hold") or tn.startswith("Election box gain"):
            outcome_idx = idx
            outcome_params = tp
            break
    if outcome_params is None:
        raise ValueError(f"{name}: no hold/gain template found")

    winner_party_raw = outcome_params.get("winner", "")
    winner_party = canon_party(winner_party_raw)
    swing = parse_pct(outcome_params.get("swing", ""))

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

    pair = []
    for idx in range(marker_idx + 1, outcome_idx):
        tn, tp = templates[idx]
        if tn.startswith("Election box candidate AU party"):
            pair.append(tp)

    if len(pair) < 2:
        raise ValueError(
            f"{name}: expected 2 candidate rows after {marker_kind}, got {len(pair)}"
        )

    cand_a, cand_b = pair[0], pair[1]
    pct_a = parse_pct(cand_a.get("percentage"))
    pct_b = parse_pct(cand_b.get("percentage"))
    party_a = canon_party(cand_a.get("party", ""))
    party_b = canon_party(cand_b.get("party", ""))

    if party_a == winner_party:
        tpp_winner_pct, tpp_loser_pct = pct_a, pct_b
        tpp_opponent = party_b
    elif party_b == winner_party:
        tpp_winner_pct, tpp_loser_pct = pct_b, pct_a
        tpp_opponent = party_a
    else:
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
        "basis": marker_kind.upper(),
    }
    if swing is not None:
        out["swing"] = swing
    return out


def main() -> int:
    html = INPUT.read_text(encoding="utf-8")
    members = json.loads(MEMBERS.read_text(encoding="utf-8"))
    district_keys = list(members["districts"].keys())

    results: dict = {}
    errors: list = []
    missing_in_2018: list = []

    for key in district_keys:
        display = display_name_from_key(key)
        anchor = display.replace(" ", "_")
        if f'id="{anchor}"' not in html:
            # District did not exist in 2018 (created in 2021 redistribution).
            results[key] = None
            missing_in_2018.append(key)
            continue
        try:
            data = extract_district_data_mw(html, anchor)
            entry = process_district(display, data)
            results[key] = entry
        except Exception as e:  # noqa: BLE001
            errors.append((key, str(e)))
            results[key] = None

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")

    captured = sum(1 for v in results.values() if v is not None)
    null_count = sum(1 for v in results.values() if v is None)
    print(f"Captured {captured} / {len(district_keys)} districts")
    print(f"Null (not in 2018): {null_count}")
    if missing_in_2018:
        print("  Null districts:", ", ".join(missing_in_2018))
    if errors:
        print("Errors:")
        for d, e in errors:
            print(f"  - {d}: {e}")

    print("\nSample entries:")
    for k in ("RICHMOND", "BRUNSWICK", "MELBOURNE", "ALBERT PARK", "HAWTHORN"):
        if k in results:
            print(f"  {k}: {results[k]}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
