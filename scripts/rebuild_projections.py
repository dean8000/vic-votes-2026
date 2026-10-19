#!/usr/bin/env python3
"""Rebuild /Users/dean/Dev/vote/assets/data/projections.json from the current
polling aggregate + 2022 margins. Uniform-swing model; see projections.html for
the methodology explanation shown to users.
"""
import json
from datetime import date
from pathlib import Path

ROOT = Path("/Users/dean/Dev/vote/assets/data")
POLL = ROOT / "polling.json"
MARG = ROOT / "margins.json"
OUT = ROOT / "projections.json"

poll = json.load(POLL.open())
margins = json.load(MARG.open())
swing = poll["aggregate"]["tpp_swing_from_2022"]
if swing is None:
    raise SystemExit("polling.json aggregate has no swing — cannot build projections")


def is_coalition(party):
    return party in {"Liberal", "National", "Coalition"}


projections = {}
flips = {"to_coalition": [], "to_labor": [], "in_play": []}
for district, data in margins.items():
    winner = data["winner"]
    opponent = data["tpp_opponent"]
    basis = data["basis"]
    winner_pct = data["tpp_winner_pct"]
    is_lab_v_coal = (
        (winner == "Labor" and is_coalition(opponent))
        or (is_coalition(winner) and opponent == "Labor")
    )
    if not is_lab_v_coal:
        projections[district] = {
            "projected_labor_tpp": None,
            "projected_winner": winner,
            "sitting_winner": winner,
            "status": "non-two-party",
            "note": f"2022 was {winner} vs {opponent} ({basis}); a statewide Labor-vs-Coalition swing doesn't tell us anything useful here.",
        }
        continue
    labor_2022 = winner_pct if winner == "Labor" else (100 - winner_pct)
    labor_2026 = labor_2022 + swing
    projected_winner = "Labor" if labor_2026 > 50 else "Coalition"
    margin_2026 = abs(labor_2026 - 50)
    sitting_bloc = "Labor" if winner == "Labor" else "Coalition"
    if projected_winner != sitting_bloc:
        status = "likely flip"
        if projected_winner == "Coalition":
            flips["to_coalition"].append(district)
        else:
            flips["to_labor"].append(district)
    elif margin_2026 < 2:
        status = "in play"
        flips["in_play"].append(district)
    elif margin_2026 < 5:
        status = "close hold"
    else:
        status = "safe hold"
    projections[district] = {
        "labor_2022_tpp": round(labor_2022, 1),
        "projected_labor_tpp": round(labor_2026, 1),
        "projected_winner": projected_winner,
        "sitting_winner": sitting_bloc,
        "sitting_winner_actual": winner,
        "status": status,
    }

json.dump({
    "basis": f"Uniform swing of {swing:+.1f}% (from current polling average) applied to each district's 2022 Labor TPP. Only applies to Labor-vs-Coalition contests; Greens- and Independent-held seats are marked non-two-party.",
    "warning": "Uniform-swing projection is simplistic — ignores regional variation, high-profile independents, local candidate quality, and preference-flow shifts (notably One Nation's unusual Victorian polling in 2026).",
    "aggregate_swing": swing,
    "as_of": date.today().isoformat(),
    "sources": {
        "2022_margins": "https://en.wikipedia.org/wiki/Results_of_the_2022_Victorian_state_election_(Legislative_Assembly)",
        "polling": "https://en.wikipedia.org/wiki/Opinion_polling_for_the_2026_Victorian_state_election",
    },
    "projections": projections,
    "summary": {
        "flips_to_coalition": len(flips["to_coalition"]),
        "flips_to_labor": len(flips["to_labor"]),
        "in_play": len(flips["in_play"]),
    },
}, OUT.open("w"), indent=2, ensure_ascii=False)
print(f"wrote {OUT}: swing {swing:+.1f}%, {len(flips['to_coalition'])} flips to Coalition, {len(flips['in_play'])} in play")
