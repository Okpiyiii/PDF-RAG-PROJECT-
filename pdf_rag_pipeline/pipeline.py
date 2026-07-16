from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Generator

from .classifier import ElementClassifier
from .exporters import JSONExporter, MarkdownExporter
from .layout import LayoutAnalyzer
from .models import DocumentElement, ExtractionResult, TableData
from .ocr import OCRPipeline
from .parser import PDFParser
from .tables import TableExtractor
from .tagging import TaggedPDFGenerator


ProgressCallback = Callable[[int, int, str], None] | None


class PDFPipeline:
    """Main pipeline orchestrator for PDF processing.

    Usage:
        # Simple — processes up to max_pages (default 50), blocks until done
        result = pipeline.process("document.pdf")

        # Chunked — processes in batches, yields partial results as a generator
        for chunk in pipeline.process_stream("large.pdf", chunk_size=20):
            print(f"Page {chunk['page_start']}-{chunk['page_end']} done")

        # Parallel — uses thread pool for concurrent page processing
        result = pipeline.process_parallel("large.pdf", workers=4)

        # Progress callback
        def on_progress(current, total, status):
            print(f"[{current}/{total}] {status}")

        result = pipeline.process("doc.pdf", on_progress=on_progress)
    """

    def __init__(
        self,
        enable_ocr: bool = True,
        ocr_language: str = "eng",
        ocr_dpi: int = 300,
        enable_tables: bool = True,
        enable_layout_detection: bool = True,
        enable_tagging: bool = False,
        output_dir: str | None = None,
        tesseract_cmd: str | None = None,
        max_pages: int | None = 50,
        max_workers: int = 4,
        chunk_size: int = 20,
        **kwargs: Any,
    ):
        self.enable_ocr = enable_ocr
        self.ocr_language = ocr_language
        self.ocr_dpi = ocr_dpi
        self.enable_tables = enable_tables
        self.enable_layout_detection = enable_layout_detection
        self.enable_tagging = enable_tagging
        self.output_dir = output_dir
        self.tesseract_cmd = tesseract_cmd
        self.max_pages = max_pages
        self.max_workers = max_workers
        self.chunk_size = chunk_size

        self._classifier = ElementClassifier(**kwargs.get("classifier_kwargs", {}))
        self._layout_analyzer = LayoutAnalyzer(**kwargs.get("layout_kwargs", {}))
        self._table_extractor = TableExtractor(**kwargs.get("table_kwargs", {}))
        self._ocr = OCRPipeline(
            dpi=self.ocr_dpi,
            language=self.ocr_language,
            tesseract_cmd=self.tesseract_cmd,
            **kwargs.get("ocr_kwargs", {}),
        )
        self._md_exporter = MarkdownExporter(**kwargs.get("md_kwargs", {}))
        self._json_exporter = JSONExporter()
        self._tagger = TaggedPDFGenerator(**kwargs.get("tagger_kwargs", {}))

    def __enter__(self) -> "PDFPipeline":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def process(
        self,
        file_path: str,
        on_progress: ProgressCallback = None,
    ) -> ExtractionResult:
        """Run the pipeline on a PDF. Uses chunked processing internally.

        For large documents use process_stream() or process_parallel().
        """
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF not found: {file_path}")

        with PDFParser(file_path) as parser:
            total_pages = parser.page_count
            pages_to_process = self._resolve_page_count(total_pages)

        elements: list[DocumentElement] = []
        tables: list[TableData] = []

        for chunk in self._process_chunks(file_path, pages_to_process, on_progress):
            elements.extend(chunk["elements"])
            tables.extend(chunk["tables"])

        # Merge consecutive paragraphs
        elements = self._classifier.merge_consecutive_paragraphs(elements)

        # Tagged PDF
        if self.enable_tagging and self.output_dir:
            tagged_path = os.path.join(
                self.output_dir,
                os.path.splitext(os.path.basename(file_path))[0] + "_tagged.pdf",
            )
            self._tagger.generate(file_path, tagged_path)

        markdown = self._md_exporter.export(elements, tables)
        truncated = self.max_pages and total_pages > self.max_pages

        result = ExtractionResult(
            file_path=file_path,
            page_count=total_pages,
            elements=elements,
            tables=tables,
            markdown=markdown,
        )
        if truncated:
            result.markdown = (
                f"<!-- ⚠ Only first {pages_to_process} of {total_pages} pages processed. "
                f"Adjust max_pages to process more. -->\n\n" + result.markdown
            )

        return result

    def process_stream(
        self,
        file_path: str,
        chunk_size: int | None = None,
        on_progress: ProgressCallback = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Process a PDF in streaming chunks. Yields partial results per chunk.

        Each yielded dict contains: page_start, page_end, elements, tables, markdown.

        Yields:
            dict with keys: page_start, page_end, elements, tables, markdown
        """
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF not found: {file_path}")

        with PDFParser(file_path) as parser:
            total_pages = parser.page_count
        pages_to_process = self._resolve_page_count(total_pages)
        chunk_size = chunk_size or self.chunk_size

        elements_batch: list[DocumentElement] = []
        tables_batch: list[TableData] = []
        current_start = 0

        for chunk in self._process_chunks(file_path, pages_to_process, on_progress):
            elements_batch.extend(chunk["elements"])
            tables_batch.extend(chunk["tables"])
            current_start = min(current_start or chunk["page_start"], chunk["page_start"])

            # Yield when batch is full
            if len(elements_batch) >= chunk_size * 5 or chunk["page_end"] == pages_to_process - 1:
                elements_batch = self._classifier.merge_consecutive_paragraphs(elements_batch)
                yield {
                    "page_start": current_start,
                    "page_end": chunk["page_end"],
                    "elements": elements_batch,
                    "tables": tables_batch,
                    "markdown": self._md_exporter.export(elements_batch, tables_batch),
                }
                elements_batch = []
                tables_batch = []
                current_start = chunk["page_end"] + 1

    def process_parallel(
        self,
        file_path: str,
        workers: int | None = None,
        on_progress: ProgressCallback = None,
    ) -> ExtractionResult:
        """Process a PDF using parallel workers. Each worker handles one page.

        Best for CPU-bound docs (OCR, heavy layout) with many pages.
        """
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF not found: {file_path}")

        with PDFParser(file_path) as parser:
            total_pages = parser.page_count
        pages_to_process = self._resolve_page_count(total_pages)
        workers = workers or self.max_workers

        elements: list[DocumentElement] = []
        tables: list[TableData] = []
        completed = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._process_page, file_path, pn): pn
                for pn in range(pages_to_process)
            }

            for future in as_completed(futures):
                pn = futures[future]
                try:
                    page_elements, page_tables = future.result()
                    if page_elements:
                        elements.extend(page_elements)
                    if page_tables:
                        tables.extend(page_tables)
                except Exception:
                    pass

                completed += 1
                if on_progress:
                    on_progress(completed, pages_to_process, "page processed")

        elements.sort(key=lambda e: (e.bbox.page, e.bbox.y0, e.bbox.x0))
        tables.sort(key=lambda t: t.bbox.page)

        elements = self._classifier.merge_consecutive_paragraphs(elements)

        markdown = self._md_exporter.export(elements, tables)
        truncated = self.max_pages and total_pages > self.max_pages

        result = ExtractionResult(
            file_path=file_path,
            page_count=total_pages,
            elements=elements,
            tables=tables,
            markdown=markdown,
        )
        if truncated:
            result.markdown = (
                f"<!-- ⚠ Only first {pages_to_process} of {total_pages} pages processed. -->\n\n"
                + result.markdown
            )
        return result

    def _process_chunks(
        self,
        file_path: str,
        pages_to_process: int,
        on_progress: ProgressCallback = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Internal: process pages in chunk_size batches, yielding per-chunk results."""
        chunk_size = self.chunk_size
        total_chunks = (pages_to_process + chunk_size - 1) // chunk_size

        for chunk_idx in range(total_chunks):
            page_start = chunk_idx * chunk_size
            page_end = min(page_start + chunk_size - 1, pages_to_process - 1)
            page_range = list(range(page_start, page_end + 1))

            if on_progress:
                on_progress(page_start + 1, pages_to_process, "extracting text blocks")

            page_elements: list[DocumentElement] = []

            for pn in page_range:
                el, _ = self._process_page(file_path, pn)
                page_elements.extend(el)

            if on_progress:
                on_progress(page_end + 1, pages_to_process, "extracting tables")

            page_tables = (
                self._table_extractor.extract_tables_from_pages(file_path, page_range)
                if self.enable_tables
                else []
            )

            yield {
                "page_start": page_start,
                "page_end": page_end,
                "elements": page_elements,
                "tables": page_tables,
            }

    def _process_page(
        self, file_path: str, page_num: int,
    ) -> tuple[list[DocumentElement], list[TableData]]:
        """Process a single page — parse, layout, classify, OCR if scanned.
        Returns (elements, tables). Designed to be called from parallel workers."""
        elements: list[DocumentElement] = []
        tables: list[TableData] = []

        try:
            with PDFParser(file_path) as parser:
                width, height = parser.get_page_size(page_num)
                raw_blocks = parser.extract_text_blocks(page_num)
                if not raw_blocks:
                    return elements, tables

                if self.enable_layout_detection:
                    layout = self._layout_analyzer.analyze_page(
                        page_num, width, height, raw_blocks,
                    )
                    ordered_blocks = self._layout_analyzer.get_reading_order(
                        raw_blocks, layout.columns, height,
                    )
                else:
                    ordered_blocks = raw_blocks

                if parser.is_scanned() and self.enable_ocr:
                    ocr_blocks = self._ocr.process(file_path, [page_num])
                    ordered_blocks = self._merge_blocks(ordered_blocks, ocr_blocks)

                elements = self._classifier.classify(
                    ordered_blocks, width, height, page_num,
                )

            if self.enable_tables:
                tables = self._table_extractor.extract_tables_from_page(
                    file_path, page_num,
                )

        except Exception:
            pass

        return elements, tables

    def _resolve_page_count(self, total_pages: int) -> int:
        return min(total_pages, self.max_pages) if self.max_pages else total_pages

    def process_to_json(self, file_path: str, on_progress: ProgressCallback = None) -> str:
        result = self.process(file_path, on_progress=on_progress)
        return result.to_json()

    def process_to_markdown(self, file_path: str, on_progress: ProgressCallback = None) -> str:
        result = self.process(file_path, on_progress=on_progress)
        return result.markdown

    @staticmethod
    def _merge_blocks(
        original: list[dict[str, Any]],
        ocr_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not ocr_results:
            return original
        if not original:
            return [
                {"text": r["text"], "bbox": r["bbox"], "block_number": i, "block_type": 0}
                for i, r in enumerate(ocr_results)
            ]
        return original

    def generate_tagged_pdf(self, input_path: str, output_path: str) -> str:
        return self._tagger.generate(input_path, output_path)
