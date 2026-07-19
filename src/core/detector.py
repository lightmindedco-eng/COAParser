"""Detection helpers for COA document types."""

from __future__ import annotations


def detect_format(content: str) -> str:
    """Return a simple format label based on content hints."""
    lowered = content.lower()
    if "aerolabs" in lowered:
        return "aerolabs"
    if "gateway" in lowered or "gatewaylabs" in lowered:
        return "gateway"
    if "confident" in lowered:
        return "confident"
    if "certificate of analysis" in lowered or "thc" in lowered or "cbd" in lowered:
        return "aerolabs"
    return "unknown"


def detect_product_name(lines: list[str]) -> str | None:
    """
    Extract product name from COA lines.
    
    First looks for "Sample Name:" pattern (Gateway Labs format).
    Then looks for lines containing product type keywords (Preroll, Bud, Flower, etc.).
    """
    import re
    
    # First pass: Look for "Sample Name:" pattern (Gateway Labs, Confident, etc.)
    # This is the most reliable source - scan more lines
    for line in lines[:300]:
        line_lower = line.lower()
        if "sample name" in line_lower and ":" in line:
            # Simple approach: split on colon and take the part after it
            parts = line.split(":", 1)  # Split only on first colon
            if len(parts) == 2:
                product_name = parts[1].strip()
                # Remove pipe-delimited suffix if present (e.g., "... | Sample #: 712")
                if "|" in product_name:
                    product_name = product_name.split("|")[0].strip()
                
                # Validate length
                if len(product_name) > 3 and len(product_name) < 250:
                    return product_name
    
    # Second pass: Look for lines with product keywords
    # BUT exclude lines that are just "Type:" fields (metadata)
    product_keywords = {
        "preroll", "bud", "flower", "edible", "tincture", "oil", "extract",
        "cartridge", "concentrate", "hash", "kief", "rosin", "sauce", "shake",
        "trim", "popcorn", "smalls", "sugar", "diamond", "crumble",
        "wax", "budder", "badder", "live", "distillate",
        "isolate", "full spectrum", "broad spectrum", "capsule", "sublingual",
    }
    
    for line in lines[:100]:
        line_lower = line.lower().strip()
        
        # Skip "Type:" metadata fields (not product names)
        if line_lower.startswith("type:"):
            continue
        
        if any(keyword in line_lower for keyword in product_keywords):
            if len(line.strip()) > 10 and len(line.strip()) < 150:
                return line.strip()
    
    return None
