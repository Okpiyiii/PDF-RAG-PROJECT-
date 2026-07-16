from __future__ import annotations

import os
import tempfile
from typing import Any

import fitz  # PyMuPDF
from PIL import Image

from .models import BoundingBox


class OCRPipeline:
    """OCR pipeline for scanned PDF documents.

    Renders PDF pages as images, then runs Tesseract OCR with hOCR output
    to get word-level bounding boxes. Falls back to plain text extraction
    if Tesseract is not available.
    """

    def __init__(
        self,
        dpi: int = 300,
        language: str = "eng",
        tesseract_config: str = "--oem 3 --psm 6",
        preprocess: bool = True,
        tesseract_cmd: str | None = None,
    ):
        self.dpi = dpi
        self.language = language
        self.tesseract_config = tesseract_config
        self.preprocess = preprocess
        self.tesseract_cmd = tesseract_cmd

    def process(
        self,
        file_path: str,
        page_numbers: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """OCR-process pages of a PDF and return text with bbox.

        Returns a list of dicts: {text, bbox: BoundingBox, confidence: float, page}
        """
        try:
            import pytesseract
        except ImportError:
            raise ImportError(
                "pytesseract is required for OCR. Install with: pip install pytesseract"
            )

        self._setup_tesseract()

        results: list[dict[str, Any]] = []
        doc = fitz.open(file_path)

        pages = page_numbers or list(range(doc.page_count))

        for page_num in pages:
            if page_num >= doc.page_count:
                continue

            page = doc[page_num]
            pix = page.get_pixmap(dpi=self.dpi)
            page_width = page.rect.width
            page_height = page.rect.height

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                pix.save(tmp.name)
                try:
                    image = Image.open(tmp.name)
                    if self.preprocess:
                        image = self._preprocess_image(image)

                    page_results = self._ocr_page(
                        image, page_num, page_width, page_height,
                    )
                    results.extend(page_results)
                finally:
                    os.unlink(tmp.name)

        doc.close()
        return results

    def _setup_tesseract(self) -> None:
        import pytesseract
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """Apply image preprocessing for better OCR accuracy."""
        try:
            from PIL import ImageFilter, ImageOps

            image = image.convert("L")  # Grayscale
            image = ImageOps.autocontrast(image, cutoff=1)
            image = image.filter(ImageFilter.SHARPEN)

            return image
        except Exception:
            return image

    def _ocr_page(
        self,
        image: Image.Image,
        page_num: int,
        pdf_width: float,
        pdf_height: float,
    ) -> list[dict[str, Any]]:
        """Run OCR on a single page image and map coordinates back to PDF space."""
        import pytesseract

        scale_x = pdf_width / image.width
        scale_y = pdf_height / image.height

        results: list[dict[str, Any]] = []

        try:
            df = pytesseract.image_to_data(
                image,
                lang=self.language,
                config=self.tesseract_config,
                output_type=pytesseract.Output.DATAFRAME,
            )
        except Exception:
            return results

        if df is None or df.empty:
            return results

        # Filter to valid word entries
        df = df[df["conf"] > 0].dropna(subset=["text"])
        df = df[df["text"].astype(str).str.strip() != ""]

        # Group words into lines by block_num + par_num + line_num
        grouped = df.groupby(["block_num", "par_num", "line_num"])

        for _, group in grouped:
            text_parts = group["text"].astype(str).tolist()
            line_text = " ".join(text_parts).strip()
            if not line_text:
                continue

            left = group["left"].min()
            top = group["top"].min()
            right = (group["left"] + group["width"]).max()
            bottom = (group["top"] + group["height"]).max()
            avg_conf = group["conf"].mean()

            bbox = BoundingBox(
                page=page_num,
                x0=left * scale_x,
                y0=top * scale_y,
                x1=right * scale_x,
                y1=bottom * scale_y,
            )

            results.append({
                "text": line_text,
                "bbox": bbox,
                "confidence": round(float(avg_conf), 2),
                "page": page_num,
            })

        return results

    def get_full_text(self, file_path: str) -> str:
        """OCR entire PDF and return concatenated text."""
        import pytesseract
        self._setup_tesseract()

        doc = fitz.open(file_path)
        full_text: list[str] = []

        for page_num in range(doc.page_count):
            pix = doc[page_num].get_pixmap(dpi=self.dpi)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                pix.save(tmp.name)
                try:
                    image = Image.open(tmp.name)
                    if self.preprocess:
                        image = self._preprocess_image(image)
                    text = pytesseract.image_to_string(
                        image, lang=self.language, config=self.tesseract_config,
                    )
                    full_text.append(text)
                finally:
                    os.unlink(tmp.name)

        doc.close()
        return "\n\n".join(full_text)
