from __future__ import annotations

import json
from typing import Any

from .models import DocumentElement, ElementType, TableData


class MarkdownExporter:
    """Converts structured document elements into clean Markdown."""

    def __init__(self, include_bbox_comment: bool = True):
        self.include_bbox_comment = include_bbox_comment

    def export(
        self,
        elements: list[DocumentElement],
        tables: list[TableData] | None = None,
    ) -> str:
        """Convert elements and tables to a single Markdown string."""
        lines: list[str] = []
        tables = tables or []

        table_texts: dict[int, str] = {}
        for t in tables:
            md = self._table_to_md(t)
            if t.bbox and md:
                table_texts[t.bbox.page] = md

        for elem in elements:
            md = self._element_to_md(elem)

            # Inject table below or near its page
            if elem.bbox.page in table_texts and elem.type == ElementType.PARAGRAPH:
                lines.append(md)
                lines.append("")
                lines.append(table_texts.pop(elem.bbox.page))
                continue

            if md.strip():
                lines.append(md)
                lines.append("")

        # Add remaining tables at end
        for page, md in sorted(table_texts.items()):
            lines.append(f"<!-- Table from page {page + 1} -->")
            lines.append(md)
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _element_to_md(self, elem: DocumentElement) -> str:
        text = elem.text.strip()
        bbox_comment = self._bbox_comment(elem.bbox) if self.include_bbox_comment else ""

        formatters = {
            ElementType.HEADING: lambda: f"{bbox_comment}\n## {text}",
            ElementType.PARAGRAPH: lambda: f"{bbox_comment}\n{text}",
            ElementType.LIST_ITEM: lambda: f"{bbox_comment}\n- {text}",
            ElementType.CODE_BLOCK: lambda: f"{bbox_comment}\n```\n{text}\n```",
            ElementType.QUOTE: lambda: f"{bbox_comment}\n> {text}",
            ElementType.CAPTION: lambda: f"{bbox_comment}\n*{text}*",
            ElementType.HEADER: lambda: f"{bbox_comment}\n*{text}*",
            ElementType.FOOTER: lambda: f"{bbox_comment}\n*{text}*",
            ElementType.FOOTNOTE: lambda: f"{bbox_comment}\n[^{text}]",
            ElementType.SEPARATOR: lambda: f"{bbox_comment}\n---",
            ElementType.IMAGE: lambda: "",
            ElementType.TABLE: lambda: f"{bbox_comment}\n{text}",
        }

        formatter = formatters.get(elem.type)
        if formatter:
            return formatter()

        return text

    @staticmethod
    def _bbox_comment(bbox: Any) -> str:
        return f"<!-- page={bbox.page} x0={bbox.x0:.1f} y0={bbox.y0:.1f} x1={bbox.x1:.1f} y1={bbox.y1:.1f} -->"

    @staticmethod
    def _table_to_md(table: TableData) -> str:
        if not table.rows:
            return ""

        all_rows = table.rows
        headers = table.column_headers
        if headers and headers != all_rows[0]:
            all_rows = [headers] + all_rows

        max_cols = max(len(row) for row in all_rows) if all_rows else 0
        if max_cols == 0:
            return ""

        padded = [row + [""] * (max_cols - len(row)) for row in all_rows]

        lines = ["| " + " | ".join(padded[0]) + " |"]
        lines.append("| " + " | ".join(["---"] * max_cols) + " |")
        for row in padded[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)


class JSONExporter:
    """Serializes the full extraction result to JSON with bbox for every element."""

    def export(
        self,
        elements: list[DocumentElement],
        tables: list[TableData] | None = None,
        file_path: str = "",
        page_count: int = 0,
    ) -> dict[str, Any]:
        """Build a JSON-serializable dict with all extraction data."""
        tables = tables or []

        return {
            "file_path": file_path,
            "page_count": page_count,
            "elements": [e.to_dict() for e in elements],
            "tables": [t.to_dict() for t in tables],
        }

    def dumps(
        self,
        elements: list[DocumentElement],
        tables: list[TableData] | None = None,
        file_path: str = "",
        page_count: int = 0,
        indent: int = 2,
    ) -> str:
        """Export to JSON string."""
        data = self.export(elements, tables, file_path, page_count)
        return json.dumps(data, indent=indent, ensure_ascii=False)
