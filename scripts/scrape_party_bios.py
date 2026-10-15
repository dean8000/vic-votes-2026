#!/usr/bin/env python3
"""Enrich bios.json with bios for non-sitting 2026 Victorian election candidates.

Primary source: the ABC News election guide, which publishes a short bio per
candidate on each electorate's page (and links to that candidate's party /
personal website). The ABC data is non-partisan and comprehensive, so we rely
on it almost exclusively for non-sitting candidates.

For each electorate page https://www.abc.net.au/news/elections/vic/2026/guide/<code>
we extract candidate cards of the form:

    <div class="eg2-card">
      ...
      <span class="eg2-card-name">Theo Zographos</span>
      <span class="eg2-party-tag ...">Liberal</span>
      <a class="eg2-card-link" href="https://...">Website →</a>
      <p class="eg2-card-bio"><span>...bio...</span></p>
      ...

Rules (per the task brief):
  - Only enrich entries that lack a `wikipedia_url`. Never overwrite a
    Wikipedia-sourced bio.
  - Match names exactly to the keys in bios.json.
  - 0.5 s polite delay between ABC requests.
  - Infer `source` from the website domain the ABC links to:
        viclabor         -> Vic Labor
        vicliberal       -> Vic Liberals
        greens           -> Vic Greens
        nationalsvic     -> Vic Nationals
    Otherwise `source` = "ABC" and `source_url` = the ABC electorate page.

Writes merged output back to assets/data/bios.json.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BIOS_PATH = Path("/Users/dean/Dev/vote/assets/data/bios.json")
CANDIDATES_PATH = Path("/Users/dean/Dev/vote/assets/data/candidates.json")

ABC_BASE = "https://www.abc.net.au/news/elections/vic/2026/guide"

USER_AGENT = (
    "VoteVicBioScraper/1.0 (dean@lumir.vc; civic-info non-commercial) "
    "python-urllib"
)

# Short URL codes used by the ABC guide for each Assembly electorate.
# Pulled from the ABC candidates index. 88 districts.
ABC_DISTRICT_CODES = [
    "albe", "ashw", "bass", "bays", "bell", "bena", "beea", "bewe", "bent",
    "berw", "boxh", "broa", "brig", "brun", "bull", "bund", "carr", "caul",
    "clar", "croy", "cran", "dand", "eild", "elth", "esse", "eure", "euro",
    "evel", "foot", "fran", "geel", "giea", "giso", "glen", "gree", "hast",
    "hawt", "ivan", "kalk", "kew", "koro", "lara", "lave", "lowa", "mace",
    "malv", "melb", "melt", "mild", "mill", "monb", "mord", "morw", "morn",
    "mulg", "murr", "narr", "nano", "naso", "nepe", "nidd", "nort", "oakl",
    "oven", "pake", "pasc", "poin", "polw", "prah", "pres", "rich", "ring",
    "ripo", "rowv", "sand", "shep", "soba", "soco", "stal", "sunb", "syde",
    "tarn", "thom", "warr", "wend", "werr", "will", "yany",
]


# ---------------- HTTP ----------------

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status != 200:
                return None, r.status
            return r.read().decode("utf-8", errors="replace"), 200
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception as e:
        return None, str(e)


# ---------------- HTML helpers ----------------

def strip_tags(html):
    class S(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self.skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.skip += 1
            if tag == "br":
                self.parts.append(" ")

        def handle_endtag(self, tag):
            if tag in ("script", "style") and self.skip > 0:
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
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ABC card: well-formed <div class="eg2-card"> ... <p class="eg2-card-bio">
# We split on card boundaries, then grab name / party / link / bio.
CARD_SPLIT_RE = re.compile(r'<div class="eg2-card">', re.I)
NAME_RE = re.compile(r'<span class="eg2-card-name">([^<]+)</span>', re.I)
PARTY_RE = re.compile(
    r'<span class="eg2-party-tag[^"]*"[^>]*>([^<]+)</span>', re.I
)
LINK_RE = re.compile(
    r'<a class="eg2-card-link" href="([^"]+)"', re.I
)
BIO_RE = re.compile(
    r'<p class="eg2-card-bio">\s*<span>(.*?)</span>\s*</p>', re.I | re.S
)


def parse_abc_page(html, electorate_code):
    """Return list of dicts, one per candidate card."""
    chunks = CARD_SPLIT_RE.split(html)
    # First chunk is pre-cards boilerplate; skip.
    cards = []
    for chunk in chunks[1:]:
        # Chunk ends at the next card or at the end of the containing block;
        # we don't need an explicit end marker because our regexes stop at the
        # closing </span> / </p>.
        name_m = NAME_RE.search(chunk)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        party_m = PARTY_RE.search(chunk)
        party = party_m.group(1).strip() if party_m else None
        link_m = LINK_RE.search(chunk)
        link = link_m.group(1).strip() if link_m else None
        bio_m = BIO_RE.search(chunk)
        bio = None
        if bio_m:
            bio = strip_tags(bio_m.group(1)).strip()
        cards.append({
            "name": name,
            "party": party,
            "link": link,
            "bio": bio,
            "electorate_code": electorate_code,
        })
    return cards


# ---------------- Source attribution ----------------

PARTY_DOMAIN_SOURCE = [
    ("viclabor.org.au", "Vic Labor"),
    ("viclabor.com.au", "Vic Labor"),
    ("vicliberal.org.au", "Vic Liberals"),
    ("vic.liberal.org.au", "Vic Liberals"),
    ("greens.org.au", "Vic Greens"),
    ("nationalsvic.org.au", "Vic Nationals"),
    ("vic.nationals.org.au", "Vic Nationals"),
]


def source_for_link(link):
    """Return (source_label, source_url) tuple.

    If `link` matches a known party domain we attribute to that party page.
    Otherwise we attribute to ABC (which is the actual source of the bio text,
    regardless of which personal/campaign site the card links out to).
    """
    if link:
        low = link.lower()
        for dom, label in PARTY_DOMAIN_SOURCE:
            if dom in low:
                return label, link
    return "ABC", None


# ---------------- Occupation sniffer ----------------

OCC_HINTS = [
    (re.compile(r"\bworks as (?:a|an) ([a-z][a-z \-]+?)[.,]", re.I),),
    (re.compile(r"\bis (?:a|an) ([a-z][a-z \-]+?)(?:\.| who\b| with\b| and\b)", re.I),),
    (re.compile(r"\bformer ([a-z][a-z \-]+?)[.,]", re.I),),
]


def guess_occupation(bio):
    """Best-effort pull of a profession phrase from the first sentence.

    Deliberately conservative. The ABC bios are already short, so if the
    guess looks noisy we leave `prior_occupation` null and let the summary
    carry the information.
    """
    if not bio:
        return None
    first = re.split(r"(?<=[.!?])\s", bio, maxsplit=1)[0]
    for (pat,) in OCC_HINTS:
        m = pat.search(first)
        if not m:
            continue
        cand = m.group(1).strip().lower()
        cand = re.sub(r"\s+", " ", cand)
        # Skip obvious false positives.
        banned = {"former", "member", "candidate", "resident", "father",
                  "mother", "veteran", "graduate"}
        head = cand.split()[0]
        if head in banned:
            continue
        if 2 <= len(cand) <= 60:
            return cand
    return None


# ---------------- Name matching ----------------

def norm_name(n):
    """Normalise a name for fuzzy match: lowercase, strip punctuation."""
    n = n.lower()
    n = re.sub(r"[‘’ʼ]", "'", n)   # curly to straight apostrophes
    n = re.sub(r"[‐-―]", "-", n)        # various dashes to hyphen
    n = re.sub(r"\s+", " ", n).strip()
    return n


def build_name_index(bios):
    """Map normalised name -> canonical key in bios.json."""
    idx = {}
    for k in bios:
        idx[norm_name(k)] = k
    return idx


def resolve_name(scraped_name, name_index):
    key = name_index.get(norm_name(scraped_name))
    return key


# ---------------- Driver ----------------

def main():
    with open(BIOS_PATH) as f:
        bios = json.load(f)
    name_index = build_name_index(bios)

    total_cards = 0
    enriched = 0
    skipped_has_wiki = 0
    unmatched = []
    failed_urls = []
    source_counts = {}

    for i, code in enumerate(ABC_DISTRICT_CODES, 1):
        url = f"{ABC_BASE}/{code}"
        print(f"[{i}/{len(ABC_DISTRICT_CODES)}] {url}", file=sys.stderr,
              flush=True)
        html, status = fetch(url)
        if not html:
            print(f"  FAILED status={status}", file=sys.stderr)
            failed_urls.append((url, status))
            time.sleep(0.5)
            continue
        cards = parse_abc_page(html, code)
        total_cards += len(cards)
        for card in cards:
            key = resolve_name(card["name"], name_index)
            if not key:
                unmatched.append((card["name"], code))
                continue
            existing = bios[key]
            if existing.get("wikipedia_url"):
                skipped_has_wiki += 1
                continue
            if not card["bio"]:
                continue
            source_label, source_url = source_for_link(card["link"])
            if source_label == "ABC":
                source_url = url
            # Merge: keep existing non-null fields, add new ones.
            merged = dict(existing)
            merged.setdefault("wikipedia_url", None)
            merged.setdefault("born", None)
            merged.setdefault("elected_since", None)
            merged.setdefault("education", None)
            merged.setdefault("prior_roles", None)
            if not merged.get("prior_occupation"):
                merged["prior_occupation"] = guess_occupation(card["bio"])
            merged["summary"] = card["bio"]
            merged["source"] = source_label
            merged["source_url"] = source_url
            bios[key] = merged
            enriched += 1
            source_counts[source_label] = source_counts.get(source_label, 0) + 1
        time.sleep(0.5)

    with open(BIOS_PATH, "w") as f:
        json.dump(bios, f, indent=2, ensure_ascii=False)

    # ---- Report ----
    print("", file=sys.stderr)
    print(f"ABC pages fetched: {len(ABC_DISTRICT_CODES)}", file=sys.stderr)
    print(f"Failed URLs: {len(failed_urls)}", file=sys.stderr)
    for u, s in failed_urls[:20]:
        print(f"  {s}  {u}", file=sys.stderr)
    print(f"Total candidate cards parsed: {total_cards}", file=sys.stderr)
    print(f"Enriched: {enriched}", file=sys.stderr)
    print(f"Skipped (already have wiki_url): {skipped_has_wiki}", file=sys.stderr)
    print(f"Unmatched names: {len(unmatched)}", file=sys.stderr)
    for n, c in unmatched[:40]:
        print(f"  {c}: {n}", file=sys.stderr)
    print("Source breakdown:", file=sys.stderr)
    for lbl, n in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f"  {lbl}: {n}", file=sys.stderr)


if __name__ == "__main__":
    main()
