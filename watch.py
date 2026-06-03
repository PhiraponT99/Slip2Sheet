from __future__ import annotations

import shutil
import time
from pathlib import Path

from expense_tracker.ocr import OcrError, run_ocr
from expense_tracker.parser import extract_transaction
from expense_tracker.sheets import SheetsError, append_transaction_to_sheet
from expense_tracker.summary import update_summary_sheet


INCOMING_DIR = Path("incoming")
PROCESSED_DIR = Path("processed")
PROCESSED_DUPLICATE_DIR = PROCESSED_DIR / "duplicate"
FAILED_DIR = Path("failed")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
POLL_SECONDS = 2


def main() -> int:
    ensure_watch_folders()
    processed_filenames: set[str] = set()

    log_info("Watching incoming/")
    while True:
        for image_path in find_incoming_images(INCOMING_DIR):
            if image_path.name in processed_filenames:
                continue

            processed_filenames.add(image_path.name)
            process_image(image_path)

        time.sleep(POLL_SECONDS)


def ensure_watch_folders() -> None:
    for folder in (INCOMING_DIR, PROCESSED_DIR, PROCESSED_DUPLICATE_DIR, FAILED_DIR):
        folder.mkdir(exist_ok=True)


def find_incoming_images(folder: Path) -> list[Path]:
    if not folder.exists():
        return []

    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def process_image(image_path: Path) -> None:
    log_info(f"Processing {image_path.name}")

    try:
        raw_text = run_ocr(image_path)
        transaction = extract_transaction(raw_text)
        saved_result = append_transaction_to_sheet(transaction, image_path)

        if saved_result["duplicate"]:
            log_warn(f"Duplicate transaction detected: {image_path.name}")
            log_info("Skipped save")
            move_file(image_path, PROCESSED_DUPLICATE_DIR)
            log_info("Moved to processed/")
            return

        log_info(f"Saved to sheet tab {saved_result['sheet_tab']}")

        update_summary_sheet()
        log_info("Summary updated")

        move_file(image_path, PROCESSED_DIR)
        log_info("Moved to processed/")
    except (OcrError, SheetsError, OSError, KeyError) as exc:
        log_error(f"Failed to process {image_path.name}: {exc}")
        try:
            move_file(image_path, FAILED_DIR)
        except OSError as move_exc:
            log_error(f"Failed to move {image_path.name} to failed/: {move_exc}")


def move_file(source: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(exist_ok=True)
    destination = unique_destination(destination_dir / source.name)
    shutil.move(str(source), str(destination))
    return destination


def unique_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    for index in range(1, 1000):
        candidate = destination.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate

    raise OSError(f"Could not create unique destination for {destination.name}")


def log_info(message: str) -> None:
    print(f"[INFO] {message}", flush=True)


def log_warn(message: str) -> None:
    print(f"[WARN] {message}", flush=True)


def log_error(message: str) -> None:
    print(f"[ERROR] {message}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
