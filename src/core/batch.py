"""Batch processing logic for COAParser."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Callable, DefaultDict


class BatchProcessor:
    """Process multiple COA PDFs and generate a summary organized by lab."""

    def __init__(
        self,
        input_dir: str | Path,
        output_dir: str | Path,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> None:
        from src.parser import COAParser

        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.parser = COAParser()
        self.progress_callback = progress_callback

        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.results_by_lab: DefaultDict[str, list] = defaultdict(list)
        self.total_processed = 0
        self.total_failed = 0

    def process_batch(self) -> dict:
        """Process all PDFs in input_dir. Returns summary dict."""
        pdf_files = sorted(self.input_dir.glob("*.pdf"))

        if not pdf_files:
            return {"total": 0, "failed": 0, "by_lab": {}}

        total = len(pdf_files)
        for i, pdf_file in enumerate(pdf_files, 1):
            self._process_file(pdf_file, i, total)

        self._save_summary()

        return {
            "total": self.total_processed,
            "failed": self.total_failed,
            "by_lab": dict(self.results_by_lab),
        }

    def _process_file(self, pdf_file: Path, current: int, total: int) -> None:
        if self.progress_callback:
            self.progress_callback(current, total, pdf_file.name)

        try:
            result = self.parser.parse_file(pdf_file, output_dir=str(self.output_dir))
            self.total_processed += 1
            lab_name = result.format_name or "unknown"
            self.results_by_lab[lab_name].append({
                "file": pdf_file.name,
                "product_name": result.metadata.get("product_name", "Unknown"),
                "compound_count": len(result.items),
                "output_file": result.output_path or "N/A",
                "status": "success",
            })
        except Exception as exc:
            self.total_failed += 1
            self.results_by_lab["error"].append({
                "file": pdf_file.name,
                "error": str(exc),
                "status": "failed",
            })

    def _save_summary(self) -> None:
        summary = {
            "total_processed": self.total_processed,
            "total_failed": self.total_failed,
            "success_rate": (
                (self.total_processed - self.total_failed) / max(1, self.total_processed)
            ),
            "by_lab": dict(self.results_by_lab),
        }
        summary_path = self.output_dir / "batch_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

    def summary_lines(self) -> list[str]:
        """Return a human-readable summary as a list of strings."""
        lines: list[str] = []
        total = self.total_processed
        failed = self.total_failed
        success_rate = (total - failed) / max(1, total) * 100

        lines.append(f"Processed: {total}  |  Failed: {failed}  |  Success: {success_rate:.1f}%")
        lines.append("")

        for lab_name in sorted(self.results_by_lab.keys()):
            files = self.results_by_lab[lab_name]
            successful = [f for f in files if f.get("status") == "success"]
            n_failed = len(files) - len(successful)

            lines.append(f"[{lab_name.upper()}]  {len(successful)} OK, {n_failed} failed")
            for f in successful[:5]:
                lines.append(f"  {f['file']}  ({f.get('compound_count', '?')} compounds)")
            if len(successful) > 5:
                lines.append(f"  ... and {len(successful) - 5} more")
            for f in files:
                if f.get("status") == "failed":
                    lines.append(f"  [FAIL] {f['file']}: {f.get('error', '')[:60]}")

        return lines
