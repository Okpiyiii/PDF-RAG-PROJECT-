from __future__ import annotations

from typing import Any

from .models import BoundingBox, PageLayout


def default_y_tolerance(page_height: float) -> float:
    return max(4.0, page_height * 0.005)


class LayoutAnalyzer:
    """Detects page layout structure — columns, reading order, multi-column layout.

    Uses histogram-based column detection: projects text block bboxes onto the
    x-axis, identifies gaps, and partitions into columns. Then sorts blocks
    within each column top-to-bottom.
    """

    def __init__(
        self,
        column_gap_threshold_ratio: float = 0.03,
        y_tolerance_ratio: float = 0.005,
        min_column_width_ratio: float = 0.05,
    ):
        self.column_gap_threshold_ratio = column_gap_threshold_ratio
        self.y_tolerance_ratio = y_tolerance_ratio
        self.min_column_width_ratio = min_column_width_ratio

    def analyze_page(
        self,
        page_number: int,
        page_width: float,
        page_height: float,
        text_blocks: list[dict[str, Any]],
    ) -> PageLayout:
        """Analyze a single page and return its layout structure."""
        blocks_only = [b for b in text_blocks if b["block_type"] == 0]

        if not blocks_only:
            return PageLayout(
                page_number=page_number,
                width=page_width,
                height=page_height,
                columns=[],
                text_blocks=[],
            )

        columns = self._detect_columns(blocks_only, page_width)

        layout = PageLayout(page_number=page_number, width=page_width, height=page_height)
        for col in columns:
            layout.columns.append(col)
        layout.text_blocks = [b["bbox"] for b in blocks_only]

        return layout

    def _detect_columns(
        self,
        blocks: list[dict[str, Any]],
        page_width: float,
    ) -> list[BoundingBox]:
        """Use x-axis projection histograms to find column boundaries."""
        gap_threshold = page_width * self.column_gap_threshold_ratio
        min_col_width = page_width * self.min_column_width_ratio

        # Collect all x-intervals
        x_intervals = []
        for block in blocks:
            bbox = block["bbox"]
            x_intervals.append((bbox.x0, bbox.x1))

        if not x_intervals:
            return []

        # Sort by x0 and merge overlapping intervals
        x_intervals.sort(key=lambda iv: iv[0])
        merged = [list(x_intervals[0])]
        for iv in x_intervals[1:]:
            prev = merged[-1]
            if iv[0] <= prev[1] + gap_threshold:
                prev[1] = max(prev[1], iv[1])
            else:
                merged.append(list(iv))

        # Filter to valid columns (wider than min_col_width)
        page_number = blocks[0]["bbox"].page
        cmin = merged[0][0] if merged else 0.0

        columns = []
        for x0, x1 in merged:
            if (x1 - x0) >= min_col_width:
                columns.append(
                    BoundingBox(
                        page=page_number,
                        x0=x0,
                        y0=0.0,
                        x1=x1,
                        y1=0.0,
                    )
                )

        # Assign y0/y1 from the first/last block's y in each column area
        for col in columns:
            col_blocks = [b for b in blocks if self._overlaps_x(b["bbox"], col, gap_threshold)]
            if col_blocks:
                col_blocks.sort(key=lambda b: b["bbox"].y0)
                col.y0 = col_blocks[0]["bbox"].y0
                col.y1 = col_blocks[-1]["bbox"].y1 + col_blocks[-1]["bbox"].height

        return columns

    @staticmethod
    def _overlaps_x(bbox: BoundingBox, column: BoundingBox, tolerance: float) -> bool:
        return bbox.x1 > column.x0 - tolerance and bbox.x0 < column.x1 + tolerance

    def get_reading_order(
        self,
        blocks: list[dict[str, Any]],
        columns: list[BoundingBox],
        page_height: float,
    ) -> list[dict[str, Any]]:
        """Sort blocks into correct reading order: by column left-to-right,
        then within each column top-to-bottom."""
        if not columns:
            return sorted(blocks, key=lambda b: (b["bbox"].y0, b["bbox"].x0))

        y_tol = self.y_tolerance_ratio * page_height

        columns_sorted = sorted(columns, key=lambda c: c.x0)
        ordered_blocks: list[dict[str, Any]] = []

        for col in columns_sorted:
            col_blocks = [
                b for b in blocks
                if self._overlaps_x(b["bbox"], col, y_tol)
            ]
            col_blocks.sort(key=lambda b: (b["bbox"].y0, b["bbox"].x0))
            ordered_blocks.extend(col_blocks)

        return ordered_blocks
