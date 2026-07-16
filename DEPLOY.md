# Deployment

## 1. Local dev (what you've been doing)

```bash
cd web_ui
python app.py
# → http://127.0.0.1:5000
```

## 2. Production — Windows

```bash
# One-time setup
pip install -r requirements.txt
pip install -e .

# Run production server (waitress)
python prod_server.py
# → http://0.0.0.0:5000 (4 workers)
```

Set `HOST`, `PORT`, `WORKERS` env vars to configure.

## 3. Production — Linux / cloud VM

```bash
pip install -r requirements.txt
pip install -e .

# Production with gunicorn
python prod_server.py
# Or directly:
gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 300 web_ui.app:app
```

## 4. Docker (any platform)

```bash
# Build and run
docker compose up -d
# → http://localhost:5000

# Scale workers
docker compose up -d --scale web=3

# View logs
docker compose logs -f
```

## 5. Library mode (use as a Python package)

```bash
pip install -e .
```

```python
from sdks.python.pdf_rag_sdk import Client, PDFRAGConfig

config = PDFRAGConfig(max_pages=200, max_workers=8)
client = Client(config)

# Blocking
result = client.process("doc.pdf")

# Streaming (for large files)
for chunk in client.process_stream("huge.pdf"):
    print(f"Pages {chunk['page_start']}-{chunk['page_end']} done")

# Parallel workers
result = client.process_parallel("large.pdf", workers=8)
```

## 6. CLI

```bash
pip install -e .

# Markdown output to stdout
pdf-rag document.pdf

# JSON output
pdf-rag document.pdf --format json -o output.json

# Process 500 pages with 8 workers, no OCR
pdf-rag large.pdf --max-pages 500 --workers 8 --no-ocr -o output.md

# Generate tagged PDF
pdf-rag document.pdf --tagged document_accessible.pdf
```

## 7. Node.js SDK

```bash
cd sdks/node
npm install
```

```javascript
const { PDFRAGClient } = require("./sdks/node");

const client = new PDFRAGClient({ maxPages: 200 });
const result = await client.process("./document.pdf");
console.log(result.markdown);
```

## Configuration reference

| Option | Default | Description |
|--------|---------|-------------|
| `max_pages` | 50 | Max pages to process (`None` = unlimited) |
| `max_workers` | 4 | Parallel workers for process_parallel |
| `chunk_size` | 20 | Pages per batch in streaming mode |
| `enable_ocr` | true | OCR for scanned documents |
| `enable_tables` | true | Table extraction |
| `enable_layout_detection` | true | Column/reading-order detection |
| `tesseract_cmd` | null | Path to tesseract binary |
| `ocr_dpi` | 300 | Render resolution for OCR |

## Tesseract setup

- **Docker**: included automatically
- **Ubuntu**: `sudo apt install tesseract-ocr`
- **macOS**: `brew install tesseract`
- **Windows**: download from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki), set `tesseract_cmd` config or add to PATH

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | 0.0.0.0 | Server bind address |
| `PORT` | 5000 | Server port |
| `WORKERS` | 4 | Number of wsgi workers |
