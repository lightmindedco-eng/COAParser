from pathlib import Path

from src.core.detector import detect_product_name
from src.core.extractor import read_text
from src.parser import COAParser


def test_parse_file_writes_output(tmp_path: Path) -> None:
    input_file = tmp_path / "sample.txt"
    input_file.write_text("Gateway test document\nSample line", encoding="utf-8")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    parser = COAParser()
    result = parser.parse_file(input_file, output_dir=str(output_dir))

    assert result.format_name == "gateway"
    output_files = list(output_dir.glob("*.txt"))
    assert len(output_files) == 1
    assert "Gateway test document" in output_files[0].read_text(encoding="utf-8")


def test_parse_file_extracts_compounds_from_coa_text(tmp_path: Path) -> None:
    input_file = tmp_path / "coa.txt"
    input_file.write_text(
        "Aerolabs COA\nCannabinoids:\nTHC: 18.2%\nCBD: 0.4%\nTerpenes:\nMyrcene: 0.6%\n",
        encoding="utf-8",
    )

    parser = COAParser()
    result = parser.parse_file(input_file)

    assert result.format_name == "aerolabs"
    assert any("THC" in item for item in result.items)
    assert any("Myrcene" in item for item in result.items)


def test_read_text_extracts_text_from_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n4 0 obj\n<< /Length 43 >>\nstream\nBT /F1 24 Tf 50 70 Td (THC CBD Myrcene) Tj ET\nendstream\nendobj\n5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\nxref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000062 00000 n \n0000000119 00000 n \n0000000207 00000 n \n0000000305 00000 n \ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
    )

    text = read_text(pdf_path)
    assert "THC" in text
    assert "Myrcene" in text


def test_parse_file_writes_matching_webp_for_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n4 0 obj\n<< /Length 43 >>\nstream\nBT /F1 24 Tf 50 70 Td (THC CBD Myrcene) Tj ET\nendstream\nendobj\n5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\nxref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000062 00000 n \n0000000119 00000 n \n0000000207 00000 n \n0000000305 00000 n \ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
    )

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    parser = COAParser()
    result = parser.parse_file(pdf_path, output_dir=str(output_dir))

    assert result.output_path is not None
    assert result.webp_path is not None

    from PIL import Image

    txt_path = Path(result.output_path)
    webp_path = Path(result.webp_path)
    assert txt_path.suffix == ".txt"
    assert webp_path.suffix == ".webp"
    assert webp_path.stem == txt_path.stem

    image = Image.open(webp_path)
    assert image.format == "WEBP"
    assert image.width > 0 and image.height > 0


def test_detect_product_name_keeps_pipe_flavors() -> None:
    """A 'Sample Name:' like 'DELIGHT | TRUFFLE CAKE' must keep the pipe-delimited
    flavor instead of truncating to just 'DELIGHT'."""
    lines = ["Certificate of Analysis", "Sample Name: DELIGHT | TRUFFLE CAKE", "Type: Vape Cartridges"]
    assert detect_product_name(lines) == "Delight | Truffle Cake"


def test_detect_product_name_strips_glued_metadata_pipe() -> None:
    """A pipe suffix that is metadata (e.g. '| Sample #: 1046') is still stripped."""
    lines = ["Certificate of Analysis", "Sample Name: Snow Monkey Bulk | Sample #: 1046", "Type: Bulk Concentrate"]
    assert detect_product_name(lines) == "Snow Monkey Bulk"


def test_detect_product_name_metis_mg_dash_no_potency_keyword() -> None:
    """Metis QA product line with mg potency + dash but no THC/CBD keyword must be
    returned instead of the Client/license/address block."""
    lines = [
        "Regulatory Compliance Testing", "1 of 2", "Metis QA Laboratory",
        "10001 Broadway Extension", "Oklahoma City, OK 73114", "(405) 605-0952",
        "https://www.metisqalab.com/", "Lic# LAAA-LTKC-8XIM",
        "WL Mango Chili 100mg - Individual",
        "METRC Sample: 1A40E0100004B19000045324; METRC Batch: 1A40E0100004B19000045297",
        "Sample ID: 2501DML0005.0014", "Strain: Mango Chili", "Matrix: Ingestible",
        "Type: Soft Chew", "Sample Size: 1 units; Batch:", "Completed: 01/08/2025",
        "Batch#: WLG-MC-100-02", "Client", "JKJ PROCESSING INC",
        "Lic. # PAAA-4JJF-VKHP", "4301 WILL ROGERS PKWY", "OKLAHOMA CITY, OK 73108",
        "Cannabinoids", "Complete", "Analyte", "LOQ", "Result", "%", "mg/g",
    ]
    assert detect_product_name(lines) == "WL Mango Chili 100mg - Individual"


def test_detect_product_name_mg_dash_without_potency_keyword() -> None:
    """Product line with mg potency + dash separator but no THC/CBD keyword is caught
    before the Strain look-ahead can append the METRC category line."""
    lines = [
        "Certificate of Analysis", "Powered by Confident LIMS", "1 of 2", "Some Labs LLC",
        "LM | Mango - 250mg", "Ingestible, Soft Chew", "Strain: Mango",
        "Batch#: MM-1", "METRC Sample: X; METRC Source: Y", "Cannabinoids", "Complete",
    ]
    assert detect_product_name(lines) == "LM | Mango - 250mg"


def test_detect_product_name_ratio_potency_colon() -> None:
    """A potency-ratio colon early in the line (e.g. '25:5mg ...') must not be treated
    as a label prefix, so the full product line is returned."""
    lines = [
        "Certificate of Analysis", "Powered by Confident LIMS", "1 of 2", "OPERATING MFG, LLC",
        "Sample: 2511OKCTL3416.29166",
        "25:5mg Watermelon THC Gummies (50: 10mg | 500:100mg Packs)",
        "Strain: Watermelon", "Ingestible, Soft Chew;", "Sample Weight: 20 units",
        "Cannabinoids", "Complete",
    ]
    assert detect_product_name(lines) == "25:5mg Watermelon THC Gummies (50: 10mg | 500:100mg Packs)"


def test_detect_product_name_does_not_join_metrc_category() -> None:
    """Pass 3 look-ahead must stop at a METRC category line ('Ingestible, ...') instead
    of appending it to the product name."""
    lines = [
        "Certificate of Analysis", "Powered by Confident LIMS", "1 of 2", "TPC Holdings LLC",
        "Sample: 2601SL0154.0942", "Strain: Benevolent Bakery | Wake N Bake Pancake Mix | 13 oz",
        "Batch#: BB.PANCAKE.1000.OK.001; Harvest Process Lot:", "Primary Sample Weight: 1 units",
        "Benevolent Bakery | Wake N Bake Pancake Mix | 13 oz", "Ingestible, Baked Goods",
        "METRC Sample: 1A40E01000020EC000010705; METRC Source: 1A40E01000020EC000009870",
        "Cannabinoids", "Analytical Date: 01/30/2026; Analyst: ehs",
    ]
    assert detect_product_name(lines) == "Benevolent Bakery | Wake N Bake Pancake Mix | 13 oz"
