#!/usr/bin/env python3
"""CLI for PDF RAG Pipeline — process PDFs directly from the command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdf_rag_pipeline import PDFPipeline


def main():
    parser = argparse.ArgumentParser(
        description="PDF RAG Pipeline — extract structured content from PDFs",
    )
    parser.add_argument("input", help="Path to the PDF file")
    parser.add_argument("-o", "--output", default=None, help="Output file (default: stdout)")
    parser.add_argument(
        "--format", choices=["md", "markdown", "json"], default="md",
        help="Output format (default: md)",
    )
    parser.add_argument(
        "--no-ocr", action="store_true", help="Disable OCR for scanned documents",
    )
    parser.add_argument(
        "--no-tables", action="store_true", help="Disable table extraction",
    )
    parser.add_argument(
        "--no-layout", action="store_true", help="Disable layout/column detection",
    )
    parser.add_argument(
        "--max-pages", type=int, default=50,
        help="Maximum pages to process (default: 50, use 0 for unlimited)",
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="Number of parallel workers (default: 4)",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=20,
        help="Pages per chunk for streaming (default: 20)",
    )
    parser.add_argument(
        "--tesseract-cmd", default=None,
        help="Path to tesseract executable",
    )
    parser.add_argument(
        "--tagged", default=None, metavar="OUTPUT.pdf",
        help="Generate accessible tagged PDF to this path",
    )

    args = parser.parse_args()
    max_pages = args.max_pages if args.max_pages > 0 else None

    pipeline = PDFPipeline(
        enable_ocr=not args.no_ocr,
        enable_tables=not args.no_tables,
        enable_layout_detection=not args.no_layout,
        tesseract_cmd=args.tesseract_cmd,
        max_pages=max_pages,
        max_workers=args.workers,
        chunk_size=args.chunk_size,
    )

    result = pipeline.process(args.input)

    fmt = args.format
    if fmt in ("json",):
        output = result.to_json()
    else:
        output = result.markdown

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Output written to {args.output}", file=sys.stderr)
    else:
        print(output)

    if args.tagged:
        pipeline.generate_tagged_pdf(args.input, args.tagged)
        print(f"Tagged PDF written to {args.tagged}", file=sys.stderr)


if __name__ == "__main__":
    main()
