# Parsing and OCR

Source structure controls what can stay together during reading. The model budget controls how many complete structures fit in one request.

| Input | Parser | Retained structure |
| --- | --- | --- |
| Markdown | `markdown-it-py` | Complete paragraphs, lists, tables, code fences and block quotes; heading ancestry, reference links and source lines. |
| Text | Unicode decoding and paragraph boundaries | Complete paragraphs, available heading structure and source lines. |
| PDF | `pypdf` | Complete extracted page text and page numbers. |
| PowerPoint | `python-pptx` | Slide title, text levels, table rows/cells, grouped shapes and speaker notes. All extracted components from one slide share a group. |
| Scanned PDF | OCRmyPDF/Tesseract, then `pypdf` | A searchable text layer with page locations. |

```sh
pip install -e '.[pdf,slides]'
lamina ingest ./sources --workspace .lamina
lamina ingest scanned.pdf --ocr --workspace .lamina
```

Convert legacy `.ppt` to `.pptx`. OCRmyPDF requires local system dependencies; follow its installation guide. `--ocr` uses `--skip-text`, preserving existing text pages. It leaves the input file unchanged. Source identity uses original bytes; parsed units retain their exact source revision and locations.

A page or slide with no extractable text stops the import with its location. All files are parsed before an atomic import, so a failed batch does not publish a partial collection.

## What is a reading unit?

A Markdown table remains one table even when it is long. A paragraph remains complete even when its language uses no spaces. PowerPoint text and speaker notes remain separately citable units, but the reader receives their whole slide group. PDF pages remain complete units because this parser exposes page boundaries without claiming a reconstructed document layout.

There is no character-count slicing rule. Request packing combines these structures across headings within one source until the configured complete-request allowance is reached. A structure that cannot fit is reported with its locator. Increase the appropriate capacity or explicitly decompose the structure while retaining its relationships.

Heading ancestry and reference links retain known relationships. A page or slide boundary does not establish semantic independence. Readers can request adjacent source context when a dependency is missing; requested additions must also fit. Parsing does not infer the meaning of diagrams or establish which slides form one argument.

## OCR choice and limits

OCRmyPDF/Tesseract is the supported local route for scanned PDFs. The repository has no matched comparison establishing an OCR winner. Layout-focused alternatives such as Docling need evaluation on the actual source family before adoption.

For representative documents, check missing text, reading order, table row/column associations, numbers, symbols and captions. Include downstream writing errors, elapsed time and memory in the comparison. Accurate word recognition can still associate a value with the wrong heading.

The OCR integration test reads an original synthetic scanned sentence and checks that input bytes remain unchanged. Mixed visual/text pages can contain information this path misses. Inspect those sources or use a visual extraction workflow.

## References

- [Markdown parser](https://markdown-it-py.readthedocs.io/)
- [pypdf extraction limits](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
- [PowerPoint notes](https://python-pptx.readthedocs.io/en/latest/user/notes.html) and [tables](https://python-pptx.readthedocs.io/en/latest/user/table.html)
- [OCRmyPDF cookbook](https://ocrmypdf.readthedocs.io/en/latest/cookbook.html)
- [Docling technical report](https://arxiv.org/abs/2408.09869)
