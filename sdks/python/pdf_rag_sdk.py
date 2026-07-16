"""
PDF RAG Pipeline — Python SDK

Provides a clean, high-level SDK interface for processing PDFs for RAG pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Generator

from pdf_rag_pipeline import PDFPipeline as _CorePipeline
from pdf_rag_pipeline.models import (
    BoundingBox,
    DocumentElement,
    ElementType,
    ExtractionResult,
    TableData,
)


@dataclass
class PDFRAGConfig:
    """Configuration for the PDF RAG Pipeline."""
    enable_ocr: bool = True
    ocr_language: str = "eng"
    ocr_dpi: int = 300
    enable_tables: bool = True
    enable_layout_detection: bool = True
    enable_tagging: bool = False
    output_dir: str | None = None
    include_bbox_comments: bool = True
    tesseract_cmd: str | None = None
    max_pages: int | None = 50
    max_workers: int = 4
    chunk_size: int = 20


@dataclass
class PDFRAGResult:
    """High-level result wrapper for the Python SDK."""
    file_path: str
    page_count: int
    markdown: str
    json: str
    elements: list[DocumentElement] = field(default_factory=list)
    tables: list[TableData] = field(default_factory=list)
    raw: ExtractionResult | None = None

    def save_markdown(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.markdown)
        return path

    def save_json(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.json)
        return path

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "page_count": self.page_count,
            "markdown": self.markdown,
            "json": self.json,
            "elements": [e.to_dict() for e in self.elements],
            "tables": [t.to_dict() for t in self.tables],
        }


class Client:
    """PDF RAG Pipeline Python SDK Client.

    Usage:
        client = Client()
        result = client.process("document.pdf")
        print(result.markdown)
        result.save_json("output.json")
    """

    def __init__(self, config: PDFRAGConfig | None = None):
        self.config = config or PDFRAGConfig()

    def _make_pipeline(self) -> _CorePipeline:
        return _CorePipeline(
            enable_ocr=self.config.enable_ocr,
            ocr_language=self.config.ocr_language,
            ocr_dpi=self.config.ocr_dpi,
            enable_tables=self.config.enable_tables,
            enable_layout_detection=self.config.enable_layout_detection,
            enable_tagging=self.config.enable_tagging,
            output_dir=self.config.output_dir,
            tesseract_cmd=self.config.tesseract_cmd,
            max_pages=self.config.max_pages,
            max_workers=self.config.max_workers,
            chunk_size=self.config.chunk_size,
            md_kwargs={"include_bbox_comment": self.config.include_bbox_comments},
        )

    def process(
        self,
        file_path: str,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> PDFRAGResult:
        """Process a PDF file through the full pipeline.

        Args:
            file_path: Path to the PDF.
            on_progress: Optional callback(current, total, status) for progress.

        For large documents use process_stream() or process_parallel().
        """
        pipeline = self._make_pipeline()
        result = pipeline.process(file_path, on_progress=on_progress)
        return self._wrap_result(result)

    def process_to_markdown(
        self, file_path: str, on_progress: Callable[[int, int, str], None] | None = None,
    ) -> str:
        """Process a PDF and return only the Markdown output."""
        return self.process(file_path, on_progress=on_progress).markdown

    def process_to_json(
        self, file_path: str, on_progress: Callable[[int, int, str], None] | None = None,
    ) -> str:
        """Process a PDF and return only the JSON output."""
        return self.process(file_path, on_progress=on_progress).json

    def process_stream(
        self,
        file_path: str,
        chunk_size: int | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Process a PDF in streaming chunks. Yields partial results.

        Each yielded dict: {page_start, page_end, elements, tables, markdown}

        Yields:
            dict with keys page_start, page_end, elements, tables, markdown
        """
        pipeline = self._make_pipeline()
        yield from pipeline.process_stream(file_path, chunk_size=chunk_size)

    def process_parallel(
        self,
        file_path: str,
        workers: int | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> PDFRAGResult:
        """Process a PDF using parallel workers for faster throughput on large docs."""
        pipeline = self._make_pipeline()
        result = pipeline.process_parallel(
            file_path, workers=workers, on_progress=on_progress,
        )
        return self._wrap_result(result)

    def process_batch(
        self, file_paths: list[str],
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[PDFRAGResult]:
        """Process multiple PDF files."""
        return [self.process(fp, on_progress=on_progress) for fp in file_paths]

    def generate_tagged_pdf(self, input_path: str, output_path: str) -> str:
        pipeline = _CorePipeline(enable_tagging=True, output_dir=self.config.output_dir)
        return pipeline.generate_tagged_pdf(input_path, output_path)

    @staticmethod
    def _wrap_result(result: ExtractionResult) -> PDFRAGResult:
        return PDFRAGResult(
            file_path=result.file_path,
            page_count=result.page_count,
            markdown=result.markdown,
            json=result.to_json(),
            elements=result.elements,
            tables=result.tables,
            raw=result,
        )


def process_pdf(
    file_path: str,
    enable_ocr: bool = True,
    enable_tables: bool = True,
    enable_layout: bool = True,
    ocr_language: str = "eng",
    tesseract_cmd: str | None = None,
    max_pages: int | None = 50,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> PDFRAGResult:
    """Convenience function for quick PDF processing.

    Args:
        file_path: Path to the PDF file.
        enable_ocr: Enable OCR for scanned documents.
        enable_tables: Enable table extraction.
        enable_layout: Enable layout analysis (columns, reading order).
        ocr_language: Tesseract language code.
        tesseract_cmd: Path to tesseract executable (if not in PATH).
        max_pages: Maximum pages to process (None = unlimited).
        on_progress: Optional callback(current, total, status) for progress.

    Returns:
        PDFRAGResult with markdown, json, and structured data.
    """
    config = PDFRAGConfig(
        enable_ocr=enable_ocr,
        enable_tables=enable_tables,
        enable_layout_detection=enable_layout,
        ocr_language=ocr_language,
        tesseract_cmd=tesseract_cmd,
        max_pages=max_pages,
    )
    return Client(config).process(file_path, on_progress=on_progress)


__all__ = [
    "Client",
    "PDFRAGConfig",
    "PDFRAGResult",
    "process_pdf",
    "BoundingBox",
    "DocumentElement",
    "ElementType",
    "TableData",
]
