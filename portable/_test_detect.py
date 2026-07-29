import sys; sys.path.insert(0, "src")
from src.core.extractor import extract_text, read_text
from src.core.detector import detect_company_name, detect_product_name

for f in ["Input/1A40E010000421F000224971.pdf", "Input/20073_092325BVR4-092325WIR4_1A40E01000149B3000001639.pdf"]:
    lines = extract_text(read_text(f))
    co = detect_company_name(lines)
    pr = detect_product_name(lines)
    print(f"{f.split('/')[-1]}: co={co}  pr={pr}")
