from __future__ import annotations

import re
from typing import Any

from .models import BoundingBox, DocumentElement, ElementType


class ElementClassifier:
    """Classifies raw text blocks into structured document elements.
    
    Uses font metrics, positional heuristics, text patterns, and spacing
    to determine element types: headings, paragraphs, lists, etc.
    """

    def __init__(
        self,
        heading_font_threshold: float = 1.15,
        list_patterns: list[str] | None = None,
    ):
        self.heading_font_threshold = heading_font_threshold
        self.list_patterns = list_patterns or [
            r"^\s*(?:[-•●○◆◇▪▹►]\s)",
            r"^\s*(?:\d+[.)]\s)",
            r"^\s*(?:[a-zA-Z][.)]\s)",
            r"^\s*(?:\([a-zA-Z\d]+\)\s)",
        ]
        self._list_regex = re.compile("|".join(self.list_patterns))

    def classify(
        self,
        text_blocks: list[dict[str, Any]],
        page_width: float,
        page_height: float,
        page_number: int = 0,
        font_sizes: list[float] | None = None,
    ) -> list[DocumentElement]:
        """Classify a list of text blocks into DocumentElements."""
        if not text_blocks:
            return []

        font_info = self._compute_font_stats(text_blocks, font_sizes)
        elements: list[DocumentElement] = []

        for block in text_blocks:
            text = block["text"]
            bbox = block["bbox"]
            element_type = self._classify_block(text, bbox, font_info, page_width, page_height)

            metadata = {
                "block_number": block.get("block_number", -1),
            }

            elements.append(
                DocumentElement(
                    type=element_type,
                    text=text,
                    bbox=bbox,
                    metadata=metadata,
                )
            )

        return elements

    def _compute_font_stats(
        self,
        blocks: list[dict[str, Any]],
        font_sizes_override: list[float] | None,
    ) -> dict[str, Any]:
        """Compute font statistics used for heading detection."""
        all_font_sizes: list[float] = []
        all_text_lengths = []

        for block in blocks:
            text = block["text"].strip()
            all_text_lengths.append(len(text))
            if "font_size" in block.get("metadata", {}):
                all_font_sizes.append(block["metadata"]["font_size"])
            elif font_sizes_override:
                # Use bbox height as font size proxy if no explicit font
                all_font_sizes.append(
                    font_sizes_override[len(all_font_sizes) % len(font_sizes_override)]
                )
            else:
                # Approximate font size from bbox height
                all_font_sizes.append(block["bbox"].height * 0.75)

        body_size = self._body_font_size(all_font_sizes)
        avg_len = (
            sum(all_text_lengths) / len(all_text_lengths)
            if all_text_lengths
            else 0
        )

        return {
            "body_font_size": body_size,
            "heading_threshold": body_size * self.heading_font_threshold,
            "avg_text_length": avg_len,
            "all_font_sizes": all_font_sizes,
        }

    def _body_font_size(self, sizes: list[float]) -> float:
        if not sizes:
            return 12.0
        sorted_sizes = sorted(sizes)
        n = len(sorted_sizes)
        if n <= 3:
            return sorted_sizes[len(sorted_sizes) // 2]
        q25 = sorted_sizes[n // 4]
        q75 = sorted_sizes[3 * n // 4]
        return sorted(
            [s for s in sorted_sizes if q25 <= s <= q75],
            key=lambda s: abs(s - sorted_sizes[n // 2]),
        )[0] if sorted_sizes else sorted_sizes[0]

    def _classify_block(
        self,
        text: str,
        bbox: BoundingBox,
        font_info: dict[str, Any],
        page_width: float,
        page_height: float,
    ) -> ElementType:
        text_stripped = text.strip()
        if not text_stripped:
            return ElementType.PARAGRAPH

        # CODE_BLOCK detection — monospace indicator via starting spaces/tabs
        if text.startswith(("    ", "\t")) or text.startswith("```"):
            return ElementType.CODE_BLOCK

        # HEADING detection
        heading_type = self._detect_heading(text_stripped, bbox, font_info, page_width)
        if heading_type is not None:
            return heading_type

        # LIST_ITEM detection
        if self._is_list_item(text_stripped):
            return ElementType.LIST_ITEM

        # FOOTNOTE check — small text near bottom of page
        if self._is_footnote(bbox, font_info, page_height):
            return ElementType.FOOTNOTE

        # HEADER/FOOTER check — edge of page
        if self._is_header_footer(bbox, page_height):
            return ElementType.HEADER if bbox.y0 > page_height * 0.9 else ElementType.FOOTER

        # CAPTION — short text near an image or table bbox overlap isn't tracked here
        if self._is_caption(text_stripped):
            return ElementType.CAPTION

        # QUOTE detection
        if self._is_quote(text_stripped):
            return ElementType.QUOTE

        # SEPARATOR
        if self._is_separator(text_stripped):
            return ElementType.SEPARATOR

        return ElementType.PARAGRAPH

    def _detect_heading(
        self,
        text: str,
        bbox: BoundingBox,
        font_info: dict[str, Any],
        page_width: float,
    ) -> ElementType | None:
        fs = font_info["all_font_sizes"]
        threshold = font_info["heading_threshold"]
        body_size = font_info["body_font_size"]

        bbox_font_proxy = bbox.height * 0.75

        # Chunk-labeled headings are unambiguous
        heading_patterns = [
            (r"^(?:chapter|section)\s+\d+", True),
            (r"^(?:abstract|references?|bibliography|appendix)\b", True),
            (r"^\d+(?:\.\d+)*\s+[A-Z]", True),
        ]
        for pattern, _ in heading_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return ElementType.HEADING

        # Font-size based heading
        if bbox_font_proxy > threshold * 1.1 and len(text) < 120:
            return ElementType.HEADING

        # Short, centered, bold-text heuristics
        is_short = len(text) < 80
        is_bold_text = text == text.upper() and len(text) > 3
        is_centered = abs((bbox.x0 + bbox.width / 2) - (page_width / 2)) < page_width * 0.15
        is_numbered = bool(re.match(r"^\d+(?:\.\d+)*\s", text))

        if is_short and (is_bold_text or is_numbered or (is_centered and bbox_font_proxy > body_size)):
            return ElementType.HEADING

        return None

    def _is_list_item(self, text: str) -> bool:
        return bool(self._list_regex.match(text))

    def _is_footnote(self, bbox: BoundingBox, font_info: dict[str, Any], page_height: float) -> bool:
        near_bottom = bbox.y0 < page_height * 0.18
        small_font = (bbox.height * 0.75) < font_info["body_font_size"] * 0.85
        return near_bottom and small_font

    def _is_header_footer(self, bbox: BoundingBox, page_height: float) -> bool:
        top_edge = bbox.y1 > page_height * 0.92
        bottom_edge = bbox.y0 < page_height * 0.08
        return top_edge or bottom_edge

    def _is_caption(self, text: str) -> bool:
        lower = text.lower().strip()
        return lower.startswith(("figure", "fig.", "table", "tab.", "exhibit", "chart"))

    def _is_quote(self, text: str) -> bool:
        stripped = text.strip()
        return stripped.startswith(('"', "'", "\u201c", "\u2018")) and len(stripped) > 20

    def _is_separator(self, text: str) -> bool:
        stripped = text.strip()
        if len(stripped) < 40:
            return False
        unique = set(stripped)
        allowed = {"-", "_", "*", "=", "~", ".", " "}
        return unique.issubset(allowed) or len(unique) <= 3

    def merge_consecutive_paragraphs(
        self,
        elements: list[DocumentElement],
    ) -> list[DocumentElement]:
        """Merge consecutive PARAGRAPH elements that belong to the same text block."""
        if not elements:
            return elements

        merged = []
        current = None

        for elem in elements:
            if elem.type == ElementType.PARAGRAPH:
                if current is None:
                    current = elem
                else:
                    current = DocumentElement(
                        type=ElementType.PARAGRAPH,
                        text=current.text + " " + elem.text,
                        bbox=BoundingBox(
                            page=current.bbox.page,
                            x0=min(current.bbox.x0, elem.bbox.x0),
                            y0=min(current.bbox.y0, elem.bbox.y0),
                            x1=max(current.bbox.x1, elem.bbox.x1),
                            y1=max(current.bbox.y1, elem.bbox.y1),
                        ),
                        metadata=current.metadata,
                    )
            else:
                if current is not None:
                    merged.append(current)
                    current = None
                merged.append(elem)

        if current is not None:
            merged.append(current)

        return merged
