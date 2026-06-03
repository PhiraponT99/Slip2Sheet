from __future__ import annotations

from pathlib import Path

TESSERACT_CMD = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


class OcrError(RuntimeError):
    """Raised when OCR cannot be completed."""


def run_ocr(image_path: Path) -> str:
    try:
        from PIL import Image, ImageOps
        import pytesseract
    except ImportError as exc:
        raise OcrError(
            "Python OCR dependencies are missing. Run: pip install -r requirements.txt"
        ) from exc

    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_CMD)
    if not TESSERACT_CMD.exists():
        raise OcrError(f"Tesseract executable not found: {TESSERACT_CMD}")

    try:
        with Image.open(image_path) as image:
            prepared = _prepare_image(image, ImageOps)
            text = pytesseract.image_to_string(prepared, lang="tha+eng")
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrError("Tesseract is not installed or is not on PATH.") from exc
    except pytesseract.TesseractError as exc:
        raise OcrError(str(exc)) from exc
    except OSError as exc:
        raise OcrError(f"Could not open image: {exc}") from exc

    return text.strip()


def _prepare_image(image, image_ops):
    grayscale = image_ops.grayscale(image)
    return image_ops.autocontrast(grayscale)
