import shutil
import subprocess

import pytest

from lamina.ingest import read_source


def test_markdown_fences_tables_and_reference_definitions_survive(tmp_path):
    source = tmp_path / "structured.md"
    table = "| Design | Condition |\n| --- | --- |\n" + "| Blade | Low wind |\n" * 800
    source.write_text(
        "# Wind\n\n```python\n# This is code\nprint('wind')\n```\n\n"
        + table
        + "\n[ref]: https://example.org\n"
    )
    _, units = read_source(source)
    assert all(u["heading"] == "Wind" for u in units)
    assert any(table.strip() in u["text"] for u in units)
    assert "[ref]: https://example.org" in "\n".join(u["text"] for u in units)
    assert "# This is code" in units[0]["text"]


def test_pptx_keeps_table_rows_and_speaker_notes(tmp_path):
    pptx = pytest.importorskip("pptx")
    from pptx.util import Inches

    deck = pptx.Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "Blade designs"
    table = slide.shapes.add_table(
        2, 2, Inches(1), Inches(2), Inches(5), Inches(2)
    ).table
    table.cell(0, 0).text, table.cell(0, 1).text = "Design", "Condition"
    table.cell(1, 0).text, table.cell(1, 1).text = "Wide blade", "Low wind"
    slide.notes_slide.notes_text_frame.text = "Do not generalize to every turbine."
    path = tmp_path / "wind.pptx"
    deck.save(path)
    _, units = read_source(path)
    assert any("Design | Condition\nWide blade | Low wind" == u["text"] for u in units)
    assert any(
        "speaker notes" in u["locator"] and "Do not generalize" in u["text"]
        for u in units
    )


def test_local_ocr_preserves_original_identity(tmp_path):
    if not shutil.which("ocrmypdf"):
        pytest.skip("OCRmyPDF is optional")
    pytest.importorskip("pypdf")
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1800, 600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("DejaVuSans.ttf", 54)
    draw.text((100, 200), "Wind turns the blades.", fill="black", font=font)
    source = tmp_path / "scan.pdf"
    image.save(source, resolution=200)
    original = source.read_bytes()
    with pytest.raises(ValueError, match="no extractable text"):
        read_source(source)
    info, units = read_source(source, ocr=True)
    assert "Wind turns the blades" in " ".join(u["text"] for u in units)
    assert info["ocr"] is True
    assert source.read_bytes() == original
