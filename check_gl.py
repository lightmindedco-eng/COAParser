import sys
sys.stdout.reconfigure(encoding="utf-8")
from src.parser import read_text, extract_text
from src.parsers.greenleaf import GreenleafParser

content = read_text(r"Input\1A40E01000021A9000024440.pdf")
lines = extract_text(content)
parser = GreenleafParser()
r = parser.parse(lines)
for item in r["items"]:
    print(item)
