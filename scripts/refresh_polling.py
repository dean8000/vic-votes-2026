#!/usr/bin/env python3
"""Scrape the Wikipedia polling tracker for the 2026 Victorian state election
and rebuild /Users/dean/Dev/vote/assets/data/polling.json.

Parses the wikitable listing of state-wide voting-intention polls. Extracts
pollster, date, sample size, primary vote %, and 2PP where present. Takes the
most recent 5 polls with a 2PP figure to compute the aggregate statewide swing.
"""
from __future__ import annotations
import json
import re
import sys
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

URL = "https://en.wikipedia.org/wiki/Opinion_polling_for_the_2026_Victorian_state_election"
OUT = Path("/Users/dean/Dev/vote/assets/data/polling.json")
LABOR_2022_TPP = 55.0  # Statewide Labor 2PP in 2022; swing is computed against this.

USER_AGENT = "VoteVicPollingScraper/1.0 (dean@lumir.vc; civic-info non-commercial)"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def strip_tags(html: str) -> str:
    class S(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self.skip = 0
        def handle_starttag(self, tag, attrs):
            if tag in ("sup", "style", "script"):
                self.skip += 1
        def handle_endtag(self, tag):
            if tag in ("sup", "style", "script") and self.skip:
                self.skip -= 1
        def handle_data(self, d):
            if not self.skip:
                self.parts.append(d)
    s = S()
    try:
        s.feed(html)
    except Exception:
        pass
    text = "".join(s.parts)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


DEFAULT_YEAR = "2026"

def parse_date(s: str) -> str | None:
    """Convert Wikipedia date formats to ISO. Returns the END date for ranges.
    If the string has no year, assume DEFAULT_YEAR (polls listed in the 2026
    election table that use '6-10 Oct' style)."""
    s = s.strip()
    # "6-10 October 2026" or "2-8 Oct 2026"
    m = re.match(r"(\d+)[–\-—](\d+)\s+([A-Za-z]+)\s+(\d{4})", s)
    if m:
        return _iso(m.group(2), m.group(3), m.group(4))
    # "6-10 Oct" (no year)
    m = re.match(r"(\d+)[–\-—](\d+)\s+([A-Za-z]+)\s*$", s)
    if m:
        return _iso(m.group(2), m.group(3), DEFAULT_YEAR)
    # "31 July-3 August 2026"
    m = re.match(r"\d+\s+([A-Za-z]+)[–\-—](\d+)\s+([A-Za-z]+)\s+(\d{4})", s)
    if m:
        return _iso(m.group(2), m.group(3), m.group(4))
    # "31 Jul-3 Aug" (no year)
    m = re.match(r"\d+\s+([A-Za-z]+)[–\-—](\d+)\s+([A-Za-z]+)\s*$", s)
    if m:
        return _iso(m.group(2), m.group(3), DEFAULT_YEAR)
    # "10 October 2026" / "13 Sep 2026"
    m = re.match(r"(\d+)\s+([A-Za-z]+)\s+(\d{4})", s)
    if m:
        return _iso(m.group(1), m.group(2), m.group(3))
    # "10 Oct" (no year)
    m = re.match(r"(\d+)\s+([A-Za-z]+)\s*$", s)
    if m:
        return _iso(m.group(1), m.group(2), DEFAULT_YEAR)
    return None


MONTHS = {m[:3].lower(): i + 1 for i, m in enumerate(
    ["January","February","March","April","May","June","July","August","September","October","November","December"]
)}


def _iso(day: str, month: str, year: str) -> str | None:
    mkey = month[:3].lower()
    if mkey not in MONTHS:
        return None
    try:
        return f"{int(year):04d}-{MONTHS[mkey]:02d}-{int(day):02d}"
    except ValueError:
        return None


def parse_table_rows(table_html: str):
    rows_raw = re.findall(r"<tr\b[^>]*>(.*?)</tr>", table_html, re.I | re.S)
    out = []
    for row_html in rows_raw:
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html, re.I | re.S)
        out.append([strip_tags(c) for c in cells])
    return out


def to_pct(s: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def main() -> int:
    html = fetch(URL)
    # Pick the table with the most occurrences of known pollster names — the
    # main statewide voting-intention table. The longest table on the page is
    # usually a per-region breakdown, not this one.
    tables = re.findall(r"<table\b[^>]*>.*?</table>", html, re.I | re.S)
    if not tables:
        print("no tables found", file=sys.stderr)
        return 1
    KNOWN_POLLSTERS = ("Resolve", "RedBridge", "Freshwater", "DemosAU", "Roy Morgan",
                       "YouGov", "Essential", "Newspoll", "Morgan")
    def score(t: str) -> int:
        return sum(t.count(p) for p in KNOWN_POLLSTERS)
    best = max(tables, key=score)
    if score(best) < 3:
        print(f"could not find a plausible main poll table (best score {score(best)})", file=sys.stderr)
        return 1
    rows = parse_table_rows(best)
    if len(rows) < 2:
        print("poll table too small", file=sys.stderr)
        return 1

    # Column layouts observed in this table:
    #   12 cells: Date, Firm, Client, Sample, ALP, Coa, Grn, ONP, Oth, 2ppALP, 2ppCoa, 2ppONP
    #   13 cells: Date, Firm, Client, Sample, ALP, Coa, Grn, ONP, IND, Oth, 2ppALP, 2ppCoa, 2ppONP
    #   11 cells: no Others col (seen on some rows)
    #   fewer: row with no 2PP figures (just Date, Firm, Client, Sample, primaries, —)
    LAYOUTS = {
        13: ("date", "firm", "client", "sample", "alp_p", "coa_p", "grn_p", "on_p", "ind_p", "oth_p", "tpp_alp", "tpp_coa", "tpp_on"),
        12: ("date", "firm", "client", "sample", "alp_p", "coa_p", "grn_p", "on_p", "oth_p", "tpp_alp", "tpp_coa", "tpp_on"),
        11: ("date", "firm", "client", "sample", "alp_p", "coa_p", "grn_p", "on_p", "oth_p", "tpp_alp", "tpp_coa"),
         9: ("date", "firm", "client", "sample", "alp_p", "coa_p", "grn_p", "on_p", "oth_p"),
    }
    polls = []
    for r in rows[1:]:
        n = len(r)
        if n not in LAYOUTS:
            continue
        schema = LAYOUTS[n]
        col = dict(zip(schema, r))
        iso = parse_date(col.get("date", ""))
        if not iso:
            continue
        pollster = col.get("firm", "").strip()
        if not pollster or pollster.lower().startswith("style="):
            continue
        sample_n = re.sub(r"[^\d]", "", col.get("sample", "")) or None
        prim = {}
        for key, k in (("Labor", "alp_p"), ("Coalition", "coa_p"), ("Greens", "grn_p"),
                       ("One Nation", "on_p"), ("Independent", "ind_p"), ("Others", "oth_p")):
            v = to_pct(col.get(k, ""))
            if v is not None:
                prim[key] = v
        # Fold Independent into Others for display consistency
        if "Independent" in prim:
            prim["Others"] = round(prim.pop("Independent") + prim.get("Others", 0), 1)
        tpp_alp = to_pct(col.get("tpp_alp", ""))
        tpp_coa = to_pct(col.get("tpp_coa", ""))
        polls.append({
            "pollster": pollster,
            "date": iso,
            "sample": int(sample_n) if sample_n else None,
            "primary": prim,
            "tpp_labor": tpp_alp,
            "tpp_coalition": tpp_coa,
        })

    # Dedupe + sort newest first
    seen = set()
    dedup = []
    for p in sorted(polls, key=lambda x: x["date"], reverse=True):
        key = (p["pollster"], p["date"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(p)

    # Aggregate: most recent 5 polls with a 2PP figure
    with_tpp = [p for p in dedup if p["tpp_labor"] is not None][:5]
    if with_tpp:
        avg_labor = round(sum(p["tpp_labor"] for p in with_tpp) / len(with_tpp), 1)
        avg_coa = round(100 - avg_labor, 1)
        swing = round(avg_labor - LABOR_2022_TPP, 1)
        # Primary average across the same 5 polls
        prim_sum = {}
        prim_count = {}
        for p in with_tpp:
            for k, v in p["primary"].items():
                prim_sum[k] = prim_sum.get(k, 0.0) + v
                prim_count[k] = prim_count.get(k, 0) + 1
        prim_avg = {k: round(prim_sum[k] / prim_count[k], 1) for k in prim_sum}
    else:
        avg_labor = avg_coa = swing = None
        prim_avg = {}

    today = date.today().isoformat()
    out = {
        "source": "Wikipedia: Opinion polling for the 2026 Victorian state election",
        "retrieved": today,
        "note": "Aggregate is a simple average of the last 5 published 2PP polls. Not a weighted/house-adjusted model. See individual polls below.",
        "aggregate": {
            "as_of": today,
            "n_polls": len(with_tpp),
            "tpp_labor": avg_labor,
            "tpp_coalition": avg_coa,
            "tpp_swing_from_2022": swing,
            "primary": prim_avg,
        },
        "polls": dedup[:30],  # keep most recent 30
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {OUT}: {len(dedup)} polls, aggregate TPP ALP {avg_labor} / Coa {avg_coa}, swing {swing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
