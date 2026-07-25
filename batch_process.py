#!/usr/bin/env python3
"CLI wrapper for batch processing. Core logic lives in src/core/batch.py."

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from core.batch import BatchProcessor


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch process COA PDFs and generate reports")
    parser.add_argument("input_dir", help="Directory containing PDF files to process")
    parser.add_argument("-o", "--output", default="Output", help="Output directory (default: Output)")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"Error: not a directory: {input_dir}")
        return 1

    def _progress(cur, tot, name):
        print(f"[{cur}/{tot}] {name}")

    processor = BatchProcessor(input_dir, args.output, progress_callback=_progress)
    result = processor.process_batch()

    print(f"Summary saved to: {Path(args.output) / 'batch_summary.json'}")
    for line in processor.summary_lines():
        print(line)

    return 0 if result['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

