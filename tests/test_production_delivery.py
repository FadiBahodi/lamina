import base64
import io
import json
import wave

from lamina.production_delivery import deliver_production
from lamina.production_export import document_html, export_production
from lamina.store import Workspace


def _receipt():
    return {
        "status": "ready",
        "title": "Lease safety",
        "format": "podcast-script",
        "markdown": "# Lease safety\n\nKeep the **token** with the write.\n\n- Reject stale writes.\n- Retry with current ownership.\n",
    }


def test_audio_delivery_reports_failure_without_losing_finished_document(tmp_path):
    class Broken:
        identity = "broken-speech"

        def call(self, stage, payload):
            raise RuntimeError("private provider configuration")

    receipt = _receipt()
    links = deliver_production(
        Workspace(tmp_path / "state"),
        receipt,
        {},
        tmp_path / "out",
        audio_provider=Broken(),
    )
    report = json.loads((tmp_path / "out" / links["report"]).read_text())
    assert report["status"] == "review"
    assert report["audio_delivery"]["status"] == "review"
    assert "private provider" not in str(report)
    assert (tmp_path / "out" / links["document"]).read_text() == receipt["markdown"]
    assert "audio" not in links


def test_audio_delivery_ready_manifest_is_in_final_report(tmp_path):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)

    class Speech:
        identity = "fixture-pcm"

        def call(self, stage, payload):
            return {
                "wav_base64": base64.b64encode(stream.getvalue()).decode(),
                "spoken_text": "Keep the token.",
            }

    receipt = _receipt()
    links = deliver_production(
        Workspace(tmp_path / "state"),
        receipt,
        {},
        tmp_path / "out",
        audio_provider=Speech(),
    )
    report = json.loads((tmp_path / "out" / links["report"]).read_text())
    assert report["audio_delivery"]["status"] == "ready"
    assert report["audio_delivery"]["audio"]["duration_seconds"] == 0.1
    assert (tmp_path / "out" / links["audio"]).read_bytes() == stream.getvalue()


def test_markdown_export_preserves_structure_and_makes_authored_html_inert(tmp_path):
    markdown = """# Structured document

**Important** and *specific*.

1. Read first.
2. Act second.

| Signal | Response |
| --- | --- |
| stale | reject |

```python
assert token > previous
```

<script>alert('bad')</script>
![Source figure](https://invalid.example/image.png)
"""
    html = document_html(markdown, "Document")
    assert "<strong>Important</strong>" in html
    assert "<ol>" in html and "<table>" in html
    assert "<script>" not in html
    assert "<img" not in html and "Image reference: Source figure" in html
    receipt = {**_receipt(), "format": "document", "markdown": markdown}
    links = export_production(receipt, {}, tmp_path)
    if "pdf" in links:
        from pypdf import PdfReader

        text = " ".join(
            page.extract_text() for page in PdfReader(tmp_path / links["pdf"]).pages
        )
        assert "Important" in text and "stale" in text and "reject" in text
        assert "Read first" in text and "Act second" in text


def test_candidate_exports_do_not_include_private_examiner_answer(tmp_path):
    receipt = {
        **_receipt(),
        "format": "assessment",
        "title": "SECRET diagnosis",
        "markdown": "# Practice assessment\n\n## Question 1\n\nWhat do you do?",
        "candidate_markdown": "# Practice assessment\n\nWhat do you do?",
        "examiner_markdown": "# Examiner\n\nSECRET answer",
    }
    links = export_production(receipt, {}, tmp_path)
    assert "SECRET" not in (tmp_path / links["reader"]).read_text()
    assert "SECRET" not in (tmp_path / links["candidate"]).read_text()
    assert "SECRET answer" in (tmp_path / links["examiner"]).read_text()
    if "pdf" in links:
        from pypdf import PdfReader

        assert "SECRET" not in " ".join(
            p.extract_text() for p in PdfReader(tmp_path / links["pdf"]).pages
        )


def test_long_table_row_can_continue_across_pdf_pages(tmp_path):
    import pytest

    pytest.importorskip("reportlab")
    from pypdf import PdfReader

    details = "A condition retains its exception and source reference. " * 240
    receipt = {
        **_receipt(),
        "format": "guide",
        "markdown": "# Long reference\n\n| Topic | Detail |\n|---|---|\n| Ownership | "
        + details
        + "Final qualifier preserved. |\n",
    }
    links = export_production(receipt, {}, tmp_path)
    pdf = PdfReader(tmp_path / links["pdf"])
    assert len(pdf.pages) > 1
    assert "Final qualifier preserved" in " ".join(
        page.extract_text() for page in pdf.pages
    )
