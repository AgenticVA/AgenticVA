#!/usr/bin/env python3
"""
Build website/data/paper_data.json from website/csv/*.csv and website/bibs/*.bib.

  python3 scripts/generate_paper_data.py

Uses only the Python standard library (no pip install).

Backup: existing paper_data.json is copied to paper_data_old.json (overwritten).
Also reads website/data/systems.json for URL fallbacks when needed.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from pathlib import Path

WEBSITE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = WEBSITE_ROOT / "data"
CSV_DIR = WEBSITE_ROOT / "csv"
BIB_DIR = WEBSITE_ROOT / "bibs"

SYSTEMS_CSV = CSV_DIR / "paper-list-systems.csv"
DATASET_CSV = CSV_DIR / "paper-list-dataset.csv"
OUT_JSON = DATA_DIR / "paper_data.json"
OLD_JSON = DATA_DIR / "paper_data_old.json"
SYSTEMS_JSON = DATA_DIR / "systems.json"

WORKFLOW_COLUMNS = [
    "data_profiling",
    "data_integration",
    "data_transformation",
    "spacial_substrate",
    "graphical_elements",
    "graphical_properties",
    "spacial_navigation",
    "hierarchy_drilling",
    "multi_view",
    "annotation",
    "summarization",
    "storytelling",
]

ROLE_MAP = [
    ("planner", "planner"),
    ("creator", "creator"),
    ("critic", "reviewer"),
    ("context_manager", "context_manager"),
]


def strip_bib_latex(s: str) -> str:
    if not s:
        return ""
    # Common BibTeX LaTeX escapes that should render as plain text.
    t = s.replace(r"\textasciicircum", "^")
    t = t.replace(r"\^{}", "^").replace(r"\^", "^")
    t = re.sub(r"\{\{([^}]*)\}\}", r"\1", t)
    t = re.sub(r"\{([^}]*)\}", r"\1", t)
    t = re.sub(r"[{}]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _parse_bib_value(text: str, start: int) -> tuple[str, int]:
    n = len(text)
    while start < n and text[start] in " \t\n\r":
        start += 1
    if start >= n:
        return "", start
    if text[start] == "{":
        depth = 0
        j = start
        while j < n:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    return text[start + 1 : j], j + 1
            j += 1
        return text[start + 1 : j], j
    if text[start] == '"':
        end = text.find('"', start + 1)
        if end < 0:
            return text[start + 1 :], n
        return text[start + 1 : end], end + 1
    j = start
    while j < n and text[j] not in ",\n}":
        j += 1
    return text[start:j].strip(), j


def parse_bib_file(path: Path) -> dict[str, dict[str, str]]:
    """Map citation key -> lowercase field dict."""
    text = path.read_text(encoding="utf-8", errors="replace")
    entries: dict[str, dict[str, str]] = {}
    pos = 0
    while True:
        m = re.search(r"@\w+\s*\{", text[pos:])
        if not m:
            break
        body_start = pos + m.end()
        depth = 1
        j = body_start
        while j < len(text) and depth:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[body_start : j - 1]
        pos = j

        comma = body.find(",")
        if comma < 0:
            continue
        key = body[:comma].strip()
        rest = body[comma + 1 :]
        fields: dict[str, str] = {}
        i = 0
        rlen = len(rest)
        while i < rlen:
            fm = re.match(r"\s*(\w+)\s*=\s*", rest[i:])
            if not fm:
                i += 1
                continue
            fname = fm.group(1).lower()
            i += fm.end()
            val, ni = _parse_bib_value(rest, i)
            fields[fname] = val
            i = ni
            while i < rlen and rest[i] in " \t\n\r,":
                i += 1
        entries[key] = fields
    return entries


def load_bib_database() -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for bib_path in sorted(BIB_DIR.glob("*.bib")):
        for k, v in parse_bib_file(bib_path).items():
            if k not in merged:
                merged[k] = v
    return merged


def load_systems_links() -> dict[str, str]:
    if not SYSTEMS_JSON.is_file():
        return {}
    with open(SYSTEMS_JSON, encoding="utf-8") as f:
        rows = json.load(f)
    out: dict[str, str] = {}
    for row in rows:
        rid = row.get("id")
        link = (row.get("link") or "").strip()
        if rid and link:
            out[rid] = link
    return out


def resolve_bib_key(cite: str, bib: dict[str, dict]) -> str | None:
    if cite in bib:
        return cite
    return None


def entry_url(fld: dict | None) -> str:
    if not fld:
        return "#"
    u = fld.get("url", "").strip()
    if u:
        return u
    doi = fld.get("doi", "").strip()
    if doi:
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
        return f"https://doi.org/{doi}"
    return "#"


def entry_year(fld: dict | None, fallback: int | None) -> int:
    if fallback is not None:
        return int(fallback)
    if not fld:
        return 0
    for key in ("year", "date"):
        v = fld.get(key, "")
        if not v:
            continue
        m = re.search(r"(19|20)\d{2}", str(v))
        if m:
            return int(m.group(0))
    return 0


def full_title_for_record(fld: dict | None, papername: str) -> str:
    """Prefer BibTeX title; strip braces; fall back to CSV short name."""
    if fld:
        t = strip_bib_latex(fld.get("title", "") or "")
        if t:
            return t
    return papername


def short_title_for_record(fld: dict | None, papername: str) -> str:
    """Prefer BibTeX shorttitle; fall back to CSV paper name."""
    if fld:
        t = strip_bib_latex(fld.get("shorttitle", "") or "")
        if t:
            return t
    return papername


def abstract_for_record(fld: dict | None) -> str:
    if not fld:
        return ""
    return strip_bib_latex(fld.get("abstract", "") or "")


def warn_unmapped_shorttitle(papername: str, source: str) -> None:
    print(
        f"[WARN] No BibTeX shorttitle match for '{papername}' ({source})",
        file=sys.stderr,
    )


def venue_from_fields(fld: dict | None) -> str:
    if not fld:
        return "Unknown"
    sj = strip_bib_latex(fld.get("shortjournal", "") or "")
    if sj:
        return sj[:24]
    blob = " ".join(
        strip_bib_latex(fld.get(k, "") or "")
        for k in ("journal", "journaltitle", "booktitle", "eventtitle")
    ).upper()
    checks = [
        ("TVCG", "TVCG"),
        ("IEEE TRANSACTIONS ON VISUALIZATION AND COMPUTER GRAPHICS", "TVCG"),
        ("EUROVIS", "EuroVis"),
        ("SIGMOD", "SIGMOD"),
        ("MANAGEMENT OF DATA", "SIGMOD"),
        ("HUMAN FACTORS IN COMPUTING SYSTEMS", "CHI"),
        ("ACM CHI", "CHI"),
        ("COMPUTATIONAL LINGUISTICS", "ACL"),
        ("NAACL", "NAACL"),
        ("ASSOCIATION FOR COMPUTATIONAL LINGUISTICS", "ACL"),
        ("EMNLP", "EMNLP"),
        ("NEURIPS", "NeurIPS"),
        ("KDD", "KDD"),
        ("COLING", "COLING"),
        ("UIST", "UIST"),
        ("IEEE VIS", "VIS"),
        ("INFOVIS", "VIS"),
        ("CGF", "CGF"),
        ("COMPUTER GRAPHICS FORUM", "CGF"),
        ("ARXIV", "arXiv"),
    ]
    for needle, label in checks:
        if needle in blob:
            return label
    if "CHI" in blob:
        return "CHI"
    if "VISUALIZATION" in blob and "IEEE" in blob:
        return "VIS"
    return "Unknown"


def find_entry_by_shorttitle(paper_name: str, bib: dict[str, dict]) -> dict | None:
    target = norm_key(paper_name)
    if not target:
        return None
    # 1) Prefer exact normalized shorttitle match to avoid collisions like
    # "nvBench" incorrectly matching "Dial-nvBench".
    for fld in bib.values():
        shorttitle_raw = fld.get("shorttitle", "")
        shorttitle = norm_key(strip_bib_latex(shorttitle_raw))
        if shorttitle and shorttitle == target:
            return fld

    # 2) Fall back to fuzzy match when no exact shorttitle exists.
    best: dict | None = None
    best_score = -1
    for fld in bib.values():
        shorttitle_raw = fld.get("shorttitle", "")
        shorttitle = norm_key(strip_bib_latex(shorttitle_raw))
        if not shorttitle:
            continue
        score = -1
        if target in shorttitle:
            # Prefer tighter containment (smaller length gap).
            score = 1000 - abs(len(shorttitle) - len(target))
        elif len(target) >= 6 and shorttitle.startswith(target[:6]):
            # Prefix fallback is weaker than containment.
            score = 100
        if score > best_score:
            best = fld
            best_score = score
    return best


def csv_int(row: dict, key: str) -> int:
    v = row.get(key, "")
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return 0


def workflows_from_row(row: dict) -> list[str]:
    return [c for c in WORKFLOW_COLUMNS if csv_int(row, c) == 1]


def roles_from_row(row: dict) -> list[str]:
    return [site for csv_col, site in ROLE_MAP if csv_int(row, csv_col) == 1]


def level_from_category(cat: str) -> int | None:
    cat = (cat or "").strip().upper()
    if not cat:
        return None
    if cat.startswith("L"):
        try:
            return int(cat[1:])
        except ValueError:
            return None
    return None


def read_systems_rows() -> list[dict]:
    with open(SYSTEMS_CSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def dataset_features_from_row(row: list[str]) -> dict[str, str]:
    def col(i: int) -> str:
        return str(row[i]).strip() if len(row) > i else ""

    return {
        "text_query_input": col(3),
        "chart_image_input": col(4),
        "other_input": col(5),
        "nl_num": col(6),
        "chart_num": col(7),
        "source": col(8),
        "generation_order": col(9),
        "generation_method": col(10),
        "annotation": col(11),
    }


def read_dataset_rows() -> list[tuple[str, str, int | None, dict[str, str]]]:
    rows: list[tuple[str, str, int | None, dict[str, str]]] = []
    with open(DATASET_CSV, encoding="utf-8", newline="") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if not row or not str(row[0]).strip():
                continue
            paper = str(row[0]).strip()
            venue = str(row[1]).strip() if len(row) > 1 else ""
            y_raw = str(row[2]).strip() if len(row) > 2 else ""
            year = int(y_raw) if y_raw.isdigit() else None
            features = dataset_features_from_row(row)
            rows.append((paper, venue, year, features))
    return rows


def merge_dataset_into_records(
    records: list[dict],
    dataset_rows: list[tuple[str, str, int | None, dict[str, str]]],
    bib: dict[str, dict[str, str]],
) -> None:
    index_by_norm: dict[str, int] = {}
    for i, rec in enumerate(records):
        index_by_norm[norm_key(rec["papername"])] = i

    for paper, d_venue, d_year, d_features in dataset_rows:
        nk = norm_key(paper)
        if nk in index_by_norm:
            rec = records[index_by_norm[nk]]
            rec["dataset"] = True
            rec["dataset_features"] = d_features
            if d_venue and rec.get("venue") == "Unknown":
                rec["venue"] = d_venue
            be_merge = find_entry_by_shorttitle(paper, bib) or find_entry_by_shorttitle(
                rec["papername"], bib
            )
            if be_merge:
                rec["fulltitle"] = full_title_for_record(be_merge, rec["papername"])
                rec["shorttitle"] = short_title_for_record(
                    be_merge, rec["papername"]
                )
                rec["abstract"] = abstract_for_record(be_merge)
            else:
                warn_unmapped_shorttitle(paper, "dataset csv existing record")
            continue

        be = find_entry_by_shorttitle(paper, bib)
        if be is None:
            warn_unmapped_shorttitle(paper, "dataset csv new record")
        url = entry_url(be)
        venue = d_venue or venue_from_fields(be)
        year = d_year if d_year is not None else entry_year(be, None)
        if year == 0 and be:
            year = entry_year(be, None)
        if year == 0:
            year = 2024

        records.append(
            {
                "papername": paper,
                "fulltitle": full_title_for_record(be, paper),
                "shorttitle": short_title_for_record(be, paper),
                "venue": venue,
                "year": year,
                "level": None,
                "system": False,
                "dataset": True,
                "dataset_features": d_features,
                "roles": [],
                "workflows": [],
                "abstract": abstract_for_record(be),
                "url": url,
            }
        )


def main() -> None:
    if not SYSTEMS_CSV.is_file():
        print(f"Missing {SYSTEMS_CSV}", file=sys.stderr)
        sys.exit(1)

    bib = load_bib_database()
    systems_links = load_systems_links()

    if OUT_JSON.is_file():
        shutil.copyfile(OUT_JSON, OLD_JSON)
        print(f"Backed up -> {OLD_JSON.name}", file=sys.stderr)

    records: list[dict] = []
    for row in read_systems_rows():
        cite = (row.get("papercite") or "").strip()
        papername = (row.get("papername") or "").strip() or cite
        year_csv = csv_int(row, "year")
        level = level_from_category(row.get("category", ""))

        bkey = resolve_bib_key(cite, bib) if cite else None
        fld = bib.get(bkey) if bkey else None
        if fld is None:
            fld = find_entry_by_shorttitle(papername, bib)
        if fld is None:
            warn_unmapped_shorttitle(papername, "systems csv")

        url = entry_url(fld)
        if url == "#" and cite in systems_links:
            url = systems_links[cite]

        venue = venue_from_fields(fld)
        year = year_csv if year_csv else entry_year(fld, None)

        records.append(
            {
                "papername": papername,
                "fulltitle": full_title_for_record(fld, papername),
                "shorttitle": short_title_for_record(fld, papername),
                "venue": venue,
                "year": year,
                "level": level,
                "system": True,
                "dataset": False,
                "dataset_features": {},
                "roles": roles_from_row(row),
                "workflows": workflows_from_row(row),
                "abstract": abstract_for_record(fld),
                "url": url,
            }
        )

    merge_dataset_into_records(records, read_dataset_rows(), bib)

    for i, rec in enumerate(records, start=1):
        rec["id"] = i

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {len(records)} entries -> {OUT_JSON.relative_to(WEBSITE_ROOT)}")


if __name__ == "__main__":
    main()
