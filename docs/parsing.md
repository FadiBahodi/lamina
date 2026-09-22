# Parsing and OCR

Use a file's existing structure before asking a model to rediscover it.

| Input | Library | Structure retained |
| --- | --- | --- |
| Markdown | `markdown-it-py` | Headings, complete lists, tables, code fences and source lines. |
| Text | Unicode decoding and bounded spans | Paragraph boundaries where available; line locations. |
| PDF | `pypdf` | Extractable page text and page numbers. |
| PowerPoint | `python-pptx` | Slide titles, text levels, table rows/cells, grouped shapes and speaker notes. |
| Scanned PDF | `ocrmypdf --skip-text`, then `pypdf` | Existing text pages remain intact; OCR supplies text on scanned pages. |

Install format support with `pip install -e '.[pdf,slides]'`. Convert legacy `.ppt` to `.pptx`. OCRmyPDF needs local system dependencies; follow its installation guide.

```sh
lamina ingest ./sources --workspace .lamina
lamina ingest scanned.pdf --ocr --workspace .lamina
```

`--ocr` is local and explicit. The input is not overwritten. Source identity uses original bytes; extracted text and page locations are stored separately. A PDF page or slide with no extractable text fails the import rather than disappearing. The batch is parsed before an atomic import, so failure does not publish a partial collection.

The parser packs complete Markdown blocks with a 12,000-character target. Oversized paragraphs can split; lists, tables and fences remain intact. A block larger than a model request budget fails rather than being truncated. This target is a packing choice, not a token budget or difficulty estimate.

## Choosing an OCR tool

There is no measured universal winner in this repository. OCRmyPDF/Tesseract is the supported path for adding a searchable text layer locally. Docling is a candidate when layout, reading order and table reconstruction are central; it adds model dependencies and needs evaluation on the actual document family. Recognizing printed words does not establish that a chart or diagram was understood.

Compare representative native PDFs, scans, dense tables and slides. Check missing text, reading order, row/column association, numbers, symbols, captions, elapsed time and memory. Measure downstream answer errors too: accurate word recognition can still pair a value with the wrong heading.

The OCR test uses an original synthetic scanned sentence. It checks integration and preservation of input bytes, not engine rankings. Mixed visual/text pages can contain information this text path misses; inspect such material or use a visual extraction workflow.

## References

- [Markdown parser](https://markdown-it-py.readthedocs.io/)
- [pypdf extraction limits](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
- [PowerPoint notes](https://python-pptx.readthedocs.io/en/latest/user/notes.html) and [tables](https://python-pptx.readthedocs.io/en/latest/user/table.html)
- [OCRmyPDF cookbook](https://ocrmypdf.readthedocs.io/en/latest/cookbook.html)
- [Docling technical report](https://arxiv.org/abs/2408.09869)
