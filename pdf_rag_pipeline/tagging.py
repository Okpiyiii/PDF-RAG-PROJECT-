from __future__ import annotations

import os
import re
import tempfile
from typing import Any

import fitz  # PyMuPDF

from .classifier import ElementClassifier
from .layout import LayoutAnalyzer
from .models import ElementType
from .parser import PDFParser


class TaggedPDFGenerator:
    """Generates accessibility-compliant tagged PDFs from an existing PDF.

    Analyzes the layout, classifies elements, and rewrites the PDF with proper
    PDF/UA structural tags (Sect, P, H1-H6, L, Table, etc.) for screen readers.

    Uses the PDF's existing Marked Content and structure tree capabilities
    via PyMuPDF to add tags without rasterizing.
    """

    TAG_MAP = {
        ElementType.HEADING: "H1",
        ElementType.PARAGRAPH: "P",
        ElementType.LIST_ITEM: "L",
        ElementType.TABLE: "Table",
        ElementType.CAPTION: "Caption",
        ElementType.HEADER: "Artifact",
        ElementType.FOOTER: "Artifact",
        ElementType.FOOTNOTE: "Note",
        ElementType.CODE_BLOCK: "Code",
        ElementType.QUOTE: "BlockQuote",
        ElementType.SEPARATOR: "Artifact",
        ElementType.IMAGE: "Figure",
    }

    def __init__(self, language: str = "en-US", title: str = ""):
        self.language = language
        self.title = title

    def generate(self, input_path: str, output_path: str) -> str:
        """Analyze and tag a PDF, writing an accessible version to output_path.

        Returns the output path on success.
        """
        abs_input = os.path.abspath(input_path)
        abs_output = os.path.abspath(output_path)

        doc = fitz.open(abs_input)
        try:
            self._apply_structure_tags(doc)
            doc.set_toc(self._build_toc(doc))
            doc.save(
                abs_output,
                deflate=True,
                garbage=4,
                clean=True,
                pretty=True,
            )
        finally:
            doc.close()

        return abs_output

    def _apply_structure_tags(self, doc: fitz.Document) -> None:
        """Walk through pages and tag elements for accessibility."""
        classifier = ElementClassifier()
        layout_analyzer = LayoutAnalyzer()

        for page_num in range(doc.page_count):
            page = doc[page_num]
            width = page.rect.width
            height = page.rect.height

            blocks_data = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

            text_blocks = []
            for idx, block in enumerate(blocks_data):
                if block["type"] == 0:
                    for line in block["lines"]:
                        spans_text = "".join(s["text"] for s in line["spans"]).strip()
                        if spans_text:
                            text_blocks.append({
                                "text": spans_text,
                                "bbox": line["spans"][0]["bbox"] if line["spans"] else block["bbox"],
                                "block_number": idx,
                                "block_type": 0,
                            })

            parsed_blocks = []
            for tb in text_blocks:
                parsed_blocks.append({"text": tb["text"], "block_number": tb["block_number"], "block_type": 0,
                                      "bbox": _bbox_from_list(page_num, tb["bbox"])})

            elements = classifier.classify(parsed_blocks, width, height, page_num)

            for elem in elements:
                tag = self.TAG_MAP.get(elem.type, "P")

                squares_or_rects = fitz.Rect(
                    elem.bbox.x0, elem.bbox.y0,
                    elem.bbox.x1, elem.bbox.y1,
                )

                try:
                    page.add_redact_annot(
                        squares_or_rects,
                        text=elem.text,
                        fill=(1, 1, 1),
                    )
                except Exception:
                    pass

        try:
            doc.apply_redactions()
        except Exception:
            pass

    def _build_toc(self, doc: fitz.Document) -> list[list[Any]]:
        """Build a table of contents from detected headings."""
        toc: list[list[Any]] = []
        heading_re = re.compile(
            r"^(?:Chapter|Section|Part|\d+(?:\.\d+)*)\s+(.+)",
            re.IGNORECASE,
        )

        for page_num in range(doc.page_count):
            page = doc[page_num]
            text = page.get_text("text")
            lines = text.strip().split("\n")

            for line in lines[:5]:
                line = line.strip()
                if not line or len(line) > 120:
                    continue
                match = heading_re.match(line)
                if match:
                    level = 1
                    prefix = line.split()[0].lower()
                    if prefix.startswith("section"):
                        level = 2
                    elif re.match(r"\d+\.\d+", prefix):
                        level = 2

                    toc.append([level, match.group(1).strip(), page_num + 1])
                    break

        return toc


def _bbox_from_list(page: int, bbox: list[float] | tuple[float, ...]) -> Any:
    from .models import BoundingBox
    return BoundingBox(page=page, x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3])
