#!/usr/bin/env python3
"""Write /Users/dean/Dev/vote/assets/data/last-refresh.json with a snapshot
summary — read by the shared footer on every page to show 'what's new'."""
import json
from datetime import date, timezone
from pathlib import Path

ROOT = Path("/Users/dean/Dev/vote/assets/data")

polling = json.load((ROOT / "polling.json").open())
candidates = json.load((ROOT / "candidates.json").open())
members = json.load((ROOT / "members.json").open())
bios = json.load((ROOT / "bios.json").open())
projections = json.load((ROOT / "projections.json").open())

n_polls = len(polling.get("polls", []))
n_districts_with_cands = sum(1 for d in candidates.get("districts", {}).values()
                             if d.get("candidates"))
cand_names = set()
for d in candidates.get("districts", {}).values():
    for c in d.get("candidates", []):
        cand_names.add(c["name"])
for r in candidates.get("regions", {}).values():
    for c in r.get("candidates", []):
        cand_names.add(c["name"])
for d in members.get("districts", {}).values():
    cand_names.add(d.get("mp", ""))
for r in members.get("regions", {}).values():
    for m in r:
        cand_names.add(m.get("mlc", ""))
n_candidates = len(cand_names)
n_with_bio = sum(1 for n in cand_names
                 if n in bios and (bios[n].get("wikipedia_url") or bios[n].get("summary")))

summary = {
    "refreshed_on": date.today().isoformat(),
    "polls_tracked": n_polls,
    "aggregate": polling.get("aggregate", {}),
    "candidates_total": n_candidates,
    "candidates_with_bio": n_with_bio,
    "projection_flips": projections.get("summary", {}).get("flips_to_coalition", 0)
                      + projections.get("summary", {}).get("flips_to_labor", 0),
    "projection_in_play": projections.get("summary", {}).get("in_play", 0),
}

out = ROOT / "last-refresh.json"
out.write_text(json.dumps(summary, indent=2))
print(f"wrote {out}: {n_polls} polls, {n_with_bio}/{n_candidates} candidates with bio")
