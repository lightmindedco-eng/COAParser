# Batch Processing Guide

## Overview

The batch processing feature allows you to process multiple COA PDFs at once and generate verification reports organized by lab/format.

## Usage

### Basic Batch Processing

```bash
# Process all PDFs in the Input directory
python batch_process.py Input

# Process with custom output directory
python batch_process.py Input -o Results

# Or from portable version
cd portable
python batch_process.py Input -o Output
```

### Command Line Arguments

```
batch_process.py INPUT_DIR [-o OUTPUT_DIR]

Positional Arguments:
  INPUT_DIR          Directory containing PDF files to process

Optional Arguments:
  -o, --output       Output directory for reports (default: Output)
  -h, --help         Show this help message
```

## Output

The batch processor generates:

1. **Individual Report Files**: One `.txt` file per PDF with extracted compounds
2. **batch_summary.json**: JSON file with processing statistics
3. **Console Summary**: Organized by lab/format showing:
   - Total files processed
   - Success/failure counts
   - Success rate percentage
   - Average compound count per lab
   - List of successful and failed files

## Example Output

```
================================================================================
COAParser Batch Processing
================================================================================
Input directory: Input
Output directory: Output
Total PDFs to process: 24

[1/24] Processing: COA_001.pdf... ✓ confident (32 compounds)
[2/24] Processing: COA_002.pdf... ✓ gateway (28 compounds)
[3/24] Processing: COA_003.pdf... ✓ aerolabs (25 compounds)
...

================================================================================
BATCH PROCESSING SUMMARY
================================================================================

Total Processed: 24
Total Failed: 0
Success Rate: 100.0%

Results by Lab/Format:
--------------------------------------------------------------------------------

CONFIDENT
  Total: 12
  Successful: 12
  Failed: 0
  Average compounds: 31.5
  Files:
    - COA_001.pdf (32 compounds)
    - COA_004.pdf (31 compounds)
    ... and 10 more

GATEWAY
  Total: 8
  Successful: 8
  Failed: 0
  Average compounds: 28.1
  Files:
    - COA_002.pdf (28 compounds)
    ... and 7 more

AEROLABS
  Total: 4
  Successful: 4
  Failed: 0
  Average compounds: 25.0
  Files:
    - COA_003.pdf (25 compounds)
    ... and 3 more

================================================================================
```

## JSON Summary Format

```json
{
  "total_processed": 24,
  "total_failed": 0,
  "success_rate": 1.0,
  "by_lab": {
    "confident": [
      {
        "file": "COA_001.pdf",
        "product_name": "Sweet Cherry 100mg THC",
        "compound_count": 32,
        "output_file": "Output/COA_001.txt",
        "status": "success"
      }
    ],
    "gateway": [...],
    "aerolabs": [...]
  }
}
```

## Verification Workflow

1. **Organize PDFs**: Place all PDFs to test in a single Input directory
2. **Run Batch Processing**: `python batch_process.py Input`
3. **Review Summary**: Check console output and `batch_summary.json`
4. **Check Lab Performance**:
   - Which labs have high success rates?
   - Which labs need training/refinement?
5. **Review Failed Files**: Check the error messages for files that failed
6. **Examine Output Files**: Look at individual `.txt` files to verify:
   - Product names extracted correctly
   - Compounds properly identified
   - Percentages are accurate
   - Terpenes vs Cannabinoids correctly categorized

## Tips for Lab Evaluation

### Identifying Lab Issues

1. **Look at batch_summary.json** for labs with:
   - Low success rate (failures indicate parsing issues)
   - High/low compound counts (might indicate missing/extra extractions)
   - Specific error patterns

2. **Review individual output files**:
   - Check product names for company prefix removal
   - Verify compound percentages (should be reasonable: 0.01% - 100%)
   - Ensure terpenes and cannabinoids are correctly separated

3. **Common Issues by Lab**:
   - **Aerolabs**: Look for format consistency
   - **Gateway**: Check decimal/value placement
   - **Confident**: Verify Greek letter handling

## Scaling Up

The batch processor handles large batches efficiently:
- Processes PDFs sequentially
- Reports progress in real-time
- Generates comprehensive statistics
- Minimal memory usage per file

For very large batches (1000+ PDFs), consider:
- Running multiple batch_process.py instances on different input subdirectories
- Post-processing the JSON summaries to compare results

## Next Steps

After batch processing:
1. Review batch_summary.json for lab breakdowns
2. Examine failed files to identify patterns
3. Update parsers based on issues found
4. Re-run batch processing on updated parsers
5. Compare success rates over time

