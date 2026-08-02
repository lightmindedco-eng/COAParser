"""Build Firestore catalog records from COA Parser .txt outputs.

A faithful Python port of COAWeb's ``js/coa-parser.js`` plus the record
shape produced by ``js/admin.js``'s ``productDoc`` / ``buildSearchText``.
This lets Database Output publish to the Firestore catalog without
re-implementing parsing logic that could drift from the web tool.

The exact record/id hashing is replicated (including JS UTF-16 semantics)
so an automated publish writes to the same document ids with ``merge``
that the admin panel uses.
"""

from __future__ import annotations

import re

KNOWN_LABS = [
    "aerolabs",
    "baseline",
    "confident",
    "gateway",
    "greenleaf",
    "highres",
    "metis_qa",
    "sunrise",
    "unknown",
    "ocr_merge",
]

KNOWN_SECTIONS = ["cannabinoids", "terpenes", "detected analytes"]

EDIBLE_CATEGORIES = [
    "ingestible, baked goods",
    "ingestible, capsule",
    "ingestible, chocolate",
    "soft chew",
]

CONCENTRATE_CATEGORIES = [
    "bulk concentrate (weight based)",
    "bulk concentrate (weight-based)",
    "concentrates & extracts, crumble",
    "concentrates & extracts, diamonds",
    "concentrates & extracts, full extract cannabis oil",
    "concentrates & extracts, live resin, butane",
    "concentrates & extracts, live rosin",
    "concentrates & extracts, other",
    "concentrates & extracts, sugar wax, butane",
    "concentrates, solvent based concentrate",
]

PREROLL_CATEGORIES = [
    "plant, preroll",
    "plant, raw preroll",
]

INFUSED_PREROLL_CATEGORIES = [
    "infused non-edible, infused pre-roll",
    "plant, enhanced/infused preroll",
    "preroll (infused)",
    "pre-roll (infused)",
]

FLOWER_CATEGORIES = [
    "plant, flower - cured",
    "plant, flower - cured, indoor",
    "plant, other",
    "plant, trim",
    "shake/trim (by strain)",
]

_NOT_DETECTED = re.compile(
    r"^(?:not\s*detected|nd|none\s*detected|not\s*found|no\s*residue|pass)$",
    re.IGNORECASE,
)
_LOQ = re.compile(
    r"^(?:<|&lt;|\u2264|<=)?\s*(?:loq|lod|below\s+loq|below\s+lod|below\s+detection)\s*$",
    re.IGNORECASE,
)
_NA_TOKEN = re.compile(r"^(?:n\/?a|na|n\/d|none|--+|-+|\s*)$", re.IGNORECASE)

_SECTION_TITLE = re.compile(r"^[A-Z][A-Z0-9 _&()/.'-]{1,40}$")
_DASH_LINE = re.compile(r"^-{5,}$")
_EQ_LINE = re.compile(r"^=+$")
_HEADER_RE = re.compile(r"^(Product|METRC Category|Detected format|Source file)\s*:\s*(.*)$")
_DATE_RE = re.compile(r"^[0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4}$")
_LAB_RE = re.compile(r"^[a-z_]+$", re.IGNORECASE)
_VALUE_RE = re.compile(r"(-?[0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z%/\u00b5\u03bc\u03bc\s]*)$")
_TITLE_CHECK = re.compile(r"[A-Za-z]{2,}")
_JS_ESCAPE = re.compile(r"[.*+?^${}()|[\]\\]")


def normalize_text(text: str | None) -> str:
    t = "" if text is None else str(text)
    if t and t[0] == "\ufeff":
        t = t[1:]
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\u00a0", " ")
    t = t.replace("\u2018", "'").replace("\u2019", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = t.replace("\u2013", "-").replace("\u2014", "-")
    return t


def normalize_compound_name(name: str) -> str:
    s = str(name)
    for a, b in (("\u03b1", "alpha-"), ("\u0391", "alpha-"),
                 ("\u03b2", "beta-"), ("\u0392", "beta-"),
                 ("\u03b3", "gamma-"), ("\u0393", "gamma-"),
                 ("\u03b4", "delta-"), ("\u0394", "delta-")):
        s = s.replace(a, b)
    for pre in ("alpha-", "beta-", "gamma-", "delta-"):
        s = s.replace(pre + "-", pre)
    return s


def item_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize_compound_name(str(name).lower()))


def normalize_category(cat: str | None) -> str | None:
    if not cat:
        return cat
    c = cat.strip()
    lower = c.lower()
    if lower in CONCENTRATE_CATEGORIES:
        return "Concentrates"
    if lower in PREROLL_CATEGORIES:
        return "Pre-Rolls"
    if lower in INFUSED_PREROLL_CATEGORIES:
        return "Infused Pre-Rolls"
    if lower in FLOWER_CATEGORIES:
        return "Flower"
    return "Edibles" if lower in EDIBLE_CATEGORIES else c


def _utf16_units(s: str):
    data = s.encode("utf-16-le", "surrogatepass")
    for i in range(0, len(data), 2):
        yield data[i] | (data[i + 1] << 8)


def _slice_utf16(s: str, units: int) -> str:
    data = s.encode("utf-16-le", "surrogatepass")
    data = data[: units * 2]
    return data.decode("utf-16-le", "surrogatepass")


def hash_string(s: str) -> str:
    """djb2 over UTF-16 code units, JS 32-bit semantics -> lowercase hex."""
    h = 5381
    for cu in _utf16_units(s):
        h = ((h << 5) + h + cu) & 0xFFFFFFFF
    return format(h, "x")


def parse_value(raw):
    s = str(raw).strip() if raw is not None else ""
    note = None
    m = re.search(r"\s*\(([^)]*)\)\s*$", s)
    if m:
        note = m.group(1).strip()
        s = s[: m.start()].strip()
    if not s:
        return {"value": None, "unit": None, "status": "empty", "note": note, "raw": raw}
    if _NA_TOKEN.match(s):
        return {"value": None, "unit": None, "status": "na", "note": note, "raw": raw}
    if _NOT_DETECTED.match(s):
        return {"value": None, "unit": None, "status": "not_detected", "note": note, "raw": raw}
    if _LOQ.match(s):
        return {"value": None, "unit": None, "status": "below_loq", "note": note, "raw": raw}

    sign = -1 if s.startswith("-") else 1
    vm = _VALUE_RE.search(s)
    if vm:
        value = float(vm.group(1)) * sign
        unit = re.sub(r"\s+", "", vm.group(2)).replace("\u00b5", "ug").replace("\u03bc", "ug")
        return {"value": value, "unit": unit or None, "status": "present", "note": note, "raw": raw}

    return {"value": None, "unit": None, "status": "text", "note": note, "raw": raw}


def parse_item(line: str) -> dict:
    stripped = line.strip()
    idx = stripped.find(":")
    if idx < 0:
        return {"ok": False, "line": line}
    name = stripped[:idx].strip()
    value_raw = stripped[idx + 1:].strip()
    if not name:
        return {"ok": False, "line": line}
    v = parse_value(value_raw)
    return {
        "ok": True,
        "name": name,
        "key": item_key(name),
        "value": v["value"],
        "unit": v["unit"],
        "status": v["status"],
        "note": v["note"],
        "raw": stripped,
    }


def indent_of(line: str) -> int:
    n = 0
    while n < len(line) and line[n] == " ":
        n += 1
    return n


def pad2(n: int) -> str:
    return str(n).zfill(2)


def parse_filename(stem: str) -> dict:
    flags: list[str] = []
    groups = []
    for m in re.finditer(r"\(([^)]*)\)", stem):
        groups.append({"text": m.group(1).strip(), "start": m.start(), "end": m.end()})

    date_group = None
    for gi in range(len(groups) - 1, -1, -1):
        if _DATE_RE.match(groups[gi]["text"]):
            date_group = groups[gi]
            break

    lab_group = None
    for li in range(len(groups) - 1, -1, -1):
        g = groups[li]
        if date_group and g["start"] >= date_group["start"]:
            continue
        lower = g["text"].lower()
        if lower in KNOWN_LABS or _LAB_RE.match(g["text"]):
            lab_group = g
            break

    company = None
    company_group = None
    if groups and groups[0]["start"] == 0:
        company_group = groups[0]
        if company_group is not lab_group and company_group is not date_group:
            company = company_group["text"]

    product = None
    product_start = company_group["end"] if company_group else 0
    product_end = lab_group["start"] if lab_group else len(stem)
    if product_end > product_start:
        product = stem[product_start:product_end].strip()
        product = re.sub(r"[()]\s*$", "", product).strip()
        if not product:
            product = None

    date = None
    date_raw = date_group["text"] if date_group else None
    if date_raw:
        dp = re.split(r"[-/]", date_raw)
        if len(dp) == 3:
            mo = int(dp[0])
            d = int(dp[1])
            y = int(dp[2])
            if mo > 12:
                mo, d = d, mo
            if y < 100:
                y += 2000 if y < 70 else 1900
            if 1 <= d <= 31 and 1 <= mo <= 12:
                date = "{}-{}-{}".format(y, pad2(mo), pad2(d))
            else:
                flags.append("Unrecognized date: " + date_raw)

    if not company:
        flags.append("No company found in filename")
    if not product:
        flags.append("No product name found in filename")
    if not lab_group:
        flags.append("No lab found in filename")
    if not date_raw:
        flags.append("No date found in filename")

    return {
        "company": company,
        "product": product,
        "lab": lab_group["text"] if lab_group else None,
        "date": date,
        "dateRaw": date_raw,
        "flags": flags,
    }


def extract_header(lines: list[str]) -> dict:
    header = {"product": None, "metrcCategory": None, "detectedFormat": None, "sourceFile": None}
    for i in range(min(len(lines), 60)):
        m = _HEADER_RE.match(lines[i])
        if not m:
            continue
        val = m.group(2).strip()
        if not val or re.match(r"^n\/?a$", val, re.IGNORECASE):
            val = None
        key = m.group(1).lower()
        if key == "product":
            header["product"] = val
        elif key == "metrc category":
            header["metrcCategory"] = val
        elif key == "detected format":
            header["detectedFormat"] = val
        elif key == "source file":
            header["sourceFile"] = val
    return header


def is_title_line(line: str) -> bool:
    s = line.strip()
    if not s or len(s) < 2 or len(s) > 60:
        return False
    if re.match(r"^[-=]+$", s):
        return False
    if ":" in s:
        return False
    if not _TITLE_CHECK.search(s):
        return False
    return True


def escape_reg_exp(s: str) -> str:
    return _JS_ESCAPE.sub(lambda m: "\\" + m.group(0), str(s))


def is_junk_line(line: str, record: dict) -> bool:
    s = str(line).strip()
    if not s:
        return True
    j = s.replace("\u00d7", "fi")
    if re.match(r"^certificate of analysis$", j, re.IGNORECASE):
        return True
    if re.match(r"^powered by confident lims$", j, re.IGNORECASE):
        return True
    if re.match(r"^[0-9]+\s+of\s+[0-9]+$", s):
        return True
    if re.match(r"^lic\.?\s*#", s, re.IGNORECASE):
        return True
    if re.match(r"^info@[A-Za-z0-9_.]+$", s, re.IGNORECASE):
        return True
    if re.match(r"^(hrl|hlr)$", s, re.IGNORECASE):
        return True
    if re.match(
        r"^(pesticides|safety|heavy\s*metals?|microbials?|mycotoxins?|analyte|loq|lod|not\s*tested)\s*$",
        s,
        re.IGNORECASE,
    ):
        return True
    if re.match(
        r"^(sample|strain|batch#?|sample received|report created|sampling|environment|harvest process lot|metrc batch|metrc sample)\s*:",
        s,
        re.IGNORECASE,
    ):
        return True
    if re.match(r"^ocr (unavailable|could not)", s, re.IGNORECASE):
        return True
    if re.match(
        r"^[0-9]{2,5}\s+[A-Za-z0-9].*\b(?:st\.?|street|ave\.?|avenue|blvd\.?|boulevard|suite|oklahoma|ok)\b",
        s,
        re.IGNORECASE,
    ):
        return True
    if re.match(r"^[A-Z][A-Za-z.'-]+,\s*[A-Z]{2}\s+[0-9]{5}$", s):
        return True
    if record.get("product") is not None and s == str(record["product"]).strip():
        return True
    if record.get("metrcCategory") is not None and s == str(record["metrcCategory"]).strip():
        return True
    if record.get("metrcCategoryRaw") is not None and s == str(record["metrcCategoryRaw"]).strip():
        return True
    return False


def parse_report(text: str, filename: str) -> dict:
    flags: list[str] = []
    lines = normalize_text(text).split("\n")
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()

    header = extract_header(lines)

    base = re.sub(r"^.*[\\/]", "", str(filename or ""))
    base = re.sub(r"\.txt$", "", base, flags=re.IGNORECASE)
    fn = parse_filename(base)

    record = {
        "company": None,
        "product": header["product"],
        "lab": header["detectedFormat"],
        "date": None,
        "dateRaw": None,
        "metrcCategory": normalize_category(header["metrcCategory"]),
        "metrcCategoryRaw": header["metrcCategory"],
        "sourceFile": header["sourceFile"],
        "detectedFormat": header["detectedFormat"],
        "sections": {},
        "strains": [],
        "flags": [],
        "quality": 0,
        "itemCount": 0,
    }

    if header["product"]:
        record["product"] = header["product"]
    elif fn["product"]:
        record["product"] = fn["product"]
    else:
        flags.append("No product name found")

    record["company"] = fn["company"]
    record["date"] = fn["date"]
    record["dateRaw"] = fn["dateRaw"]
    record["lab"] = record["lab"] or fn["lab"]
    flags = flags + fn["flags"]

    if not record["product"] and record["sourceFile"]:
        sf = re.sub(r"\.pdf$", "", str(record["sourceFile"]), flags=re.IGNORECASE).strip()
        sf = re.sub(r"^[A-Z0-9][A-Z0-9.]*\s*-\s*", "", sf)
        if record["company"]:
            sf = re.sub(
                "^" + escape_reg_exp(record["company"]) + r"\s*-\s*",
                "",
                sf,
                flags=re.IGNORECASE,
            )
        sf = sf.replace("_", " ")
        sf = re.sub(r"\s*-\s*$", "", sf).strip()
        if sf and len(sf) > 1:
            record["product"] = sf
            flags.append("Product name taken from source filename")

    cur_section = None
    cur_strain = None
    pending_title = None
    pending_indent = 0
    unmatched: list[str] = []

    def ensure_section(title: str, _indent: int, strain: dict | None) -> None:
        nonlocal cur_section, cur_strain
        target = strain["sections"] if strain else record["sections"]
        if title not in target:
            target[title] = []
        cur_section = target[title]
        cur_strain = strain

    def clear_pending_title() -> None:
        nonlocal pending_title
        if pending_title is None:
            return
        flags.append('Possible section title not followed by a rule: "{}"'.format(pending_title))
        unmatched.append(pending_title)
        pending_title = None

    for raw_line in lines:
        line = raw_line.strip()
        ind = indent_of(raw_line)

        if not line:
            clear_pending_title()
            continue

        if _EQ_LINE.match(line):
            pending_title = None
            cur_section = None
            cur_strain = None
            continue

        if _DASH_LINE.match(line):
            if pending_title is not None:
                title = pending_title
                title_indent = pending_indent
                pending_title = None
                is_caps = (
                    title and title[0] in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" and title == title.upper()
                )
                if is_caps and title_indent == 0:
                    ensure_section(title, 0, None)
                elif is_caps and title_indent > 0 and cur_strain:
                    ensure_section(title, title_indent, cur_strain)
                elif is_caps and title_indent > 0 and not cur_strain:
                    ensure_section(title, title_indent, None)
                else:
                    strain = {"name": title, "sections": {}}
                    record["strains"].append(strain)
                    cur_strain = strain
                    cur_section = None
                    pending_title = None
            continue

        if re.match(r"^COA Parser Report\b", line, re.IGNORECASE):
            continue

        if is_junk_line(line, record):
            clear_pending_title()
            continue

        if is_title_line(line):
            clear_pending_title()
            if (
                line[0] in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                and line == line.upper()
                and ind > 0
                and cur_strain
            ):
                ensure_section(line, ind, cur_strain)
                continue
            pending_title = line
            pending_indent = ind
            continue

        clear_pending_title()

        if re.match(
            r"^(COA Parser Report|Source file|Detected format|Product|METRC Category)\b",
            line,
            re.IGNORECASE,
        ):
            continue

        if cur_section is None:
            unmatched.append(line)
            continue

        item = parse_item(line)
        if not item["ok"]:
            flags.append('Unparseable line in section: "{}"'.format(line))
            unmatched.append(line)
            continue
        cur_section.append(item)

    clear_pending_title()

    if unmatched:
        record["sections"].setdefault("DETECTED ANALYTES", [])
        for l in [x for x in unmatched if not is_junk_line(x, record)]:
            item = parse_item(l)
            if item["ok"]:
                record["sections"]["DETECTED ANALYTES"].append(item)
            else:
                record["sections"]["DETECTED ANALYTES"].append(
                    {
                        "ok": True,
                        "name": l,
                        "key": item_key(l),
                        "value": None,
                        "unit": None,
                        "status": "text",
                        "note": None,
                        "raw": l,
                    }
                )

    section_names = list(record["sections"].keys())
    for sname in section_names:
        if sname.lower() not in KNOWN_SECTIONS:
            flags.append("Unrecognized section: " + sname)
    for sn in list(record["sections"].keys()):
        if not record["sections"][sn]:
            del record["sections"][sn]
    for s in record["strains"]:
        for sn in list(s["sections"].keys()):
            if not s["sections"][sn]:
                del s["sections"][sn]
    section_names = list(record["sections"].keys())
    for s in record["strains"]:
        if not s["sections"]:
            flags.append("Strain with no sections: " + s["name"])

    item_count = 0
    for sn in section_names:
        item_count += len(record["sections"][sn])
    for s in record["strains"]:
        for sn in s["sections"]:
            item_count += len(s["sections"][sn])
    record["itemCount"] = item_count

    if item_count == 0:
        flags.append("No analytes parsed")

    record["flags"] = flags

    import math

    score = 0
    if record["product"]:
        score += 0.25
    if record["company"]:
        score += 0.15
    if record["lab"]:
        score += 0.1
    if record["date"]:
        score += 0.1
    if item_count > 0:
        score += 0.2
    score += min(0.2, item_count * 0.02)
    record["quality"] = min(1.0, math.floor(score * 100 + 0.5) / 100)

    return record


def parse_file(text: str, filename: str) -> dict:
    record = parse_report(text, filename)
    return {
        "ok": True,
        "id": hash_string((filename or "") + "|" + _slice_utf16(normalize_text(text), 4000)),
        "filename": filename or "",
        "record": record,
    }


def stem_of(name: str) -> str:
    n = re.sub(r"^.*[\\/]", "", str(name))
    return re.sub(r"\.[^.]+$", "", n)


def image_path_for(filename: str) -> str:
    return "images/" + stem_of(filename) + ".webp"


def build_search_text(r: dict) -> str:
    parts = [
        r.get("company"),
        r.get("product"),
        r.get("metrcCategory"),
        r.get("lab"),
        r.get("sourceFile"),
    ]
    for sn in r.get("sections") or {}:
        parts.append(sn)
        for it in r["sections"][sn]:
            parts.append(it.get("name"))
    for s in r.get("strains") or []:
        parts.append(s.get("name"))
        for sn in s.get("sections") or {}:
            parts.append(sn)
            for it in s["sections"][sn]:
                parts.append(it.get("name"))
    return " ".join("" if p is None else str(p) for p in parts).lower()


def build_catalog_doc(text: str, filename: str) -> dict:
    """Full Firestore document for a .txt output (mirrors admin productDoc)."""
    pf = parse_file(text, filename)
    r = pf["record"]
    return {
        "id": pf["id"],
        "filename": pf["filename"],
        "company": r.get("company"),
        "product": r.get("product"),
        "lab": r.get("lab"),
        "date": r.get("date"),
        "dateRaw": r.get("dateRaw"),
        "metrcCategory": r.get("metrcCategory"),
        "sourceFile": r.get("sourceFile"),
        "detectedFormat": r.get("detectedFormat"),
        "sections": r.get("sections"),
        "strains": r.get("strains"),
        "quality": r.get("quality"),
        "flags": r.get("flags"),
        "itemCount": r.get("itemCount"),
        "searchText": build_search_text(r),
        "imagePath": image_path_for(pf["filename"]),
    }
