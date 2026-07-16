from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class ElementType(Enum):
    HEADING = auto()
    PARAGRAPH = auto()
    LIST_ITEM = auto()
    TABLE = auto()
    IMAGE = auto()
    CAPTION = auto()
    HEADER = auto()
    FOOTER = auto()
    FOOTNOTE = auto()
    CODE_BLOCK = auto()
    QUOTE = auto()
    SEPARATOR = auto()


class ReadingOrder(Enum):
    LTR_TOP_TO_BOTTOM = auto()
    TTB_RIGHT_TO_LEFT = auto()


@dataclass
class BoundingBox:
    """Bounding box in PDF coordinate space (origin at bottom-left unless page-normalized)."""
    page: int
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "x0": round(self.x0, 2),
            "y0": round(self.y0, 2),
            "x1": round(self.x1, 2),
            "y1": round(self.y1, 2),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BoundingBox":
        return cls(
            page=d["page"],
            x0=d["x0"],
            y0=d["y0"],
            x1=d["x1"],
            y1=d["y1"],
        )


@dataclass
class DocumentElement:
    """A single structural element extracted from the PDF."""
    type: ElementType
    text: str
    bbox: BoundingBox
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.name.lower(),
            "text": self.text,
            "bbox": self.bbox.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DocumentElement":
        return cls(
            type=ElementType[d["type"].upper()],
            text=d["text"],
            bbox=BoundingBox.from_dict(d["bbox"]),
            metadata=d.get("metadata", {}),
        )


@dataclass
class TableData:
    """Structured table representation with cells and row/column spans."""
    rows: list[list[str]]
    bbox: BoundingBox
    column_headers: list[str] = field(default_factory=list)
    row_headers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "bbox": self.bbox.to_dict(),
            "column_headers": self.column_headers,
            "row_headers": self.row_headers,
        }


@dataclass
class PageLayout:
    """Describes the layout of a single page."""
    page_number: int
    width: float
    height: float
    columns: list[BoundingBox] = field(default_factory=list)
    text_blocks: list[BoundingBox] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Complete extraction result for a PDF document."""
    file_path: str
    page_count: int
    elements: list[DocumentElement] = field(default_factory=list)
    tables: list[TableData] = field(default_factory=list)
    page_layouts: list[PageLayout] = field(default_factory=list)
    markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "page_count": self.page_count,
            "elements": [e.to_dict() for e in self.elements],
            "tables": [t.to_dict() for t in self.tables],
            "page_layouts": [
                {
                    "page_number": pl.page_number,
                    "width": pl.width,
                    "height": pl.height,
                    "columns": [c.to_dict() for c in pl.columns],
                    "text_blocks": [b.to_dict() for b in pl.text_blocks],
                }
                for pl in self.page_layouts
            ],
            "markdown": self.markdown,
        }

    def to_json(self, indent: int = 2) -> str:
        import json
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
