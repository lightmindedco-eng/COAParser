#!/usr/bin/env python3
"""CLI wrapper for batch processing. Core logic lives in src/core/batch.py."""

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

    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

    def __init__(self, input_dir: str | Path, output_dir: str | Path):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.parser = COAParser()
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Track results by lab
        self.results_by_lab: DefaultDict[str, list] = defaultdict(list)
        self.total_processed = 0
        self.total_failed = 0
    
    def process_batch(self) -> dict:
        """Process all PDFs in the input directory."""
        pdf_files = sorted(self.input_dir.glob("*.pdf"))
        
        if not pdf_files:
            print(f"No PDF files found in {self.input_dir}")
            return {"total": 0, "failed": 0, "by_lab": {}}
        
        print(f"\n{'='*80}")
        print(f"COAParser Batch Processing")
        print(f"{'='*80}")
        print(f"Input directory: {self.input_dir}")
        print(f"Output directory: {self.output_dir}")
        print(f"Total PDFs to process: {len(pdf_files)}\n")
        
        for i, pdf_file in enumerate(pdf_files, 1):
            self._process_file(pdf_file, i, len(pdf_files))
        
        # Generate summary report
        self._print_summary()
        self._save_summary()
        
        return {
            "total": self.total_processed,
            "failed": self.total_failed,
            "by_lab": dict(self.results_by_lab),
        }
    
    def _process_file(self, pdf_file: Path, current: int, total: int) -> None:
        """Process a single PDF file."""
        try:
            print(f"[{current}/{total}] Processing: {pdf_file.name}...", end=" ")
            
            result = self.parser.parse_file(pdf_file, output_dir=str(self.output_dir))
            
            self.total_processed += 1
            
            # Track by lab/format
            lab_name = result.format_name or "unknown"
            
            self.results_by_lab[lab_name].append({
                "file": pdf_file.name,
                "product_name": result.metadata.get("product_name", "Unknown"),
                "compound_count": len(result.items),
                "output_file": result.output_path or "N/A",
                "status": "success",
            })
            
            print(f"[OK] {lab_name} ({len(result.items)} compounds)")
            
        except Exception as e:
            print(f"[FAIL] ERROR: {str(e)[:50]}")
            self.total_failed += 1
            
            lab_name = "error"
            self.results_by_lab[lab_name].append({
                "file": pdf_file.name,
                "error": str(e),
                "status": "failed",
            })
    
    def _print_summary(self) -> None:
        """Print a summary of processed files by lab."""
        print(f"\n{'='*80}")
        print("BATCH PROCESSING SUMMARY")
        print(f"{'='*80}\n")
        
        print(f"Total Processed: {self.total_processed}")
        print(f"Total Failed: {self.total_failed}")
        print(f"Success Rate: {(self.total_processed - self.total_failed) / max(1, self.total_processed) * 100:.1f}%\n")
        
        print("Results by Lab/Format:")
        print("-" * 80)
        
        for lab_name in sorted(self.results_by_lab.keys()):
            files = self.results_by_lab[lab_name]
            successful = [f for f in files if f.get("status") == "success"]
            failed = len(files) - len(successful)
            
            print(f"\n{lab_name.upper()}")
            print(f"  Total: {len(files)}")
            print(f"  Successful: {len(successful)}")
            print(f"  Failed: {failed}")
            
            if successful:
                print(f"  Average compounds: {sum(f.get('compound_count', 0) for f in successful) / len(successful):.1f}")
                print(f"  Files:")
                for f in successful[:5]:  # Show first 5
                    print(f"    - {f['file']} ({f.get('compound_count', '?')} compounds)")
                if len(successful) > 5:
                    print(f"    ... and {len(successful) - 5} more")
            
            if failed:
                print(f"  Failed files:")
                for f in files:
                    if f.get("status") == "failed":
                        print(f"    - {f['file']}: {f.get('error', 'Unknown error')[:60]}")
        
        print(f"\n{'='*80}\n")
    
    def _save_summary(self) -> None:
        """Save a JSON summary of the batch processing results."""
        summary = {
            "total_processed": self.total_processed,
            "total_failed": self.total_failed,
            "success_rate": (self.total_processed - self.total_failed) / max(1, self.total_processed),
            "by_lab": dict(self.results_by_lab),
        }
        
        summary_path = self.output_dir / "batch_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        
        print(f"Summary saved to: {summary_path}")


def main() -> int:
    """Main entry point for batch processing."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Batch process COA PDFs and generate reports"
    )
    parser.add_argument(
        "input_dir",
        help="Directory containing PDF files to process",
    )
    parser.add_argument(
        "-o", "--output",
        default="Output",
        help="Output directory for reports (default: Output)",
    )
    
    args = parser.parse_args()
    
    # Verify input directory exists
    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"Error: Input directory not found: {input_dir}")
        return 1
    
    if not input_dir.is_dir():
        print(f"Error: Not a directory: {input_dir}")
        return 1
    
    # Run batch processing
    processor = BatchProcessor(input_dir, args.output)
    result = processor.process_batch()
    
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
