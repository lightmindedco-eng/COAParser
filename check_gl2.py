import sys
sys.stdout.reconfigure(encoding="utf-8")
from src.parser import read_text, extract_text
content = read_text(r"Input\1A40E01000021A9000022595.pdf")
lines = extract_text(content)
for i, line in enumerate(lines):
    print(f"{i:4d}: {line}")
