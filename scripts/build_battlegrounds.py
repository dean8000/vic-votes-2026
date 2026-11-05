#!/usr/bin/env python3
"""Pre-compute the battleground categories from current projections + margins.
Called by the daily refresh chain so the Battlegrounds page auto-updates."""
import json
from pathlib import Path

ROOT = Path("/Users/dean/Dev/vote/assets/data")

margins = json.load((ROOT / "margins.json").open())
members = json.load((ROOT / "members.json").open())
proj = json.load((ROOT / "projections.json").open())["projections"]
candidates = json.load((ROOT / "candidates.json").open())

# Known Greens-challenger seats (based on 2022 primary + ABC guide analysis).
# A short, deliberately conservative list — add to it as campaign develops.
GREENS_TARGETS = ["NORTHCOTE", "PASCOE VALE", "ALBERT PARK", "FOOTSCRAY", "PRESTON"]


def district_dict(key):
    mem = members["districts"].get(key, {})
    mg = margins.get(key, {})
    v = proj.get(key, {})
    cand = candidates.get("districts", {}).get(key, {}).get("candidates", [])
    return {
        "key": key,
        "label": mg.get("label") or key.title(),
        "mp": mem.get("mp"),
        "party": mem.get("party"),
        "retiring": bool(mem.get("retiring")),
        "margin_2022": mg.get("margin"),
        "safety_2022": mg.get("safety"),
        "basis_2022": mg.get("basis"),
        "projected_winner": v.get("projected_winner"),
        "projected_labor_tpp": v.get("projected_labor_tpp"),
        "status": v.get("status"),
        "note": v.get("note"),
        "candidate_count": len(cand),
    }


# 1. Tightest projected flips
flips = sorted(
    [
        (k, abs(v["projected_labor_tpp"] - 50))
        for k, v in proj.items()
        if v.get("status") == "likely flip" and v.get("projected_labor_tpp") is not None
    ],
    key=lambda x: x[1],
)[:12]

# 2. In-play
in_play = sorted(
    [
        (k, abs(v.get("projected_labor_tpp", 50) - 50))
        for k, v in proj.items()
        if v.get("status") == "in play"
    ],
    key=lambda x: x[1],
)

# 3. Non-two-party races
ntp = []
for k, v in proj.items():
    if v.get("status") == "non-two-party":
        mem = members["districts"].get(k, {})
        if mem.get("party") == "Greens":
            ntp.append((k, 0, "greens-hold"))
        elif "Independent" in (mem.get("party") or ""):
            ntp.append((k, 0, "ind-hold"))
for k in GREENS_TARGETS:
    mem = members["districts"].get(k, {})
    if mem.get("party") == "Labor":
        mg = margins.get(k, {})
        ntp.append((k, mg.get("margin") or 99, "greens-target"))
ntp.sort(key=lambda x: x[1])

# 4. Open contests (incumbent retiring)
retiring = sorted(
    [
        (k, (margins.get(k, {}).get("margin") or 99))
        for k, mem in members["districts"].items()
        if mem.get("retiring")
    ],
    key=lambda x: x[1],
)

out = {
    "generated_at": __import__("datetime").date.today().isoformat(),
    "categories": [
        {
            "id": "tightest_flips",
            "title": "Tightest projected flips",
            "blurb": "If the state-wide swing is even slightly smaller than polling suggests, these seats stay with their current party. Ordered by how narrow the projection is — the tighter the gap, the less certain the flip.",
            "districts": [district_dict(k) for k, _ in flips],
        },
        {
            "id": "in_play",
            "title": "True toss-ups (<2% projected margin)",
            "blurb": "Within normal polling error. Either side could win.",
            "districts": [district_dict(k) for k, _ in in_play],
        },
        {
            "id": "non_two_party",
            "title": "Non-Labor-vs-Coalition races to watch",
            "blurb": "Seats where the real contest isn't Labor vs Coalition — Greens-held seats, Independent-held seats, and Labor-held seats where a Greens challenger is competitive. Uniform swing doesn't apply here; the race depends on local dynamics and preference flows.",
            "districts": [district_dict(k) for k, *_ in ntp],
        },
        {
            "id": "open_contests",
            "title": "Open contests — sitting MP retiring",
            "blurb": "17 lower-house incumbents are retiring, including Premier Jacinta Allan (Bendigo East) and several ministers. Open seats historically swing more than those with an incumbent on the ballot.",
            "districts": [district_dict(k) for k, _ in retiring],
        },
    ],
}

(ROOT / "battlegrounds.json").write_text(json.dumps(out, indent=2))
print("wrote battlegrounds.json")
for cat in out["categories"]:
    print(f"  {cat['id']:20} {len(cat['districts'])} seats")
