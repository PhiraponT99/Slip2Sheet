from __future__ import annotations

import json
import os
import platform
import shutil
from datetime import datetime
from pathlib import Path

WINDOWS_TESSERACT_CMD = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
LINUX_TESSERACT_CMD = Path("/usr/bin/tesseract")
DEFAULT_TESSERACT_CONFIG = "--oem 3 --psm 6"
DEFAULT_OCR_ENGINE = "tesseract"
DEFAULT_OCR_DEBUG_DIR = Path("debug") / "ocr"


class OcrError(RuntimeError):
    """Raised when OCR cannot be completed."""


def run_ocr(image_path: Path) -> str:
    engine = get_ocr_engine()
    if engine == "easyocr":
        return run_easyocr(image_path)
    if engine != DEFAULT_OCR_ENGINE:
        raise OcrError(f"Unsupported OCR_ENGINE: {engine}")
    return run_tesseract_ocr(image_path)


def run_tesseract_ocr(image_path: Path) -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise OcrError(
            "Python OCR dependencies are missing. Run: pip install -r requirements.txt"
        ) from exc

    prepared = preprocess_image(image_path)
    _save_debug_image(image_path, prepared)

    tesseract_cmd = resolve_tesseract_cmd()
    tesseract_exists = tesseract_command_exists(tesseract_cmd)
    print("[INFO] Tesseract command selected:", tesseract_cmd)
    print("[INFO] Tesseract executable exists:", tesseract_exists)
    pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd)
    if not tesseract_exists:
        raise OcrError(f"Tesseract executable not found: {tesseract_cmd}")

    try:
        text = pytesseract.image_to_string(
            prepared,
            lang="tha+eng",
            config=DEFAULT_TESSERACT_CONFIG,
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrError("Tesseract is not installed or is not on PATH.") from exc
    except pytesseract.TesseractError as exc:
        raise OcrError(str(exc)) from exc

    text = text.strip()
    _save_debug_ocr_text(image_path, text)
    _save_debug_parser_candidates(image_path, text)
    return text


def run_easyocr(image_path: Path) -> str:
    try:
        import easyocr
    except ImportError as exc:
        raise OcrError(
            "EasyOCR is not installed. Install it only if OCR_ENGINE=easyocr is required."
        ) from exc

    reader = easyocr.Reader(["th", "en"], gpu=False)
    results = reader.readtext(str(image_path), detail=0, paragraph=True)
    text = "\n".join(str(result).strip() for result in results if str(result).strip())
    _save_debug_ocr_text(image_path, text)
    _save_debug_parser_candidates(image_path, text)
    return text.strip()


def preprocess_image(image_path: Path):
    try:
        import cv2
    except ImportError as exc:
        raise OcrError(
            "OpenCV OCR preprocessing dependency is missing. Run: pip install -r requirements.txt"
        ) from exc

    image = cv2.imread(str(image_path))
    if image is None:
        raise OcrError(f"Could not open image: {image_path}")

    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(
        grayscale,
        None,
        fx=2,
        fy=2,
        interpolation=cv2.INTER_CUBIC,
    )
    contrasted = cv2.convertScaleAbs(resized, alpha=1.35, beta=0)
    denoised = cv2.medianBlur(contrasted, 3)
    return cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        11,
    )


def resolve_tesseract_cmd(
    env: dict[str, str] | None = None,
    platform_name: str | None = None,
    which=shutil.which,
    windows_path: Path = WINDOWS_TESSERACT_CMD,
) -> Path:
    env = env if env is not None else os.environ
    env_cmd = env.get("TESSERACT_CMD")
    if env_cmd:
        return Path(env_cmd)

    platform_name = platform_name or platform.system()
    if platform_name == "Windows" and windows_path.exists():
        return windows_path

    path_cmd = which("tesseract")
    if path_cmd:
        return Path(path_cmd)

    if platform_name == "Windows":
        return windows_path
    return LINUX_TESSERACT_CMD


def tesseract_command_exists(tesseract_cmd: Path) -> bool:
    return tesseract_cmd.exists() or shutil.which(str(tesseract_cmd)) is not None


def get_ocr_engine(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else os.environ
    return env.get("OCR_ENGINE", DEFAULT_OCR_ENGINE).strip().lower()


def debug_ocr_enabled(env: dict[str, str] | None = None) -> bool:
    env = env if env is not None else os.environ
    return env.get("DEBUG_OCR", "").strip().lower() in {"1", "true", "yes", "on"}


def ocr_debug_dir(env: dict[str, str] | None = None) -> Path:
    env = env if env is not None else os.environ
    return Path(env.get("OCR_DEBUG_DIR", str(DEFAULT_OCR_DEBUG_DIR)))


def _debug_base_path(image_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_stem = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in image_path.stem
    )
    return ocr_debug_dir() / f"{timestamp}-{safe_stem}"


def _save_debug_image(image_path: Path, processed_image) -> None:
    if not debug_ocr_enabled():
        return

    try:
        import cv2

        base_path = _debug_base_path(image_path)
        base_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(base_path.with_suffix(".processed.png")), processed_image)
    except Exception as exc:
        print("[WARN] OCR debug image save failed:", exc)


def _save_debug_ocr_text(image_path: Path, text: str) -> None:
    if not debug_ocr_enabled():
        return

    print("[DEBUG] OCR raw text:")
    print(text)
    try:
        base_path = _debug_base_path(image_path)
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.with_suffix(".ocr.txt").write_text(text, encoding="utf-8")
    except OSError as exc:
        print("[WARN] OCR debug text save failed:", exc)


def _save_debug_parser_candidates(image_path: Path, text: str) -> None:
    if not debug_ocr_enabled():
        return

    try:
        from expense_tracker.parser_diagnostics import analyze_parser_accuracy

        report = analyze_parser_accuracy(text)
        print("[DEBUG] Parser selected amount:", report.get("selected_amount"))
        print("[DEBUG] Parser selected score:", report.get("selected_score"))
        base_path = _debug_base_path(image_path)
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.with_suffix(".parser-candidates.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        print("[WARN] OCR debug parser candidate save failed:", exc)
