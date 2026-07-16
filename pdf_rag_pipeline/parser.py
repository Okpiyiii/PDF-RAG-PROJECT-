from __future__ import annotations

from typing import Any

import fitz  # PyMuPDF

from .models import BoundingBox


class PDFParser:
    """Low-level PDF reader that extracts text blocks with bounding boxes using PyMuPDF.

    Provides word-level, block-level, and span-level detail with exact coordinates.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._doc: fitz.Document | None = None

    def __enter__(self) -> "PDFParser":
        self._doc = fitz.open(self.file_path)
        return self

    def __exit__(self, *args: Any) -> None:
        if self._doc:
            self._doc.close()

    @property
    def doc(self) -> fitz.Document:
        if self._doc is None:
            raise RuntimeError("PDFParser must be used as a context manager or .open() called")
        return self._doc

    def open(self) -> "PDFParser":
        self._doc = fitz.open(self.file_path)
        return self

    def close(self) -> None:
        if self._doc:
            self._doc.close()
            self._doc = None

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    def get_page_size(self, page_number: int) -> tuple[float, float]:
        """Return (width, height) of the page."""
        page = self.doc[page_number]
        rect = page.rect
        return rect.width, rect.height

    def extract_text_blocks(self, page_number: int) -> list[dict[str, Any]]:
        """Extract text blocks with bbox from a single page.

        Returns list of dicts: {text, bbox: BoundingBox, block_number, block_type}
        """
        page = self.doc[page_number]
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        result = []

        for block_idx, block in enumerate(blocks):
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    spans_text = []
                    bbox_min = None
                    for span in line["spans"]:
                        spans_text.append(span["text"])
                        sb = fitz.Rect(span["bbox"])
                        if bbox_min is None:
                            bbox_min = sb
                        else:
                            bbox_min |= sb

                    line_text = "".join(spans_text).strip()
                    if line_text and bbox_min:
                        result.append({
                            "text": line_text,
                            "bbox": BoundingBox(
                                page=page_number,
                                x0=bbox_min.x0,
                                y0=bbox_min.y0,
                                x1=bbox_min.x1,
                                y1=bbox_min.y1,
                            ),
                            "block_number": block_idx,
                            "block_type": block["type"],
                        })
            elif block["type"] == 1:  # image block
                result.append({
                    "text": "",
                    "bbox": BoundingBox(
                        page=page_number,
                        x0=block["bbox"][0],
                        y0=block["bbox"][1],
                        x1=block["bbox"][2],
                        y1=block["bbox"][3],
                    ),
                    "block_number": block_idx,
                    "block_type": 1,
                })

        return result

    def extract_text_blocks_all(self) -> list[dict[str, Any]]:
        """Extract text blocks from all pages."""
        all_blocks = []
        for p in range(self.page_count):
            all_blocks.extend(self.extract_text_blocks(p))
        return all_blocks

    def get_raw_text(self) -> str:
        """Get full document text (no bbox)."""
        return "\n".join(self.doc[p].get_text() for p in range(self.page_count))

    def extract_images(self, page_number: int) -> list[dict[str, Any]]:
        """Extract image references with bbox from a page."""
        page = self.doc[page_number]
        images = page.get_image_info(xrefs=True)
        result = []
        for img in images:
            result.append({
                "xref": img["xref"],
                "width": img["width"],
                "height": img["height"],
                "bbox": BoundingBox(
                    page=page_number,
                    x0=img["bbox"][0],
                    y0=img["bbox"][1],
                    x1=img["bbox"][2],
                    y1=img["bbox"][3],
                ),
            })
        return result

    def is_scanned(self, sample_pages: int = 3) -> bool:
        """Heuristic check — if sampled pages have very little extractable text, likely scanned."""
        pages_to_check = min(sample_pages, self.page_count)
        total_chars = 0
        for p in range(pages_to_check):
            text = self.doc[p].get_text().strip()
            total_chars += len(text)
        avg_chars = total_chars / pages_to_check if pages_to_check > 0 else 0
        return avg_chars < 100
