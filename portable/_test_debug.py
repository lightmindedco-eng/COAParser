import sys; sys.path.insert(0, "src")
from src.core.extractor import extract_text, read_text
from src.core.detector import _looks_like_company_name

# Check the Regulatory Compliance PDF lines
lines = extract_text(read_text("Input/1A40E010000421F000224971.pdf"))
print("=== Pass 0 candidates (lines before cert/CoA) ===")
for i in range(min(10, len(lines))):
    cand = lines[i].strip()
    looks = _looks_like_company_name(cand)
    wc = len(cand.split())
    print(f"  {i}: {repr(cand)}  words={wc}  looks_like={looks}")

print()
print("=== Full line list with context ===")
for i, l in enumerate(lines[:35]):
    print(f"  {i}: {repr(l)}")
