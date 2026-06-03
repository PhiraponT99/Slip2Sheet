from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from watch import find_incoming_images, move_file


class WatchTest(unittest.TestCase):
    def test_find_incoming_images_filters_and_sorts_supported_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "b.png").write_text("", encoding="utf-8")
            (folder / "a.JPG").write_text("", encoding="utf-8")
            (folder / "c.txt").write_text("", encoding="utf-8")

            images = find_incoming_images(folder)

            self.assertEqual([path.name for path in images], ["a.JPG", "b.png"])

    def test_move_file_uses_unique_destination_when_name_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incoming = root / "incoming"
            processed = root / "processed"
            incoming.mkdir()
            processed.mkdir()
            source = incoming / "slip.jpg"
            source.write_text("new", encoding="utf-8")
            (processed / "slip.jpg").write_text("old", encoding="utf-8")

            destination = move_file(source, processed)

            self.assertEqual(destination.name, "slip-1.jpg")
            self.assertFalse(source.exists())
            self.assertEqual(destination.read_text(encoding="utf-8"), "new")


if __name__ == "__main__":
    unittest.main()
