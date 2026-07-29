#!/usr/bin/env python3
"""Check if vocabulary is loading."""
from src.parsers.base import BaseParser

parser = BaseParser()

print("VOCABULARY CHECK")
print("=" * 60)
print(f"Cannabinoids: {len(parser.vocabulary['cannabinoids'])} items")
if parser.vocabulary['cannabinoids']:
    print(f"  First 10: {parser.vocabulary['cannabinoids'][:10]}")
else:
    print("  ERROR: Empty!")

print()
print(f"Terpenes: {len(parser.vocabulary['terpenes'])} items")
if parser.vocabulary['terpenes']:
    print(f"  First 10: {parser.vocabulary['terpenes'][:10]}")
else:
    print("  ERROR: Empty!")

print()
print(f"Aliases: {len(parser.vocabulary['aliases'])} entries")
if parser.vocabulary['aliases']:
    print(f"  First 5: {list(parser.vocabulary['aliases'].items())[:5]}")
else:
    print("  ERROR: Empty!")

# Check data files exist
from pathlib import Path
print()
print("DATA FILE CHECK")
print("=" * 60)
for fname in ["cannabinoids.json", "terpenes.json", "aliases.json"]:
    fpath = Path("data") / fname
    print(f"{fname}: {'✓' if fpath.exists() else '✗ NOT FOUND'}")

# Also check portable
print()
print("PORTABLE DATA FILE CHECK")
print("=" * 60)
for fname in ["cannabinoids.json", "terpenes.json", "aliases.json"]:
    fpath = Path("portable/data") / fname
    print(f"{fname}: {'✓' if fpath.exists() else '✗ NOT FOUND'}")
