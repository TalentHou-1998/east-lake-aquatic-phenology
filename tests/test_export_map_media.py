import tempfile
import unittest
from pathlib import Path

from src.export_map_site import media_sources


class MediaSourcesTest(unittest.TestCase):
    def test_file_path_does_not_collect_sibling_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "post-a.jpg"
            other = root / "post-b.jpg"
            first.touch()
            other.touch()
            self.assertEqual(media_sources(root, {"media_paths": "", "media_local_path": first.name}), [first])

    def test_directory_path_collects_supported_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "post-a"
            folder.mkdir()
            image = folder / "01.jpg"
            image.touch()
            (folder / "note.txt").touch()
            self.assertEqual(media_sources(root, {"media_paths": "", "media_local_path": folder.name}), [image])


if __name__ == "__main__":
    unittest.main()
