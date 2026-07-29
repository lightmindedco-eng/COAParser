"""Detection helpers for COA document types."""

from __future__ import annotations

import re


def detect_format(content: str) -> str:
    """Return a simple format label based on content hints."""
    lowered = content.lower()
    if "aerolabs" in lowered:
        return "aerolabs"
    if "gateway" in lowered or "gatewaylabs" in lowered:
        return "gateway"
    if "baseline" in lowered:
        return "baseline"
    if "havard industries" in lowered or "condent" in lowered:
        return "confident"
    if "confident" in lowered:
        return "confident"
    if "certificate of analysis" in lowered or "thc" in lowered or "cbd" in lowered:
        return "aerolabs"
    return "unknown"


def detect_product_name(lines: list[str]) -> str | None:
    """
    Extract product name from COA lines.

    Pass 1 – "Sample Name:" label (Gateway v2, Confident LIMS newer reports)
    Pass 2 – "Strain:" label (Aerolabs / Confident LIMS)
    Pass 3 – Standalone line immediately before "Sample #:" (Gateway v1 / older reports)
    Pass 4 – Product keyword + dash heuristic (fallback)
    """
    # Early exit: single OCR-failure line has no useful content
    if len(lines) == 1 and lines[0].lower().startswith("ocr unavailable"):
        return None

    # Pass 1: "Sample Name:" label
    for line in lines[:300]:
        line_lower = line.lower()
        if "sample name" in line_lower and ":" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                product_name = parts[1].strip()
                if "|" in product_name:
                    product_name = product_name.split("|")[0].strip()
                if len(product_name) > 3 and len(product_name) < 250:
                    return _clean_product_name(product_name)

    # Pass 1b: "Sample:" label (Baseline Labs, others)
    # Skip if value looks like a sample ID (short alphanumeric code with dots/dashes)
    for line in lines[:300]:
        line_lower = line.lower()
        if re.match(r"^sample\s*:", line_lower) and "sample name" not in line_lower and "sample id" not in line_lower:
            parts = line.split(":", 1)
            if len(parts) == 2:
                product_name = parts[1].strip()
                # Skip sample IDs (short codes like "2604HTL0930.6411")
                if re.match(r"^[A-Z0-9][\w.-]+$", product_name) and len(product_name) < 30:
                    continue
                if len(product_name) > 3 and len(product_name) < 250:
                    return _clean_product_name(product_name)

    # Pass 2: full product description line (with brand, potency, form) before Strain:
    # Catches lines like "Smokiez Sour Peach Sativa 100mg THC Fruit Chews"
    # but avoids catching continuation lines that lack a potency indicator.
    for line in lines[:80]:
        stripped = line.strip()
        if not stripped or len(stripped) < 15:
            continue
        # Skip labeled lines (colon in first 25 chars is a label prefix like "Strain: Peach")
        # but keep lines where colon is in compound ratio notation (e.g. "THC:CBD")
        colon_pos = stripped.find(":")
        if colon_pos >= 0 and colon_pos < 25:
            continue
        if re.search(r"\b\d+\s*mg\b", stripped, re.IGNORECASE) and re.search(r"\b(thc|cbd)\b", stripped, re.IGNORECASE):
            if not re.match(r"^[\d\s/\-:.,()%]+$", stripped):
                return _clean_product_name(stripped)

    # Pass 3: "Strain:" or "Strain Name:" label (Aerolabs / Confident LIMS / HighRes Labs)
    # Also look ahead for a fuller product description line nearby.
    for i, line in enumerate(lines[:50]):
        if re.match(r"strain\s*(?:name)?\s*:", line, re.IGNORECASE):
            parts = line.split(":", 1)
            strain_value = parts[1].strip() if len(parts) == 2 else ""

            # Look ahead for a fuller description line (no colon, longer, has " - " separator)
            for j in range(i + 1, min(i + 15, len(lines))):
                candidate = lines[j].strip()
                if not candidate or ":" in candidate:
                    continue
                # Check for a fuller product description first
                if len(candidate) > 15 and " - " in candidate:
                    if not re.search(r"(batch\s+#?|lot\s+#?|harvest|sampling|environment|primary\s+sample|metrc)", candidate, re.IGNORECASE):
                        return _clean_product_name(candidate)
                # Stop at category or METRC lines (checked after description match)
                if re.search(r"\b(metrc|concentrate|edible|ingestible|plant,\s|^[A-Z][a-z]+,\s)", candidate, re.IGNORECASE):
                    break

            # Fallback to the Strain: value
            if strain_value:
                strain_value = re.sub(
                    r"\s*-\s*batch\s*\d+.*$", "", strain_value, flags=re.IGNORECASE
                ).strip()
                if len(strain_value) > 3 and len(strain_value) < 250:
                    return _clean_product_name(strain_value)

    # Pass 3: standalone line just before "Sample #:" (Gateway v1 older format)
    # Collect backward from the "Sample #:" anchor, joining wrapped lines
    for i, line in enumerate(lines[:30]):
        if re.search(r"sample\s*#", line, re.IGNORECASE):
            candidate_lines: list[str] = []
            j = i - 1
            while j >= 0 and ":" not in lines[j]:
                candidate_lines.insert(0, lines[j].strip())
                j -= 1
            if candidate_lines:
                joined = " ".join(candidate_lines).strip()
                # Reject if it looks like a plain date, number, or is too short
                if len(joined) > 3 and not re.match(r"^[\d/\s:.-]+$", joined):
                    return _clean_product_name(joined)
            break

    # Pass 3b: "Description:" label (Sunrise Labs / Bee Elevated Results format)
    for i, line in enumerate(lines[:100]):
        if re.match(r"description\s*:", line, re.IGNORECASE):
            if i + 1 < len(lines):
                candidate = lines[i + 1].strip()
                if candidate and 3 < len(candidate) < 250:
                    if not re.match(r"^[\d/\s:.-]+$", candidate):
                        return _clean_product_name(candidate)

    # Pass 4: product keyword + dash heuristic (fallback)
    _product_keywords = {
        "preroll", "pre-roll", "bud", "flower", "edible", "tincture", "oil", "extract",
        "cartridge", "concentrate", "hash", "kief", "rosin", "sauce", "shake",
        "trim", "popcorn", "smalls", "sugar", "diamond", "crumble",
        "wax", "budder", "badder", "live", "distillate",
        "isolate", "full spectrum", "broad spectrum", "capsule", "sublingual",
    }
    _skip_prefixes = (
        "type:", "plant,", "strain:", "category/type:", "category:",
        "date ", "license", "metrc", "report #", "order #", "sample #",
        "batch#", "batch #",
    )
    for line in lines[:100]:
        line_lower = line.lower().strip()
        if any(line_lower.startswith(p) for p in _skip_prefixes):
            continue
        if any(kw in line_lower for kw in _product_keywords):
            if 10 < len(line.strip()) < 150:
                if "-" in line or any(kw + "s" in line_lower for kw in ["preroll", "pre-roll"]):
                    return _clean_product_name(line.strip())

    return None



def _clean_product_name(name: str) -> str:
    """Clean up product name by removing common metadata prefixes/suffixes."""
    # Remove common metadata labels at the start
    patterns_to_remove = [
        r"^(LLC|Inc|Inc\.|Corp|Corp\.|Co\.|Company|Brand|Producer|Grower)\s*-?\s*",
        r"^(Email|Date|Tested|Sample)\s*[:\-]?\s*",
    ]
    
    cleaned = name
    for pattern in patterns_to_remove:
        match = re.match(pattern, cleaned)
        if match:
            candidate = cleaned[match.end():].strip()
            if len(candidate) >= 5:
                cleaned = candidate
            break
    
    # Also remove common suffixes that are metadata
    suffix_patterns = [
        r"\s*\(.*?batch.*?\)$",
        r"\s*\(.*?lot.*?\)$",
    ]
    for pattern in suffix_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip()


_TEST_HEADER_NAMES = frozenset({
    "regulatory compliance testing",
    "residual solvents",
    "foreign materials & filth",
    "microbial impurities",
    "heavy metals",
    "water activity",
    "certificate of analysis",
    "analysis summary",
})


def _looks_like_company_name(candidate: str) -> bool:
    """Check if a line looks like a company/producer name."""
    if len(candidate) < 5 or len(candidate) > 80:
        return False
    stripped = candidate.strip()
    if stripped.lower() in _TEST_HEADER_NAMES:
        return False
    # Skip addresses (starts with number + street)
    if re.match(r"^\d+\s+\w+\s+(st|street|rd|road|ave|avenue|blvd|drive|dr|ln|lane|way|ct|circle|pl|place)\b", candidate, re.IGNORECASE):
        return False
    # Skip city/state/zip lines
    if re.match(r"^[\w\s]+,\s*(OK|CA|CO|NV|MI|OR|WA|AZ|NM)\s+\d{5}", candidate, re.IGNORECASE):
        return False
    # Skip emails, phones, URLs
    if re.search(r"@|www\.|\.com|\d{3}[\s.-]\d{3}[\s.-]\d{4}", candidate):
        return False
    # Skip labeled fields (contain ":")
    if ":" in candidate:
        return False
    # Skip purely numeric or percentage lines
    if re.match(r"^[\d.%]+$", candidate):
        return False
    # Skip single words
    if len(candidate.split()) < 2:
        return False
    # At least one capitalized word (not all-lowercase or all-uppercase metadata)
    words = candidate.split()
    caps_count = sum(1 for w in words if w[0].isupper() if len(w) > 1)
    if caps_count < 1:
        return False
    return True


def _find_client_line(lines: list[str]) -> str | None:
    """Extract company name from a 'Client:' or 'Client Name:' label."""
    for i, line in enumerate(lines[:50]):
        m = re.match(r"^client\s*(?:name)?\s*:\s*(.+)$", line.strip(), re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if candidate and 3 < len(candidate) < 80:
                if not re.search(r"^\d|sample|batch|metrc|http|lic", candidate, re.IGNORECASE):
                    return candidate
        if re.match(r"^client\s*(?:name)?\s*:?\s*$", line.strip(), re.IGNORECASE):
            if i + 1 < len(lines):
                candidate = lines[i + 1].strip()
                if candidate and 3 < len(candidate) < 80:
                    if not re.search(r"^\d|sample|batch|metrc|http|lic", candidate, re.IGNORECASE):
                        return candidate
    return None


def detect_company_name(lines: list[str]) -> str | None:
    """
    Extract the company/producer name from COA lines.

    Pass 0 – "Client" / "Client Name" label (most reliable)
    Pass 1 – Leading lines before "Certificate of Analysis" (Gateway format, others)
    Pass 2 – Known patterns (LLC, Inc, Corp) in first 10 lines
    Pass 3 – Line right after "Certificate of Analysis" header (most formats)
    """
    # Pass 0: "Client" / "Client Name" label (most reliable indicator)
    client = _find_client_line(lines)
    if client:
        return client

    # Pass 1: Company name often appears in first lines before "Certificate of Analysis"
    # Find where "Certificate of Analysis" first appears
    cert_idx = None
    for i, line in enumerate(lines[:100]):
        if re.search(r"certi.{0,2}cate\s+of\s+analysis", line, re.IGNORECASE):
            cert_idx = i
            break
    scan_limit = cert_idx if cert_idx is not None else 10
    for i in range(min(scan_limit, 20)):
        candidate = lines[i].strip()
        if _looks_like_company_name(candidate):
            # Skip lines that look like testing labs — the real company is elsewhere
            if re.search(r"\blab(?:oratory|s)?\b", candidate, re.IGNORECASE):
                continue
            return candidate

    # Pass 2: Known company patterns (LLC, Inc, Corp) in first 10 lines
    for line in lines[:10]:
        line_stripped = line.strip()
        if re.search(r"\b(LLC|Inc\.?|Corp\.?|Co\.?|Company)\b", line_stripped, re.IGNORECASE):
            if re.match(r"^client\s*(?:name)?\s*:", line_stripped, re.IGNORECASE):
                continue
            if re.match(r"^report\s+version\s*:", line_stripped, re.IGNORECASE):
                continue
            if 3 < len(line_stripped) < 80:
                return line_stripped

    # Pass 3: Company name typically appears right after "Certificate of Analysis"
    for i, line in enumerate(lines[:200]):
        if re.search(r"certi.{0,2}cate\s+of\s+analysis", line, re.IGNORECASE):
            for j in range(i + 1, min(i + 10, len(lines))):
                candidate = lines[j].strip()
                if not candidate:
                    continue
                if re.search(r"page\s*\d|powered\s+by|sample|strain|final|pass\b|fail\b|^\d+\s+of\s+\d+$|batch|compliance|production|manifest", candidate, re.IGNORECASE):
                    continue
                if re.search(r"\d{3}[\s.-]\d{3}[\s.-]\d{4}|^\d+\s+\w+\s+(st|rd|ave|blvd|dr)|date|released|^\d+/|order\s*#|\b(oklahoma|ok|ca|co|nv|mi)\s+\d{5}\b|\d+\s+\w+\s+(st|street|road|rd|avenue|ave|blvd|drive|dr|ln|lane|way|ct|circle)\b|^\d{3}\s+\w+\s+\w+\s+(st|street|road|rd|avenue|ave|blvd|drive|dr|ln|lane|way|ct|circle)\b|broadway\s+extension", candidate, re.IGNORECASE):
                    continue
                if re.search(r"lic\.?\s*#|omma|report\s*#|http|www\.|\.com", candidate, re.IGNORECASE):
                    continue
                if re.search(r"^(requested|comprehensive|estimated|sampling|sop|errors|report\s+version|potency|terpenes?|cannabinoids?|residual\s+solvents?|pesticides?|heavy\s+metals?|microbiology|moisture|water\s+activity|foreign\s+material|mycotoxins|contamination|tested|pass\b|fail\b|complete|analyte|result|method|limit|not\s+detected|certificate|summary|total\b|page\s+\d)", candidate, re.IGNORECASE):
                    continue
                if re.match(r"^[\d.]+%?$", candidate):
                    continue
                if 3 < len(candidate) < 80:
                    return candidate
            break

    return None


def _detect_metrc_category_raw(lines: list[str]) -> str | None:
    """
    Extract the METRC product category from COA lines.

    Pass 1 – "Category/Type:" label (Gateway v1/v2, older reports)
    Pass 2 – "Type:" label (newer reports without Category prefix)
    """
    # Pass 1: "Category/Type:" label
    for line in lines[:50]:
        m = re.match(r"^category/type\s*:\s*(.+)$", line.strip(), re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if candidate and len(candidate) > 3:
                return candidate

    # Pass 2: "Type:" label (standalone, not preceded by "Category/")
    for line in lines[:50]:
        m = re.match(r"^type\s*:\s*(.+)$", line.strip(), re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if candidate and len(candidate) > 3:
                return candidate

    # Pass 3: Match unlabeled lines against known METRC category vocabulary
    # (covers PDFs where category appears as a standalone line without "Type:" label)
    _METRC_CATEGORIES = {
        # Official METRC values
        "Bulk Concentrate (Weight-Based)",
        "Concentrate (Non-Solvent Based) (Count-Volume)",
        "Concentrate (Non-Solvent Based) (Count-Weight)",
        "Edibles (Count-Volume)", "Edibles (Count-Weight)",
        "Extracts (Solvent Based) (Count-Volume)",
        "Extracts (Solvent Based) (Count-Weight)",
        "Flower & Bud (Count)", "Flower & Buds bulk",
        "Flower - For Decontamination", "Immature Plants",
        "InfusedNonEdible (Count)", "InfusedNonEdible (Weight)",
        "Kief (Count)", "Kief bulk", "Mature Plants",
        "Metered Dose Nasal Spray Products",
        "MMJ Clone Waste", "MMJ Waste", "MMJ Waste (by Count)",
        "Pre-Roll (Flower Only)", "Pre-Roll (Infused)",
        "Pressurized Metered Dose Inhaler Products",
        "Rectal/Vaginal Administration Products (Count-Volume)",
        "Rectal/Vaginal Administration Products (Count-Weight)",
        "Seeds", "Shake/Trim (by Strain)", "Shake/Trim (Count)",
        "Shake/Trim - For Decontamination", "Shake/Trim bulk",
        "Tinctures (Count-Volume)", "Tinctures (Count-Weight)",
        "Topicals (Count-Volume)", "Topicals (Count-Weight)",
        "Transdermal Patches", "Whole Wet Plant", "Vape Cartridges",
        # Variations seen in actual PDFs
        "Soft Chew",
        "Plant, Flower - Cured",
        "Plant, Enhanced/Infused Preroll",
        "Concentrates, Solvent based concentrate",
        "Concentrates & Extracts, Vape",
        "Infused Non-Edible, Lotion",
        "Flower - Cured",
        "Plant, Preroll",
        "Plant, Trim",
        "Plant, Bulk Flower",
        "Plant, Flower - Cured, Indoor",
        "Concentrates & Extracts, Live Rosin",
        "Concentrates & Extracts, Diamonds",
        "Concentrates & Extracts, Other",
        "Concentrates & Extracts, Full Extract Cannabis Oil",
        "Concentrates & Extracts, Distillate",
        "Concentrates & Extracts, Vape",
        "Edible (Count-Weight)",
        "Ingestible, Chocolate",
        "Ingestible, Baked Goods",
    }
    _METRC_SHORT = {c.lower(): c for c in _METRC_CATEGORIES}
    # Non-canonical forms → canonical category (sample matrix labels, etc.)
    _METRC_ALIASES = {
        "infused pre-roll": "Plant, Enhanced/Infused Preroll",
        "vape cart": "Concentrates & Extracts, Vape",
        "vape cartridges": "Concentrates & Extracts, Vape",
        "flower - cured": "Plant, Flower - Cured",
    }
    _METRC_SHORT.update(
        {k.lower(): v for k, v in _METRC_ALIASES.items()}
    )

    # Build category format patterns (matches lines that look like category entries)
    # Format: `<CategoryType>, <Specific>` or `<CategoryType> - <Specific>`
    # but NOT product names (which often contain "(g)", "Strain:", etc.)
    _CATEGORY_LINE_PATTERN = re.compile(
        r"^(?:"
        r"Plant,\s+.+|"
        r"Concentrates?\s+(?:&\s+)?Extracts?,\s+.+|"
        r"Infused\s+(?:Non-Edible|NonEdible),\s+.+"
        r")$",
        re.IGNORECASE
    )
    _PRODUCT_INDICATORS = re.compile(r"\(g\)|\(units\)|inherited", re.IGNORECASE)
    _HARVEST_SUFFIX = re.compile(r";\s*harvest\s+process\s+lot:.*$", re.IGNORECASE)
    _LABELED_LINES = re.compile(
        r"^(?:strain|sample\s+matrix|type|category)\s*:\s*(.+)$", re.IGNORECASE
    )

    for line in lines[:50]:
        stripped = line.strip()
        if not stripped:
            continue


        # Check labeled lines (Strain:, Sample Matrix:, Type:, etc.) for category in values
        m_label = _LABELED_LINES.match(stripped)
        if m_label:
            value = m_label.group(1).strip()
            # Split on pipe (common in Strain: lines with format "Product | Category | Details")
            for val_seg in re.split(r"\s*\|\s*", value):
                val_clean = val_seg.strip().rstrip(";.,")
                if not val_clean or len(val_clean) < 4:
                    continue
                val_lower = val_clean.lower()
                if val_lower in _METRC_SHORT:
                    return _METRC_SHORT[val_lower]
                for cat_lower, cat in _METRC_SHORT.items():
                    if cat_lower in val_lower:
                        return cat

        # Check each semicolon-separated segment for category clues
        # (category often appears before "; Harvest Process Lot:" on Confident LIMS)
        segments = re.split(r"\s*;\s*", stripped)
        for segment in segments:
            if ":" in segment:
                # Also check the right side of labeled segments
                parts = segment.split(":", 1)
                if len(parts) == 2:
                    rhs = parts[1].strip()
                    if rhs and len(rhs) >= 4 and not _PRODUCT_INDICATORS.search(rhs):
                        rhs_lower = rhs.lower()
                        if rhs_lower in _METRC_SHORT:
                            return _METRC_SHORT[rhs_lower]
                        for cat_lower, cat in _METRC_SHORT.items():
                            if cat_lower in rhs_lower:
                                return cat
                continue
            candidate = segment.strip()
            if not candidate or len(candidate) < 5:
                continue
            if _PRODUCT_INDICATORS.search(candidate):
                continue
            clean = candidate.rstrip(";.,")
            lower = clean.lower()
            if lower in _METRC_SHORT:
                return _METRC_SHORT[lower]
            for cat_lower, cat in _METRC_SHORT.items():
                if cat_lower in lower:
                    return cat
            if _CATEGORY_LINE_PATTERN.match(candidate):
                return clean
        # Also check the whole line (minus harvest suffix) for pattern match
        line_clean = _HARVEST_SUFFIX.sub("", stripped).strip().rstrip(";.,")
        if line_clean and ":" not in line_clean and len(line_clean) >= 5:
            lower_full = line_clean.lower()
            if lower_full in _METRC_SHORT:
                return _METRC_SHORT[lower_full]
            for cat_lower, cat in _METRC_SHORT.items():
                if cat_lower in lower_full:
                    return cat
            if _CATEGORY_LINE_PATTERN.match(line_clean):
                return line_clean

    return None


def _normalize_category(cat: str | None) -> str | None:
    if cat is None:
        return None
    _MAP = {
        "Vape Cartridges": "Concentrates & Extracts, Vape",
        "Flower - Cured": "Plant, Flower - Cured",
    }
    return _MAP.get(cat, cat)


def detect_metrc_category(lines: list[str]) -> str | None:
    return _normalize_category(_detect_metrc_category_raw(lines))


def detect_report_date(lines: list[str]) -> str | None:
    """
    Extract the report date from COA lines.

    High-priority patterns (return immediately):
    - "Report Created: MM/DD/YYYY"
    - "Report Date: MM/DD/YYYY"
    - "Released: MM/DD/YYYY"
    - "Completed: MM/DD/YYYY"

    Low-priority patterns (return only if no high-priority found):
    - "Date Released: MM/DD/YYYY"
    - "Date Received: MM/DD/YYYY"
    - "Date Tested: MM/DD/YYYY"
    - "Date Analyzed: MM/DD/YYYY"
    """
    # Pass 1: High-priority report date patterns
    for i, line in enumerate(lines[:300]):
        m = re.search(r"report\s+created\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"report\s+date\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"released?\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"completed\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
        # Date on next line: "Date Reported:\n4/14/2026"
        if re.match(r"^date\s+reported\s*:?\s*$", line.strip(), re.IGNORECASE):
            if i + 1 < len(lines):
                m2 = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", lines[i + 1])
                if m2:
                    return m2.group(1)

    # Pass 2: Lower-priority date patterns (Date Released/Received/Tested/Analyzed)
    for i, line in enumerate(lines[:300]):
        m = re.search(r"date\s+released?\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"date\s+received\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"date\s+tested\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"date\s+analyzed\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
        # Date on next line: "Date Received:\n3/11/2026"
        if re.match(r"^date\s+(?:received|tested|analyzed|released)\s*:?\s*$", line.strip(), re.IGNORECASE):
            if i + 1 < len(lines):
                m2 = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", lines[i + 1])
                if m2:
                    return m2.group(1)
    return None
