from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from expense_tracker.ocr import (
    debug_ocr_enabled,
    get_ocr_engine,
    ocr_debug_dir,
    preprocess_image,
    resolve_tesseract_cmd,
    tesseract_command_exists,
)


class OcrConfigTests(unittest.TestCase):
    def test_env_tesseract_cmd_takes_priority(self) -> None:
        cmd = resolve_tesseract_cmd(
            env={"TESSERACT_CMD": "/custom/tesseract"},
            platform_name="Linux",
            which=lambda name: "/usr/bin/tesseract",
        )

        self.assertEqual(cmd, Path("/custom/tesseract"))

    def test_windows_default_is_used_when_available(self) -> None:
        cmd = resolve_tesseract_cmd(
            env={},
            platform_name="Windows",
            which=lambda name: None,
            windows_path=Path("."),
        )

        self.assertEqual(cmd, Path("."))

    def test_path_tesseract_is_used_when_available(self) -> None:
        cmd = resolve_tesseract_cmd(
            env={},
            platform_name="Linux",
            which=lambda name: "/usr/bin/tesseract",
        )

        self.assertEqual(cmd, Path("/usr/bin/tesseract"))

    def test_linux_falls_back_to_usr_bin_tesseract(self) -> None:
        cmd = resolve_tesseract_cmd(
            env={},
            platform_name="Linux",
            which=lambda name: None,
        )

        self.assertEqual(cmd, Path("/usr/bin/tesseract"))

    def test_command_exists_uses_path_lookup(self) -> None:
        with patch("expense_tracker.ocr.shutil.which", return_value="/usr/bin/tesseract"):
            self.assertTrue(tesseract_command_exists(Path("tesseract")))

    def test_ocr_engine_defaults_to_tesseract(self) -> None:
        self.assertEqual(get_ocr_engine({}), "tesseract")

    def test_ocr_engine_reads_environment_value(self) -> None:
        self.assertEqual(get_ocr_engine({"OCR_ENGINE": " easyocr "}), "easyocr")

    def test_debug_ocr_enabled_accepts_truthy_values(self) -> None:
        self.assertTrue(debug_ocr_enabled({"DEBUG_OCR": "true"}))
        self.assertTrue(debug_ocr_enabled({"DEBUG_OCR": "1"}))
        self.assertFalse(debug_ocr_enabled({"DEBUG_OCR": "false"}))

    def test_ocr_debug_dir_defaults_and_overrides(self) -> None:
        self.assertEqual(ocr_debug_dir({}), Path("debug") / "ocr")
        self.assertEqual(ocr_debug_dir({"OCR_DEBUG_DIR": "tmp/ocr"}), Path("tmp/ocr"))

    def test_preprocess_image_resizes_and_thresholds(self) -> None:
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV is not installed in this environment.")

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.png"
            image = np.full((10, 20, 3), 255, dtype=np.uint8)
            cv2.putText(
                image,
                "50",
                (1, 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.3,
                (0, 0, 0),
                1,
            )
            cv2.imwrite(str(image_path), image)

            processed = preprocess_image(image_path)

        self.assertEqual(processed.shape, (20, 40))
        self.assertTrue(set(np.unique(processed)).issubset({0, 255}))


if __name__ == "__main__":
    unittest.main()
