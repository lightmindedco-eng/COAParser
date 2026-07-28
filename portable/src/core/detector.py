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

    # Pass 2: "Strain:" label (Aerolabs / Confident LIMS)
    for line in lines[:50]:
        if re.match(r"strain\s*:", line, re.IGNORECASE):
            parts = line.split(":", 1)
            if len(parts) == 2:
                product_name = parts[1].strip()
                # Remove trailing " - Batch XXXX" metadata
                product_name = re.sub(
                    r"\s*-\s*batch\s*\d+.*$", "", product_name, flags=re.IGNORECASE
                ).strip()
                if len(product_name) > 3 and len(product_name) < 250:
                    return _clean_product_name(product_name)

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


def detect_company_name(lines: list[str]) -> str | None:
    """
    Extract the company/producer name from COA lines.

    Pass 1 – Known patterns (LLC, Inc, Corp) in first 10 lines
    Pass 2 – Line right after "Certificate of Analysis" header (most formats)
    """
    # Pass 1: Known company patterns (LLC, Inc, Corp) in first 10 lines
    for line in lines[:10]:
        line_stripped = line.strip()
        if re.search(r"\b(LLC|Inc\.?|Corp\.?|Co\.?|Company)\b", line_stripped, re.IGNORECASE):
            if 3 < len(line_stripped) < 80:
                return line_stripped

    # Pass 2: Company name typically appears right after "Certificate of Analysis"
    # Handle encoding artifacts: "Certi×cate", "Certiﬁcate", "Con×dent"
    for i, line in enumerate(lines[:200]):
        if re.search(r"certi.{0,2}cate\s+of\s+analysis", line, re.IGNORECASE):
            # Check the next few non-empty lines for a company name
            for j in range(i + 1, min(i + 10, len(lines))):
                candidate = lines[j].strip()
                if not candidate:
                    continue
                # Skip page numbers, metadata, headers
                if re.search(r"page\s*\d|powered\s+by|sample|strain|final|pass\b|fail\b|^\d+\s+of\s+\d+$|batch|compliance|production|manifest", candidate, re.IGNORECASE):
                    continue
                # Skip lines that look like addresses, phone numbers, or dates
                if re.search(r"\d{3}[\s.-]\d{3}[\s.-]\d{4}|^\d+\s+\w+\s+(st|rd|ave|blvd|dr)|date|released|^\d+/|order\s*#|\b(oklahoma|ok|ca|co|nv|mi)\s+\d{5}\b|\d+\s+\w+\s+(st|street|road|rd|avenue|ave|blvd|drive|dr|ln|lane|way|ct|circle)\b", candidate, re.IGNORECASE):
                    continue
                # Skip license lines
                if re.search(r"lic\.?\s*#|omma|report\s*#", candidate, re.IGNORECASE):
                    continue
                # Looks like a company name (short, no numbers except in abbreviations)
                if 3 < len(candidate) < 80:
                    return candidate
            break

    return None


def detect_report_date(lines: list[str]) -> str | None:
    """
    Extract the report date from COA lines.

    Looks for patterns like:
    - "Report Created: MM/DD/YYYY"
    - "Report Date: MM/DD/YYYY"
    - "Released: MM/DD/YYYY"
    - "Date Released: MM/DD/YYYY"
    """
    for line in lines[:300]:
        # "Report Created: MM/DD/YYYY"
        m = re.search(r"report\s+created\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
        # "Report Date: MM/DD/YYYY"
        m = re.search(r"report\s+date\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
        # "Released: MM/DD/YYYY"
        m = re.search(r"released?\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
        # "Date Released: MM/DD/YYYY"
        m = re.search(r"date\s+released?\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if m:
            return m.group(1)
    return None
