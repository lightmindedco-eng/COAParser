from pathlib import Path

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
    output_file = output_dir / input_file.name
    assert output_file.exists()
    assert "Gateway test document" in output_file.read_text(encoding="utf-8")


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
