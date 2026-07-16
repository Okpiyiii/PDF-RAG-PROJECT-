# PDF RAG Pipeline

A high-accuracy PDF processing engine built for RAG (Retrieval-Augmented Generation) pipelines. Extracts structured content with precise bounding box coordinates, handles complex layouts, and works with scanned documents.

## Features

- **Structured extraction** — extracts headings, paragraphs, lists, tables, code blocks, and more into Markdown and JSON
- **Bounding box metadata** — every element includes page and (x0, y0, x1, y1) coordinates for source citation
- **Multi-column layout detection** — histogram-based column detection with correct reading order across columns
- **Table extraction** — handles both bordered and borderless tables via pdfplumber's line/text alignment strategies
- **OCR pipeline** — Tesseract-based OCR with image preprocessing for scanned documents
- **Accessibility tagging** — generates screen-reader-friendly tagged PDFs (PDF/UA)
- **SDKs for Python and Node.js** — idiomatic, async-friendly APIs for both ecosystems

## Architecture

```
pdf_rag_pipeline/
├── __init__.py          # Public API
├── models.py            # BoundingBox, DocumentElement, TableData, ElementType
├── parser.py            # PyMuPDF text block extraction with bbox
├── layout.py            # Column detection and reading order
├── classifier.py        # Element type classification (heading, list, paragraph, etc.)
├── tables.py            # Table extraction (bordered + borderless)
├── ocr.py               # Tesseract OCR pipeline for scanned PDFs
├── tagging.py           # Accessible tagged PDF generation
├── exporters.py         # Markdown and JSON exporters
└── pipeline.py          # Main orchestrator
```

## Installation

```bash
# Clone and install the engine
pip install -e .

# For OCR support, install Tesseract:
# macOS:   brew install tesseract
# Ubuntu:  sudo apt install tesseract-ocr
# Windows: download from https://github.com/UB-Mannheim/tesseract/wiki

# Additional languages (optional):
# sudo apt install tesseract-ocr-{fra,deu,spa}  # French, German, Spanish
```

## Quick Start

### Python SDK

```python
from sdks.python.pdf_rag_sdk import Client

client = Client()
result = client.process("document.pdf")

print(result.markdown)
print(result.json)

# Access structured data
for element in result.elements:
    print(f"{element.type}: {element.text}")
    print(f"  Location: page {element.bbox.page}, "
          f"({element.bbox.x0}, {element.bbox.y0}) -> "
          f"({element.bbox.x1}, {element.bbox.y1})")

# Save to files
result.save_markdown("output.md")
result.save_json("output.json")
```

### Convenience function

```python
from sdks.python.pdf_rag_sdk import process_pdf

result = process_pdf("document.pdf", enable_ocr=True)
print(result.markdown)
```

### Node.js SDK

```javascript
const { PDFRAGClient } = require("./sdks/node");

const client = new PDFRAGClient();
const result = await client.process("./document.pdf");

console.log(result.markdown);

// Save results
await client.saveMarkdown(result, "./output.md");
await client.saveJSON(result, "./output.json");
```

### Direct engine usage

```python
from pdf_rag_pipeline import PDFPipeline

pipeline = PDFPipeline()
result = pipeline.process("document.pdf")

print(result.markdown)
print(result.to_json())

# Generate accessible tagged PDF
pipeline.generate_tagged_pdf("document.pdf", "document_tagged.pdf")
```

## Configuration

```python
from sdks.python.pdf_rag_sdk import PDFRAGConfig, Client

config = PDFRAGConfig(
    enable_ocr=True,           # OCR for scanned docs
    ocr_language="eng",        # Tesseract language code
    ocr_dpi=300,               # OCR rendering resolution
    enable_tables=True,        # Table extraction
    enable_layout_detection=True,  # Multi-column support
    enable_tagging=True,       # Generate tagged PDF
    output_dir="./output",     # Output directory
    include_bbox_comments=True, # Include bbox in Markdown comments
)

client = Client(config)
result = client.process("document.pdf")
```

## JSON Output Structure

```json
{
  "file_path": "/path/to/document.pdf",
  "page_count": 12,
  "elements": [
    {
      "type": "heading",
      "text": "Introduction",
      "bbox": { "page": 0, "x0": 72.0, "y0": 680.5, "x1": 450.3, "y1": 708.2 },
      "metadata": { "block_number": 0 }
    },
    {
      "type": "paragraph",
      "text": "This is the first paragraph...",
      "bbox": { "page": 0, "x0": 72.0, "y0": 640.1, "x1": 504.0, "y1": 672.0 },
      "metadata": { "block_number": 1 }
    }
  ],
  "tables": [
    {
      "rows": [["Name", "Value"], ["Alice", "42"]],
      "bbox": { "page": 3, "x0": 100.0, "y0": 400.0, "x1": 500.0, "y1": 520.0 },
      "column_headers": ["Name", "Value"],
      "row_headers": []
    }
  ],
  "markdown": "## Introduction\n\nThis is the first paragraph...\n\n| Name | Value |\n| --- | --- |\n| Alice | 42 |"
}
```

## Requirements

- Python 3.8+
- Tesseract OCR (optional, for scanned documents)
- Node.js 16+ (for Node.js SDK)
