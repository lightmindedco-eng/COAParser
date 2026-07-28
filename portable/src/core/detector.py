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

    # Pass 2: "Strain:" or "Strain Name:" label (Aerolabs / Confident LIMS / HighRes Labs)
    for line in lines[:50]:
        if re.match(r"strain\s*(?:name)?\s*:", line, re.IGNORECASE):
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


def detect_company_name(lines: list[str]) -> str | None:
    """
    Extract the company/producer name from COA lines.

    Pass 1 – Known patterns (LLC, Inc, Corp) in first 10 lines
    Pass 2 – Line right after "Certificate of Analysis" header (most formats)
    Pass 3 – "Client" / "Client Name" label followed by company name
    """
    # Pass 1: Known company patterns (LLC, Inc, Corp) in first 10 lines
    for line in lines[:10]:
        line_stripped = line.strip()
        if re.search(r"\b(LLC|Inc\.?|Corp\.?|Co\.?|Company)\b", line_stripped, re.IGNORECASE):
            # Skip lines that start with labels like "Client Name:" — Pass 3 will handle
            if re.match(r"^client\s*(?:name)?\s*:", line_stripped, re.IGNORECASE):
                continue
            # Skip metadata lines like "Report Version: 1.2"
            if re.match(r"^report\s+version\s*:", line_stripped, re.IGNORECASE):
                continue
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
                if re.search(r"\d{3}[\s.-]\d{3}[\s.-]\d{4}|^\d+\s+\w+\s+(st|rd|ave|blvd|dr)|date|released|^\d+/|order\s*#|\b(oklahoma|ok|ca|co|nv|mi)\s+\d{5}\b|\d+\s+\w+\s+(st|street|road|rd|avenue|ave|blvd|drive|dr|ln|lane|way|ct|circle)\b|^\d{3}\s+\w+\s+\w+\s+(st|street|road|rd|avenue|ave|blvd|drive|dr|ln|lane|way|ct|circle)\b|broadway\s+extension", candidate, re.IGNORECASE):
                    continue
                # Skip license lines
                if re.search(r"lic\.?\s*#|omma|report\s*#|http|www\.|\.com", candidate, re.IGNORECASE):
                    continue
                # Skip lines that are clearly not company names
                if re.search(r"^(requested|comprehensive|estimated|sampling|sop|errors|report\s+version|potency|terpenes?|cannabinoids?|residual\s+solvents?|pesticides?|heavy\s+metals?|microbiology|moisture|water\s+activity|foreign\s+material|mycotoxins|contamination|tested|pass\b|fail\b|complete|analyte|result|method|limit|not\s+detected|certificate|summary|page\s+\d)", candidate, re.IGNORECASE):
                    continue
                # Looks like a company name (short, no numbers except in abbreviations)
                if 3 < len(candidate) < 80:
                    return candidate
            break

    # Pass 3: "Client" / "Client Name" followed by or containing company name
    for i, line in enumerate(lines[:50]):
        # "Client Name: Company Name, LLC" — value on same line
        m = re.match(r"^client\s*(?:name)?\s*:\s*(.+)$", line.strip(), re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if candidate and 3 < len(candidate) < 80:
                if not re.search(r"^\d|sample|batch|metrc|http|lic", candidate, re.IGNORECASE):
                    return candidate
        # "Client Name" on one line, company on next
        if re.match(r"^client\s*(?:name)?\s*:?\s*$", line.strip(), re.IGNORECASE):
            if i + 1 < len(lines):
                candidate = lines[i + 1].strip()
                if candidate and 3 < len(candidate) < 80:
                    if not re.search(r"^\d|sample|batch|metrc|http|lic", candidate, re.IGNORECASE):
                        return candidate

    return None


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
