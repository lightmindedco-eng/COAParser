import sys
sys.stdout.reconfigure(encoding="utf-8")
from src.parser import read_text, detect_format
text = read_text(r"Input\1A40E01000021A9000024440.pdf")
print("Detected format:", detect_format(text))
print()
print(text[:3000])
