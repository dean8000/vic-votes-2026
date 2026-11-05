#!/usr/bin/env python3
"""Download the VEC's voting-venues spreadsheet, parse the EVCs (early voting
centres) sheet, and write it to assets/data/early-voting-centres.json keyed by
district (UPPER case) so the My area page can show relevant venues.

We only extract EVCs here (early voting centres). Election-day polling places
are a separate task if we ever want to include them.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path
from openpyxl import load_workbook

URL = "https://www.vec.vic.gov.au/-/media/19326aa361284a49a69b08194421da96.xlsx"
OUT = Path("/Users/dean/Dev/vote/assets/data/early-voting-centres.json")
USER_AGENT = "VoteVicEVCScraper/1.0 (dean@lumir.vc; civic-info non-commercial)"

ACCESS = {
    "AWA": "Assisted wheelchair access",
    "IWA": "Independent wheelchair access",
    "NWA": "No wheelchair access",
    "IWBO": "Independent wheelchair boarding only",
}


def main() -> int:
    req = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    tmp = Path("/tmp/vec_venues.xlsx")
    tmp.write_bytes(data)
    wb = load_workbook(tmp, data_only=True)
    if "EVCs" not in wb.sheetnames:
        print("no EVCs sheet found", file=sys.stderr)
        return 1
    ws = wb["EVCs"]
    header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    want = {
        "District": "district_label",
        "Voting Location Name": "name",
        "Venue Name": "venue",
        "Accessibility": "accessibility",
        "Address Line 1": "address1",
        "Address Line 2": "address2",
        "Suburb": "suburb",
        "Post Code": "postcode",
        "Est. Early Votes": "est_votes",
    }
    cols = {h: i for i, h in enumerate(header) if h in want}
    by_district = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[cols["District"]] is None:
            continue
        label = str(row[cols["District"]]).strip()
        # "Albert Park District" -> "ALBERT PARK"
        key = re.sub(r"\s+District$", "", label, flags=re.I).upper()
        entry = {
            want[h]: row[i] for h, i in cols.items()
        }
        acc = entry.get("accessibility")
        entry["accessibility_label"] = ACCESS.get(acc, acc) if acc else None
        # Build an address string for display + geocoding
        addr_parts = [entry.get("address1"), entry.get("address2"), entry.get("suburb")]
        addr = ", ".join(str(p) for p in addr_parts if p)
        if entry.get("postcode"):
            addr += " " + str(entry["postcode"])
        entry["address_full"] = addr.strip(", ")
        by_district.setdefault(key, []).append(entry)

    # Sort each district's list by estimated votes (busiest first)
    for v in by_district.values():
        v.sort(key=lambda x: -(x.get("est_votes") or 0))

    out = {
        "source": "Victorian Electoral Commission — 2026 state election voting venues spreadsheet",
        "source_url": "https://www.vec.vic.gov.au/voting/2026-state-election/voting-locations",
        "early_voting_opens": "2026-11-18",
        "early_voting_closes": "2026-11-27",
        "hours": "8am to 6pm, Wednesday 18 Nov to Friday 27 Nov",
        "districts": by_district,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    total = sum(len(v) for v in by_district.values())
    print(f"wrote {OUT}: {total} early voting centres across {len(by_district)} districts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
