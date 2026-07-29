# COAParser Quick Start Guide

## What is COAParser?

COAParser extracts compound data (cannabinoids and terpenes) from cannabis Certificate of Analysis (COA) PDFs. It supports multiple lab formats and now includes batch processing for large-scale lab verification.

## Installation

### Requirements
- Python 3.8+
- pip (Python package manager)

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# For OCR support (optional but recommended)
pip install pytesseract
# Then install Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
```

## Quick Usage

### Single File Processing
```bash
python app.py
# Then select a PDF file in the GUI
```

Or command-line:
```bash
python -c "from src.parser import COAParser; p = COAParser(); r = p.parse_file('path/to/pdf.pdf'); print(r)"
```

### Batch Processing (New!)

Process multiple PDFs at once and get a lab-organized summary:

```bash
# Basic usage
python batch_process.py Input

# With custom output directory
python batch_process.py Input -o Results

# From portable version
cd portable
python batch_process.py Input -o Output
```

### What You Get

1. **Individual Report Files** (.txt)
   - One file per PDF
   - Separated cannabinoids and terpenes
   - Extracted compound percentages

2. **Batch Summary** (batch_summary.json)
   - Total files processed
   - Success/failure counts
   - Results organized by lab format
   - Statistics per lab

3. **Console Output**
   - Real-time progress [N/M]
   - Lab format identification
   - Compound count per file
   - Error reporting

## Example Workflow

```bash
# Step 1: Organize your PDFs
# Put all PDFs to test in: Input/ directory

# Step 2: Run batch processing
python batch_process.py Input

# Step 3: Review results
# Check console output for lab breakdown
# Open batch_summary.json for detailed stats
# Review .txt files in Output/ for extracted data

# Step 4: Identify issues
# Look for labs with low success rates
# Check failed files for error patterns
# Verify compound extraction accuracy

# Step 5: Report findings
# Note which labs need training/refinement
# Request targeted parser updates
```

## Supported Lab Formats

- **Aerolabs**: Standard format with column-based layout
- **Gateway Labs**: Multi-line value extraction
- **Confident Cannabis**: Greek letter compound names
- **Havard Industries (Condent LIMS)**: Inline and line-by-line formats

## File Structure

```
COAParser/
├── app.py                    # GUI application
├── batch_process.py          # Batch processing CLI tool
├── src/
│   ├── parser.py            # Main parser entry point
│   ├── core/
│   │   ├── detector.py      # Format detection
│   │   ├── extractor.py     # Data extraction
│   │   └── normalizer.py    # Data normalization
│   └── parsers/
│       ├── aerolabs.py      # Aerolabs format
│       ├── gateway.py       # Gateway Labs format
│       ├── confident.py     # Confident Cannabis format
│       └── base.py          # Base parser class
├── data/
│   ├── cannabinoids.json    # Cannabinoid vocabulary
│   ├── terpenes.json        # Terpene vocabulary
│   └── aliases.json         # Alternative names
├── Input/                   # Place PDFs here
├── Output/                  # Generated reports go here
└── Logs/                    # Processing logs
```

## Common Issues

### OCR Not Working
- Make sure Tesseract OCR is installed
- Update pytesseract: `pip install --upgrade pytesseract`
- Check Tesseract path in config.json

### Parser Not Recognizing Format
- Check if lab is supported (Aerolabs, Gateway, Confident, Havard)
- Review the output file to see what was detected
- Report the issue with a sample PDF

### Batch Processing Errors
- Check that PDFs are valid (can open in Adobe Reader)
- Verify input directory path
- Review batch_summary.json for specific errors

## Testing

Run the included test to verify setup:
```bash
python -m pytest tests/
```

## Next Steps

1. **Place test PDFs** in the Input/ directory
2. **Run batch processing** to test your PDF collection
3. **Review results** in Output/ and batch_summary.json
4. **Identify issues** and request parser refinements
5. **Re-run batch** to verify improvements

## Support

- Check BATCH_PROCESSING.md for detailed batch processing guide
- Review README.md for full documentation
- Check individual parser files for format-specific details

## Success Criteria

✓ Batch processing completes without errors
✓ All PDFs produce output files
✓ Summary shows success rate
✓ Compound names and percentages match PDFs
✓ Terpenes separated from cannabinoids

