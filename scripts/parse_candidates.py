#!/usr/bin/env python3
"""Parse Wikipedia 'Candidates of the 2026 Victorian state election' into JSON.

The LA table has a header row like:
  Electorate | [color] | Held by | [color] | Labor candidate | [color] |
  Coalition candidate | [color] | Greens candidate | [color] | One Nation candidate
  | [color] | Socialists candidate | Other candidates

Color-bar cells are empty <td>s. We read the header row to find which columns
carry candidate text; for each subsequent district row we align cells to party.

The LC table is per-region with candidate groups.
"""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

HTML_PATH = Path("/tmp/vic_candidates.html")
OUT_PATH = Path("/Users/dean/Dev/vote/assets/data/candidates.json")


def strip_tags(html):
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
    s.feed(html)
    return re.sub(r"\s+", " ", "".join(s.parts)).strip()


def section_slice(html, start_id, end_id):
    m = re.search(r'id="' + re.escape(start_id) + r'"', html)
    if not m:
        return ""
    start = m.end()
    if end_id:
        m2 = re.search(r'id="' + re.escape(end_id) + r'"', html[start:])
        return html[start:start + m2.start()] if m2 else html[start:]
    return html[start:]


def parse_table(table_html):
    """Rows with rowspan expansion."""
    rows_raw = re.findall(r"<tr\b[^>]*>(.*?)</tr>", table_html, re.I | re.S)
    out = []
    pending = {}
    for row_html in rows_raw:
        cells = re.findall(r"<(t[dh])\b([^>]*)>(.*?)</\1>", row_html, re.I | re.S)
        row = []
        col = 0
        ci = 0
        while True:
            if col in pending:
                remain, text = pending[col]
                row.append(text)
                if remain - 1 <= 0:
                    del pending[col]
                else:
                    pending[col] = (remain - 1, text)
                col += 1
                continue
            if ci >= len(cells):
                break
            _, attrs, content = cells[ci]
            ci += 1
            rs = int(re.search(r'rowspan\s*=\s*"?(\d+)"?', attrs, re.I).group(1)) if re.search(r'rowspan\s*=\s*"?(\d+)"?', attrs, re.I) else 1
            cs = int(re.search(r'colspan\s*=\s*"?(\d+)"?', attrs, re.I).group(1)) if re.search(r'colspan\s*=\s*"?(\d+)"?', attrs, re.I) else 1
            text = strip_tags(content)
            for _ in range(cs):
                if rs > 1:
                    pending[col] = (rs - 1, text)
                row.append(text)
                col += 1
        if row:
            out.append(row)
    return out


DISTRICT_SET = {
    "Albert Park", "Ashwood", "Bass", "Bayswater", "Bellarine", "Benambra", "Bendigo East",
    "Bendigo West", "Bentleigh", "Berwick", "Box Hill", "Brighton", "Broadmeadows", "Brunswick",
    "Bulleen", "Bundoora", "Carrum", "Caulfield", "Clarinda", "Cranbourne", "Croydon",
    "Dandenong", "Eildon", "Eltham", "Essendon", "Eureka", "Euroa", "Evelyn", "Footscray",
    "Frankston", "Geelong", "Gippsland East", "Gippsland South", "Glen Waverley", "Greenvale",
    "Hastings", "Hawthorn", "Ivanhoe", "Kalkallo", "Kew", "Kororoit", "Lara", "Laverton", "Lowan",
    "Macedon", "Malvern", "Melbourne", "Melton", "Mildura", "Mill Park", "Monbulk", "Mordialloc",
    "Mornington", "Morwell", "Mulgrave", "Murray Plains", "Narracan", "Narre Warren North",
    "Narre Warren South", "Nepean", "Niddrie", "Northcote", "Oakleigh", "Ovens Valley",
    "Pakenham", "Pascoe Vale", "Point Cook", "Polwarth", "Prahran", "Preston", "Richmond",
    "Ringwood", "Ripon", "Rowville", "Sandringham", "Shepparton", "South Barwon",
    "South-West Coast", "St Albans", "Sunbury", "Sydenham", "Tarneit", "Thomastown", "Warrandyte",
    "Wendouree", "Werribee", "Williamstown", "Yan Yean",
}


def parse_la(html):
    section = section_slice(html, "Legislative_Assembly", "Legislative_Council")
    tables = re.findall(r"<table\b[^>]*>.*?</table>", section, re.I | re.S)
    out = {}
    for table in tables:
        rows = parse_table(table)
        if not rows:
            continue
        # Header: find column -> party mapping from the first row
        header = rows[0]
        col_party = {}
        for i, cell in enumerate(header):
            t = cell.strip().lower()
            # strip trailing " candidate" / " candidates"
            tm = re.match(r"(.+?)\s*candidates?$", t)
            if tm:
                col_party[i] = tm.group(1).strip().title()
            elif t == "electorate":
                col_party[i] = "__district__"
            elif t == "held by":
                col_party[i] = "__held_by__"
        # Walk data rows
        for row in rows[1:]:
            district = None
            for i, cell in enumerate(row):
                if col_party.get(i) == "__district__":
                    district = cell.strip()
                    break
            if not district or district not in DISTRICT_SET:
                continue
            key = district.upper()
            entry = out.setdefault(key, {"label": district, "sitting_party": None, "candidates": []})
            for i, cell in enumerate(row):
                party = col_party.get(i)
                if not party or party.startswith("__") or not cell.strip():
                    continue
                # cell may contain multiple candidates in "Other candidates" column
                if party.lower().startswith("other"):
                    for piece in split_other_candidates(cell):
                        name, p = extract_name_party(piece, default_party="Independent")
                        entry["candidates"].append({"name": name, "party": p})
                else:
                    name, p = extract_name_party(cell, default_party=party)
                    if name:
                        entry["candidates"].append({"name": name, "party": p})
            for i, cell in enumerate(row):
                if col_party.get(i) == "__held_by__" and cell.strip():
                    entry["sitting_party"] = cell.strip()
    return out


PARTY_ABBREV = {
    "L": "Liberal", "LIB": "Liberal", "N": "National", "NAT": "National",
    "G": "Greens", "GRN": "Greens", "LAB": "Labor", "ALP": "Labor",
    "Ind": "Independent", "I": "Independent", "IND": "Independent",
    "AJP": "Animal Justice", "FF": "Family First", "ON": "One Nation",
    "LCV": "Legalise Cannabis", "LC": "Legalise Cannabis",
    "DLP": "Democratic Labour", "SFF": "Shooters, Fishers and Farmers",
    "VS": "Victorian Socialists", "LDP": "Libertarian", "LIBT": "Libertarian",
    "SA": "Sustainable Australia", "FRE": "Freedom",
}


def extract_name_party(text, default_party):
    text = text.strip()
    # "Name (ABBR)" — party in parens
    m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", text)
    if m:
        name, p = m.group(1).strip(), m.group(2).strip()
        return name, PARTY_ABBREV.get(p, p)
    # "Name Independent" / "Name Labor" — trailing party word with no parens
    m = re.match(r"^(.+?)\s+(Independent|Labor|Liberal|National|Greens)$", text)
    if m:
        return m.group(1).strip(), m.group(2)
    return text, default_party


def split_other_candidates(text):
    """Split cells like 'A (P1)B (P2)' or 'A (P1), B (P2)' into separate candidate strings."""
    # Split before an uppercase letter that follows a close-paren.
    parts = re.split(r"(?<=\))\s*(?=[A-Z])|\n|;", text)
    return [p.strip() for p in parts if p.strip()]


LC_REGION_ANCHORS = {
    "Eastern_Victoria": "Eastern Victoria",
    "North_Eastern_Metropolitan": "North-Eastern Metropolitan",
    "Northern_Metropolitan": "Northern Metropolitan",
    "Northern_Victoria": "Northern Victoria",
    "South_Eastern_Metropolitan": "South-Eastern Metropolitan",
    "Southern_Metropolitan": "Southern Metropolitan",
    "Western_Metropolitan": "Western Metropolitan",
    "Western_Victoria": "Western Victoria",
}


def parse_lc(html):
    section = section_slice(html, "Legislative_Council", "Resignations_and_disendorsements") or \
              section_slice(html, "Legislative_Council", "References")
    # Carve the LC section into per-region slices by h3 anchors.
    anchor_hits = [(m.start(), m.group(1)) for m in re.finditer(
        r'<h3\b[^>]*id="([^"]+)"', section) if m.group(1) in LC_REGION_ANCHORS]
    anchor_hits.append((len(section), None))
    out = {}
    for i in range(len(anchor_hits) - 1):
        start, anchor = anchor_hits[i]
        end = anchor_hits[i + 1][0]
        region_label = LC_REGION_ANCHORS[anchor]
        region_html = section[start:end]
        tm = re.search(r"<table\b[^>]*>.*?</table>", region_html, re.S)
        if not tm:
            out[region_label.upper()] = {"label": region_label + " Region", "candidates": []}
            continue
        candidates = parse_lc_table(tm.group(0))
        out[region_label.upper()] = {"label": region_label + " Region", "candidates": candidates}
    return out


def parse_lc_table(table_html):
    """LC region table: alternating header rows ('X candidates') + color-bar rows + data rows.
    Headers establish a column-index → party map that applies to subsequent data rows,
    until the next header row.
    """
    rows = parse_table(table_html)
    results = []
    col_party = {}  # column index -> party name, replaced each time we see a header row
    for row in rows:
        cleaned = [c.strip() for c in row]
        if not any(cleaned):
            continue
        # Junk-filter rows that are only style gunk from colour-bar cells
        if all((not c) or c.startswith('style=') or c.startswith('"') for c in cleaned):
            continue
        # Header row? Any cell ending in 'candidates'
        header_hits = [(i, c) for i, c in enumerate(cleaned)
                       if re.search(r"candidates?$", c.lower())]
        if header_hits:
            col_party = {}
            for i, c in header_hits:
                m = re.match(r"(.+?)\s*candidates?$", c, re.I)
                if m:
                    col_party[i] = m.group(1).strip()
            continue
        # Data row — align by absolute column index
        for i, cell in enumerate(cleaned):
            if not cell:
                continue
            # drop ref brackets, then split on multiple names ("A B C" where each is capitalised)
            name_text = re.sub(r"\s*\[\d+\]\s*", " ", cell).strip()
            if not name_text or re.match(r"^\d+$", name_text):
                continue
            # Split cells that contain multiple candidates by capitalised-word boundaries,
            # preserving "First Middle Last" and "O'Brien" / "de Vietri" etc.
            pieces = split_candidate_cell(name_text)
            party = col_party.get(i, "Unknown")
            for piece in pieces:
                nm, p = extract_name_party(piece, default_party=party)
                nm = nm.strip()
                if nm and len(nm) < 80:
                    results.append({"name": nm, "party": p})
    # Dedupe by (name, party)
    seen = set()
    dedup = []
    for c in results:
        k = (c["name"].lower(), c["party"].lower())
        if k in seen:
            continue
        seen.add(k)
        dedup.append(c)
    return dedup


def split_candidate_cell(text):
    """Split a cell that may contain multiple candidates concatenated with spaces.
    Heuristic: break before a capital letter that begins a plausible first-name token
    after we've already consumed a full "First Last" pair.
    """
    # Simple approach: find positions where a space precedes a capital letter and
    # the preceding token ends a surname (letter) rather than a word like "van", "de".
    # We'll split on " (?=[A-Z][a-z])" after we have at least 2 words.
    parts = []
    tokens = text.split()
    buf = []
    for tok in tokens:
        if buf and len(buf) >= 2 and re.match(r"^[A-Z][a-z]", tok) and \
           not re.match(r"^(van|de|den|der|la|le|du|di|al)$", buf[-1].lower()):
            # finalise current if the last token in buf also starts with a capital
            # (i.e. a surname); otherwise keep accumulating
            if re.match(r"^[A-Z]", buf[-1]) or buf[-1].endswith(")"):
                parts.append(" ".join(buf))
                buf = [tok]
                continue
        buf.append(tok)
    if buf:
        parts.append(" ".join(buf))
    return parts if parts else [text]


def main():
    html = HTML_PATH.read_text(encoding="utf-8", errors="replace")
    la = parse_la(html)
    lc = parse_lc(html)
    print(f"LA districts: {len(la)}/88")
    counts = [len(v["candidates"]) for v in la.values()]
    if counts:
        print(f"LA candidate counts: min={min(counts)} max={max(counts)} mean={sum(counts)/len(counts):.1f}")
    print(f"LC regions populated: {sum(1 for r in lc.values() if r['candidates'])}/8")
    OUT_PATH.write_text(json.dumps({
        "source": "Wikipedia: Candidates of the 2026 Victorian state election",
        "retrieved": "2026-10-15",
        "note": "Nominations officially close 9 November 2026 — this list is best-effort pre-close and will be incomplete. See VEC for the authoritative post-nomination candidate list.",
        "districts": la,
        "regions": lc,
    }, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
