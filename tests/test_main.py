import json
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import brotli

sys.path.insert(0, str(Path(__file__).parents[1]))
import main


class DownloaderTests(unittest.TestCase):
    def test_extracts_nested_s3_link(self):
        wrapped = "http://internal/decom?s3link=https%3A%2F%2Fbucket%2Ffile.json.br"
        self.assertEqual(main.extract_s3_link(wrapped), "https://bucket/file.json.br")

    def test_downloads_valid_json_and_skips_existing_file(self):
        payload = {"url_visible_text": "hello"}
        compressed = brotli.compress(json.dumps(payload).encode())

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            row = {"hashval": "abc", "s3status": "https://bucket/abc.json.br"}
            with patch.object(main, "fetch_bytes", return_value=compressed) as fetch:
                self.assertEqual(main.download_one(row, output_dir)[0], "downloaded")
                self.assertEqual(main.download_one(row, output_dir)[0], "skipped")

            self.assertEqual(json.loads((output_dir / "abc.json").read_text()), payload)
            fetch.assert_called_once()

    def test_failed_row_does_not_stop_later_rows(self):
        compressed = brotli.compress(b'{"ok": true}')
        rows = [
            {"hashval": "bad", "s3status": ""},
            {"hashval": "good", "s3status": "https://bucket/good.json.br"},
        ]

        with tempfile.TemporaryDirectory() as directory:
            with redirect_stderr(io.StringIO()), patch.object(
                main, "fetch_bytes", return_value=compressed
            ):
                counts = main.process_rows(rows, Path(directory), workers=1)

            self.assertEqual(counts, {"downloaded": 1, "skipped": 0, "failed": 1})
            self.assertTrue((Path(directory) / "good.json").exists())


if __name__ == "__main__":
    unittest.main()
