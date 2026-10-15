#!/usr/bin/env python3
"""Scrape Wikipedia bios for every sitting member of Victoria's 60th Parliament.

Reads /Users/dean/Dev/vote/assets/data/members.json, resolves each name to a
Wikipedia article, extracts a few factual fields from the infobox + lead, and
writes /Users/dean/Dev/vote/assets/data/bios.json.

Non-partisan: facts only, no commentary. Fields left null when unsure.

Usable disambiguation suffixes we try, in order:
  <Name>
  <Name>_(Australian_politician)
  <Name>_(Victorian_politician)
  <Name>_(politician)
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

MEMBERS_PATH = Path("/Users/dean/Dev/vote/assets/data/members.json")
CANDIDATES_PATH = Path("/Users/dean/Dev/vote/assets/data/candidates.json")
OUT_PATH = Path("/Users/dean/Dev/vote/assets/data/bios.json")

USER_AGENT = (
    "VoteVicBioScraper/1.0 (dean@lumir.vc; civic-info non-commercial) "
    "python-urllib"
)

DISAMBIG_SUFFIXES = [
    "",
    " (Australian politician)",
    " (Victorian politician)",
    " (politician)",
]

# Manual overrides where auto resolution misses or is ambiguous.
# key = name as in members.json, value = Wikipedia title (spaces OK).
MANUAL_TITLES = {
    "Vacant": None,
    "John Lister": "John Lister (Victorian politician)",
    "Nina Taylor": "Nina Taylor",
    "Matt Fregon": "Matt Fregon",
    "Jackson Taylor": "Jackson Taylor",
    "Paul Hamer": "Paul Hamer",
    "Tim Bull": "Tim Bull",
    "Josh Bull": "Josh Bull",
    "Kim Wells": "Kim Wells (Victorian politician)",
    "Belinda Wilson": "Belinda Wilson",
    "Jess Wilson": "Jess Wilson",
    "Michael O'Brien": "Michael O'Brien (Victorian politician)",
    "Danny O'Brien": "Danny O'Brien (politician)",
    "David Davis": "David Davis (Australian politician)",
    "Martin Cameron": "Martin Cameron (Victorian politician)",
    "Danny Pearson": "Danny Pearson (politician)",
    "Shaun Leane": "Shaun Leane",
    "John Berger": "John Berger (politician)",
    "Michael Galea": "Michael Galea (politician)",
    "Gabrielle Williams": "Gabrielle Williams",
    "Rachel Payne": "Rachel Payne",
    "Nicole Werner": "Nicole Werner",
    "Richard Welch": "Richard Welch (Australian politician)",
    "Ben Carroll": "Ben Carroll",
    "Georgie Crozier": "Georgie Crozier",
    "Harriet Shing": "Harriet Shing",
    "Jacinta Allan": "Jacinta Allan",
    "Jaclyn Symes": "Jaclyn Symes",
    "Tom McIntosh": "Tom McIntosh (politician)",
    "Renee Heath": "Renee Heath",
    "Ryan Batchelor": "Ryan Batchelor",
    "Melissa Horne": "Melissa Horne",
    "Natalie Hutchins": "Natalie Hutchins",
    "Ellen Sandell": "Ellen Sandell",
    "Peter Walsh": "Peter Walsh (Victorian politician)",
    "Matthew Guy": "Matthew Guy",
    "John Pesutto": "John Pesutto",
    "Brad Battin": "Brad Battin",
    "Gabrielle de Vietri": "Gabrielle de Vietri",
    "Ingrid Stitt": "Ingrid Stitt",
    "Lily D'Ambrosio": "Lily D'Ambrosio",
    "Mary-Anne Thomas": "Mary-Anne Thomas",
    "Steve Dimopoulos": "Steve Dimopoulos",
    "Colin Brooks": "Colin Brooks (politician)",
    "Anthony Carbines": "Anthony Carbines",
    "Sonya Kilkenny": "Sonya Kilkenny",
    "Natalie Suleyman": "Natalie Suleyman",
    "Ros Spence": "Ros Spence",
    "Vicki Ward": "Vicki Ward",
    "Enver Erdogan": "Enver Erdogan",
    "Lizzie Blandthorn": "Lizzie Blandthorn",
    "Gayle Tierney": "Gayle Tierney",
    "Tim Richardson": "Tim Richardson (Australian politician)",
    "Will Fowles": "Will Fowles",
    "Darren Cheeseman": "Darren Cheeseman",
    "David Southwick": "David Southwick",
    "James Newbury": "James Newbury",
    "Cindy McLeish": "Cindy McLeish",
    "David Hodgett": "David Hodgett",
    "Bridget Vallence": "Bridget Vallence",
    "Richard Riordan": "Richard Riordan (Australian politician)",
    "Roma Britnell": "Roma Britnell",
    "Bill Tilley": "Bill Tilley",
    "Emma Kealy": "Emma Kealy",
    "Tim McCurdy": "Tim McCurdy",
    "Kim O'Keeffe": "Kim O'Keeffe",
    "Annabelle Cleeland": "Annabelle Cleeland",
    "Wayne Farnham": "Wayne Farnham",
    "Chris Crewther": "Chris Crewther",
    "Jade Benham": "Jade Benham",
    "Moira Deeming": "Moira Deeming",
    "David Limbrick": "David Limbrick",
    "Jeff Bourman": "Jeff Bourman",
    "David Ettershank": "David Ettershank",
    "Georgie Purcell": "Georgie Purcell",
    "Rikkie-Lee Tyrrell": "Rikkie-Lee Tyrrell",
    "Melina Bath": "Melina Bath",
    "Wendy Lovell": "Wendy Lovell",
    "Bev McArthur": "Bev McArthur",
    "Joe McCracken": "Joe McCracken",
    "Sarah Mansfield": "Sarah Mansfield",
    "Katherine Copsey": "Katherine Copsey",
    "Aiv Puglielli": "Aiv Puglielli",
    "Anasina Gray-Barberio": "Anasina Gray-Barberio",
    "Adem Somyurek": "Adem Somyurek",
    "Evan Mulholland": "Evan Mulholland",
    "Nick McGowan": "Nick McGowan",
    "Ann-Marie Hermans": "Ann-Marie Hermans",
    "Trung Luu": "Trung Luu",
    "Sheena Watt": "Sheena Watt",
    "Lee Tarlamis": "Lee Tarlamis",
    "Sonja Terpstra": "Sonja Terpstra",
    "Jacinta Ermacora": "Jacinta Ermacora",
    "Gaelle Broad": "Gaelle Broad",
}


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status != 200:
            return None, r.status
        data = r.read()
        return data.decode("utf-8", errors="replace"), 200


def title_to_url(title):
    # Wikipedia replaces spaces with underscores but keeps most punctuation.
    quoted = urllib.parse.quote(title.replace(" ", "_"), safe="_(),'-/")
    return f"https://en.wikipedia.org/wiki/{quoted}"


# ---------------- HTML parsing helpers ----------------

def strip_tags(html):
    """Collapse HTML to plain text, dropping <sup> (ref markers) and <style>."""
    class S(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self.skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in ("sup", "style", "script"):
                self.skip += 1
            if tag == "br":
                self.parts.append(" ")

        def handle_endtag(self, tag):
            if tag in ("sup", "style", "script") and self.skip > 0:
                self.skip -= 1

        def handle_data(self, d):
            if self.skip == 0:
                self.parts.append(d)
    s = S()
    try:
        s.feed(html)
    except Exception:
        pass
    text = "".join(s.parts)
    text = re.sub(r"\[[0-9a-zA-Z]+\]", "", text)  # footnote markers
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_infobox(html):
    """Return the raw HTML of the first infobox table on the page, if any."""
    # Look for <table class="infobox ..."> and capture to matching </table>.
    m = re.search(r'<table[^>]*class="[^"]*infobox[^"]*"[^>]*>', html, re.I)
    if not m:
        return None
    start = m.start()
    i = m.end()
    depth = 1
    while i < len(html) and depth > 0:
        nxt_open = html.find("<table", i)
        nxt_close = html.find("</table>", i)
        if nxt_close == -1:
            return None
        if nxt_open != -1 and nxt_open < nxt_close:
            depth += 1
            i = nxt_open + 6
        else:
            depth -= 1
            i = nxt_close + len("</table>")
    return html[start:i]


def parse_infobox_rows(infobox_html):
    """Yield (label, value_text, value_html) per data row of an infobox."""
    # Rows look like: <tr><th ...>Label</th><td ...>Value</td></tr>
    row_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
    for row in row_re.findall(infobox_html):
        th = re.search(r"<th[^>]*>(.*?)</th>", row, re.I | re.S)
        td = re.search(r"<td[^>]*>(.*?)</td>", row, re.I | re.S)
        if not th or not td:
            continue
        label = strip_tags(th.group(1)).strip().rstrip(":").lower()
        val_html = td.group(1)
        val_text = strip_tags(val_html).strip()
        yield label, val_text, val_html


# ---------------- Field extractors ----------------

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
DATE_RE = re.compile(
    rf"(\d{{1,2}}\s+({MONTHS})\s+\d{{4}}|({MONTHS})\s+\d{{1,2}},?\s+\d{{4}}|\d{{4}})"
)
YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")


def extract_born(rows_dict, infobox_html):
    v = rows_dict.get("born")
    if not v:
        return None
    # Strip "(age NN)" and parenthetical place-of-birth.
    v = re.sub(r"\(age [^)]+\)", "", v)
    v = v.strip()
    # Prefer "DD Month YYYY" or "Month DD, YYYY" if present.
    for pat in (
        rf"\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}}",
        rf"(?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}}",
    ):
        m = re.search(pat, v)
        if m:
            return m.group(0).strip()
    y = YEAR_RE.search(v)
    return y.group(0) if y else None


def extract_education(rows_dict_html):
    # rows_dict_html: dict label -> raw HTML.
    for key in ("alma mater", "education"):
        html_val = rows_dict_html.get(key)
        if not html_val:
            continue
        # <br/> and </li> are list separators we should preserve as "; ".
        tmp = re.sub(r"<br\s*/?>", "; ", html_val, flags=re.I)
        tmp = re.sub(r"</li\s*>", "; ", tmp, flags=re.I)
        v = strip_tags(tmp)
        v = re.sub(r"\s*;\s*", "; ", v).strip(" ,;")
        v = re.sub(r"\s+", " ", v)
        if v:
            return v
    return None


def extract_elected_since(infobox_html, lead_text):
    """Earliest year of entering Victorian Parliament (Assembly or Council).

    Strategy: look at infobox role-sections whose header mentions
    "Legislative Assembly", "Legislative Council", or "Member for ...". Collect
    all years appearing in each section's date cells; return the earliest.
    If no parliamentary section is found, fall back to the earliest year across
    all "In office" rows. If still nothing, scan the lead text.
    """
    years = []
    if infobox_html:
        header_re = re.compile(
            r'<th[^>]*class="[^"]*infobox-header[^"]*"[^>]*>(.*?)</th>',
            re.I | re.S,
        )
        headers = list(header_re.finditer(infobox_html))
        parl_sections = []
        all_sections = []
        for i, h in enumerate(headers):
            title = strip_tags(h.group(1)).strip().lower()
            start = h.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(infobox_html)
            chunk = infobox_html[start:end]
            all_sections.append((title, chunk))
            if (
                "legislative assembly" in title
                or "legislative council" in title
                or "member for " in title
                or title.startswith("member of the victorian")
            ):
                parl_sections.append(chunk)
        pool = parl_sections if parl_sections else [c for _, c in all_sections]
        for chunk in pool:
            # Only look at "In office" / "Assumed office" cells.
            for m in re.finditer(
                r"(?:In office|Assumed office)\s*(?:</[a-z]+>)?(.*?)</td>",
                chunk, re.I | re.S,
            ):
                for y in YEAR_RE.findall(m.group(1)):
                    years.append(int(y))
    if not years and lead_text:
        m = re.search(
            r"(?:elected|first elected)\s+(?:to [^.]{0,80}?)?(?:in\s+)?(\d{4})",
            lead_text, re.I,
        )
        if m:
            years.append(int(m.group(1)))
    if years:
        return min(years)
    return None


def rows_dict_items(rows_dict):
    # rows_dict stores last-seen value per label (string). We also kept HTML in
    # a parallel dict (rows_html). This helper just iterates as if label/text.
    for k, v in rows_dict.items():
        yield k, v, ""


def _clean_occ(s):
    s = re.split(r"[.;\n]", s)[0]
    s = s.strip().strip(",").strip()
    # Drop pure "politician" entries; we want pre-political career.
    if s.lower() in ("politician", "political", "member of parliament", "mp"):
        return None
    return s or None


def extract_prior_occupation(rows_dict, lead_text):
    for key in ("occupation", "profession"):
        v = (rows_dict.get(key) or "").strip()
        if v:
            cleaned = _clean_occ(v)
            if cleaned:
                return cleaned
    if lead_text:
        patterns = [
            r"[Bb]efore (?:entering politics|her election|his election|being elected)[^.]*?(?:was|worked as)\s+(?:a|an)?\s*([^.]+?)\.",
            r"[Pp]rior to (?:entering politics|her election|his election|being elected)[^.]*?(?:was|worked as)\s+(?:a|an)?\s*([^.]+?)\.",
            r"[Bb]efore (?:her|his) election[^.]*?(?:,\s*)?(?:was|worked as|she was|he was)\s+(?:a|an)?\s*([^.]+?)\.",
            r"[Ff]ormerly (?:a|an)\s+([^.,]+?)(?:[.,])",
            r"worked as\s+(?:a|an)\s+([^.,]+?)(?:[.,])",
        ]
        for p in patterns:
            m = re.search(p, lead_text)
            if m:
                cand = m.group(1).strip()
                cand = re.sub(r"\s+", " ", cand)
                # Trim trailing clauses after " and " that get too long.
                if len(cand) <= 120:
                    return cand
    return None


OFFICE_SKIP_TITLES = {
    "personal details", "member of", "member of parliament", "other offices held",
    "member", "political offices", "parliamentary offices",
}


def _parse_office_dates(block_html):
    """From a chunk following a role header, return a date string.

    Looks for <b>In office</b> or <b>Assumed office</b> patterns.
    """
    # Grab the first "In office" / "Assumed office" cell contents up to </td>.
    m = re.search(
        r"(?:In office|Assumed office)\s*</[a-z]+>(.*?)</td>",
        block_html, re.I | re.S
    )
    assumed = False
    text = ""
    if m:
        text = strip_tags(m.group(1)).strip()
    else:
        # Alternative wrapping: <span><b>In office</b></span><br/>...
        m2 = re.search(
            r"<b>\s*(In office|Assumed office)\s*</b>(.*?)</td>",
            block_html, re.I | re.S,
        )
        if m2:
            assumed = m2.group(1).lower().startswith("assumed")
            text = strip_tags(m2.group(2)).strip()
    if not text:
        # Fallback: nothing we can extract.
        return None
    text_norm = re.sub(r"\s*[–-]\s*", "–", text)
    years = YEAR_RE.findall(text_norm)
    # Detect open-ended ("present" / "Incumbent" / trailing dash) or single-date
    # (no dash at all → implies still in office).
    has_dash = "–" in text_norm
    open_ended = (
        bool(re.search(r"present|incumbent", text_norm, re.I))
        or text_norm.endswith("–")
        or (not has_dash)
    )
    if assumed and years:
        return f"since {years[0]}"
    if len(years) >= 2:
        return f"{years[0]}–{years[-1]}"
    if len(years) == 1:
        return f"since {years[0]}" if open_ended else years[0]
    return None


def extract_prior_roles(infobox_html, lead_text):
    """Pull up to ~3 notable office entries from the infobox.

    Infobox role headers are `<th class="infobox-header"...>Title</th>`.
    The following rows (until the next header or end-of-table) contain the
    office details, including an `In office` date range.
    """
    if not infobox_html:
        return None
    # Split the infobox into chunks by the role-header rows.
    header_re = re.compile(
        r'<th[^>]*class="[^"]*infobox-header[^"]*"[^>]*>(.*?)</th>',
        re.I | re.S,
    )
    headers = list(header_re.finditer(infobox_html))
    roles = []
    for i, h in enumerate(headers):
        title = strip_tags(h.group(1)).strip()
        title = re.sub(r"\s+", " ", title)
        if not title:
            continue
        low = title.lower()
        if low in OFFICE_SKIP_TITLES:
            continue
        # Grab chunk until next header or end.
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(infobox_html)
        chunk = infobox_html[start:end]
        date_str = _parse_office_dates(chunk)
        # Strip ordinal prefixes like "49th " to keep it tidy.
        title_clean = re.sub(r"^\d+(st|nd|rd|th)\s+", "", title)
        if date_str:
            roles.append(f"{title_clean} {date_str}")
        else:
            roles.append(title_clean)
    if not roles:
        return None
    # Dedup, preserve order.
    seen = set()
    unique = []
    for r in roles:
        k = r.lower()
        if k in seen:
            continue
        seen.add(k)
        unique.append(r)
    # Prioritise: ministerial / shadow / leadership / premier first, then
    # chamber-membership rows last (as backfill).
    def is_membership(role):
        rl = role.lower()
        return rl.startswith("member of") or rl.startswith("member for")
    primary = [r for r in unique if not is_membership(r)]
    secondary = [r for r in unique if is_membership(r)]
    out = primary + secondary
    return out[:3]


def extract_lead(html):
    """Return plain text of the first paragraph(s) of the article."""
    # Content body is inside <div class="mw-parser-output">. First real <p>.
    body_m = re.search(r'<div class="mw-parser-output">(.*)', html, re.S)
    if not body_m:
        return ""
    body = body_m.group(1)
    paras = re.findall(r"<p>(.*?)</p>", body[:60000], re.S)
    text_parts = []
    for p in paras[:3]:
        t = strip_tags(p)
        if t:
            text_parts.append(t)
    return " ".join(text_parts)


# ---------------- Page resolver ----------------

def resolve_and_fetch(name, manual_title):
    """Return (url, html) or (None, None)."""
    candidates = []
    if manual_title:
        candidates.append(manual_title)
    else:
        for suf in DISAMBIG_SUFFIXES:
            candidates.append(name + suf)
    tried = []
    for title in candidates:
        url = title_to_url(title)
        tried.append(url)
        try:
            html, status = fetch_html(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            # Transient; move on.
            continue
        except Exception:
            continue
        if not html:
            continue
        # Did Wikipedia redirect/match? Reject disambiguation pages.
        if 'class="disambigbox"' in html or 'disambiguation page' in html.lower()[:5000]:
            continue
        # Confirm it's actually about a Victorian politician: lead should
        # mention Victorian / Legislative. Soft check only.
        return url, html
    return None, None


# ---------------- Driver ----------------

def build_bio(name, manual_title):
    if name == "Vacant":
        return {
            "wikipedia_url": None,
            "born": None,
            "prior_occupation": None,
            "elected_since": None,
            "prior_roles": None,
            "education": None,
            "note": "Seat vacant",
        }
    url, html = resolve_and_fetch(name, manual_title)
    if not html:
        return {
            "wikipedia_url": None,
            "born": None,
            "prior_occupation": None,
            "elected_since": None,
            "prior_roles": None,
            "education": None,
        }
    infobox_html = extract_infobox(html) or ""
    rows = {}
    rows_html = {}
    for label, text, val_html in parse_infobox_rows(infobox_html):
        if label and text and label not in rows:
            rows[label] = text
            rows_html[label] = val_html
    lead = extract_lead(html)
    return {
        "wikipedia_url": url,
        "born": extract_born(rows, infobox_html),
        "prior_occupation": extract_prior_occupation(rows, lead),
        "elected_since": extract_elected_since(infobox_html, lead),
        "prior_roles": extract_prior_roles(infobox_html, lead),
        "education": extract_education(rows_html),
    }


def main():
    with open(MEMBERS_PATH) as f:
        members = json.load(f)
    names = []
    for d in members["districts"].values():
        names.append(d["mp"])
    for region in members["regions"].values():
        for m in region:
            names.append(m["mlc"])
    # Also pull every unique 2026 candidate name — many will be stubs.
    if CANDIDATES_PATH.exists():
        with open(CANDIDATES_PATH) as f:
            cand_data = json.load(f)
        for d in cand_data.get("districts", {}).values():
            for c in d.get("candidates", []):
                names.append(c["name"])
        for r in cand_data.get("regions", {}).values():
            for c in r.get("candidates", []):
                names.append(c["name"])
    # Preserve order, dedup.
    seen = set()
    ordered = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            ordered.append(n)

    # Load existing bios so re-runs can be incremental (keeps good data on
    # transient failures).
    existing = {}
    if OUT_PATH.exists():
        try:
            with open(OUT_PATH) as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    bios = {}
    captured = 0
    stubs = 0
    for i, name in enumerate(ordered, 1):
        manual = MANUAL_TITLES.get(name)
        print(f"[{i}/{len(ordered)}] {name}", file=sys.stderr, flush=True)
        try:
            bio = build_bio(name, manual)
        except Exception as e:
            print(f"  error: {e}", file=sys.stderr)
            bio = {
                "wikipedia_url": None,
                "born": None,
                "prior_occupation": None,
                "elected_since": None,
                "prior_roles": None,
                "education": None,
            }
        # If this run produced only a stub but we already had good data for the
        # person, keep the richer entry.
        if (not bio.get("wikipedia_url")) and name in existing and existing[name].get("wikipedia_url"):
            bio = existing[name]
        bios[name] = bio
        if bio.get("wikipedia_url"):
            captured += 1
        else:
            stubs += 1
        time.sleep(0.4)  # polite to Wikipedia

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(bios, f, indent=2, ensure_ascii=False)
    print(
        f"wrote {OUT_PATH}: {captured} captured, {stubs} stubs, "
        f"{len(bios)} total",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
