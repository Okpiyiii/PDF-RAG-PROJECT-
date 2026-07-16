from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_from_directory, stream_with_context

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdf_rag_pipeline import PDFPipeline

app = Flask(__name__, template_folder="templates", static_folder="static")

UPLOAD_FOLDER = Path(tempfile.gettempdir()) / "pdf_rag_uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


def get_pipeline(config: dict) -> PDFPipeline:
    return PDFPipeline(
        enable_ocr=config.get("enable_ocr", True),
        ocr_language=config.get("ocr_language", "eng"),
        ocr_dpi=config.get("ocr_dpi", 300),
        enable_tables=config.get("enable_tables", True),
        enable_layout_detection=config.get("enable_layout_detection", True),
        tesseract_cmd=config.get("tesseract_cmd"),
        output_dir=config.get("output_dir"),
        max_pages=config.get("max_pages"),
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported"}), 400

    file_id = uuid.uuid4().hex
    upload_path = UPLOAD_FOLDER / f"{file_id}.pdf"
    file.save(upload_path)

    return jsonify({
        "file_id": file_id,
        "filename": file.filename,
    })


@app.route("/api/process/<file_id>", methods=["POST"])
def process(file_id):
    upload_path = UPLOAD_FOLDER / f"{file_id}.pdf"
    if not upload_path.exists():
        return jsonify({"error": "File not found. Upload first."}), 404

    config = request.get_json(silent=True) or {}

    try:
        pipeline = get_pipeline(config)
        result = pipeline.process(str(upload_path))
        truncated = pipeline.max_pages and result.page_count > pipeline.max_pages
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "file_id": file_id,
        "page_count": result.page_count,
        "pages_processed": min(result.page_count, pipeline.max_pages) if pipeline.max_pages else result.page_count,
        "truncated": truncated,
        "markdown": result.markdown,
        "elements": [e.to_dict() for e in result.elements],
        "tables": [t.to_dict() for t in result.tables],
    })


@app.route("/api/process-stream/<file_id>", methods=["POST"])
def process_stream(file_id):
    """Server-Sent Events endpoint — streams chunks as they're processed."""
    upload_path = UPLOAD_FOLDER / f"{file_id}.pdf"
    if not upload_path.exists():
        return jsonify({"error": "File not found. Upload first."}), 404

    config = request.get_json(silent=True) or {}
    pipeline = get_pipeline(config)

    def generate():
        try:
            for chunk in pipeline.process_stream(str(upload_path)):
                payload = {
                    "page_start": chunk["page_start"],
                    "page_end": chunk["page_end"],
                    "elements": [e.to_dict() for e in chunk["elements"]],
                    "tables": [t.to_dict() for t in chunk["tables"]],
                    "markdown": chunk["markdown"],
                }
                yield f"data: {json.dumps(payload)}\n\n"
            yield "data: {\"done\": true}\n\n"
        except Exception as e:
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/preview/<file_id>")
def preview(file_id):
    upload_path = UPLOAD_FOLDER / f"{file_id}.pdf"
    if not upload_path.exists():
        return jsonify({"error": "File not found"}), 404

    return send_from_directory(str(UPLOAD_FOLDER), f"{file_id}.pdf")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="PDF RAG Pipeline Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    print(f"\n  PDF RAG Pipeline Web UI")
    print(f"  http://{args.host}:{args.port}\n")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
