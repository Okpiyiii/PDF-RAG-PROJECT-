from __future__ import annotations

import threading
from typing import Any

import pdfplumber

from .models import BoundingBox, TableData


class TableExtractor:
    """Extracts tables from PDF pages using pdfplumber.

    Handles bordered tables (via explicit line detection) and borderless tables
    (via text-alignment heuristics). Returns structured TableData with cell contents
    and bounding box coordinates.
    """

    def __init__(
        self,
        snap_tolerance: float = 3.0,
        join_tolerance: float = 3.0,
        edge_min_length: float = 8.0,
        text_tolerance: float = 4.0,
        text_x_tolerance: float = 4.0,
        text_y_tolerance: float = 4.0,
    ):
        self.snap_tolerance = snap_tolerance
        self.join_tolerance = join_tolerance
        self.edge_min_length = edge_min_length
        self.text_tolerance = text_tolerance
        self.text_x_tolerance = text_x_tolerance
        self.text_y_tolerance = text_y_tolerance

    def extract_tables(self, file_path: str) -> list[TableData]:
        """Extract all tables from a PDF file."""
        all_tables: list[TableData] = []

        with pdfplumber.open(file_path) as pdf:
            for page_number, page in enumerate(pdf.pages):
                page_tables = self._extract_from_page(page, page_number)
                all_tables.extend(page_tables)

        return all_tables

    def extract_tables_from_page(
        self, file_path: str, page_number: int,
    ) -> list[TableData]:
        """Extract tables from a single page without opening the whole file repeatedly.
        Use extract_tables_from_pages() for batch extraction."""
        with pdfplumber.open(file_path) as pdf:
            if page_number >= len(pdf.pages):
                return []
            return self._extract_from_page(pdf.pages[page_number], page_number)

    def extract_tables_from_pages(
        self, file_path: str, page_numbers: list[int],
    ) -> list[TableData]:
        """Extract tables from specific pages in a single file open."""
        result: list[TableData] = []
        with pdfplumber.open(file_path) as pdf:
            for pn in page_numbers:
                if pn < len(pdf.pages):
                    result.extend(self._extract_from_page(pdf.pages[pn], pn))
        return result

    def _extract_from_page(
        self,
        page: pdfplumber.page.Page,
        page_number: int,
    ) -> list[TableData]:
        tables: list[TableData] = []

        # Strategy 1: Bordered tables via line detection
        bordered = page.find_tables({
            "snap_tolerance": self.snap_tolerance,
            "join_tolerance": self.join_tolerance,
            "edge_min_length": self.edge_min_length,
            "text_tolerance": self.text_tolerance,
            "text_x_tolerance": self.text_x_tolerance,
            "text_y_tolerance": self.text_y_tolerance,
        })

        if bordered:
            for btable in bordered:
                rows = self._normalize_rows(btable.extract())
                if rows:
                    bbox = BoundingBox(
                        page=page_number,
                        x0=btable.bbox[0],
                        y0=btable.bbox[1],
                        x1=btable.bbox[2],
                        y1=btable.bbox[3],
                    )
                    headers = self._extract_headers(rows)
                    tables.append(TableData(
                        rows=rows,
                        bbox=bbox,
                        column_headers=headers,
                    ))
        else:
            # Strategy 2: Borderless tables — text alignment heuristic
            borderless = page.extract_tables({
                "snap_tolerance": self.snap_tolerance,
                "join_tolerance": self.join_tolerance,
            })
            if borderless:
                for btable in borderless:
                    rows = self._normalize_rows(btable)
                    if rows:
                        page_bbox = page.bbox
                        bbox = BoundingBox(
                            page=page_number,
                            x0=page_bbox[0],
                            y0=page_bbox[1],
                            x1=page_bbox[2],
                            y1=page_bbox[3],
                        )
                        headers = self._extract_headers(rows)
                        tables.append(TableData(
                            rows=rows,
                            bbox=bbox,
                            column_headers=headers,
                        ))
                        break  # one borderless table per page

        return tables

    @staticmethod
    def _normalize_rows(rows: list[list[str | None]]) -> list[list[str]]:
        """Clean None values and strip whitespace."""
        return [
            [(cell or "").strip() for cell in row]
            for row in rows
            if any((cell or "").strip() for cell in row)
        ]

    @staticmethod
    def _extract_headers(rows: list[list[str]]) -> list[str]:
        """Heuristic: first row is usually the header."""
        if rows:
            return rows[0]
        return []

    def to_markdown(self, table: TableData) -> str:
        """Convert a TableData to a Markdown table string."""
        if not table.rows:
            return ""

        all_rows = table.rows
        if table.column_headers and table.column_headers != all_rows[0]:
            all_rows = [table.column_headers] + all_rows

        max_cols = max(len(row) for row in all_rows) if all_rows else 0
        if max_cols == 0:
            return ""

        # Pad rows to same width
        padded = [row + [""] * (max_cols - len(row)) for row in all_rows]

        header = padded[0]
        lines = []

        # Header row
        lines.append("| " + " | ".join(header) + " |")

        # Separator
        lines.append("| " + " | ".join(["---"] * max_cols) + " |")

        # Data rows
        for row in padded[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)
