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

    def test_process_line_downloads_and_returns_filtered_json(self):
        paragraph = " ".join(f"word{number}" for number in range(41))
        artifact = {
            "input_url": "https://example.com/",
            "wc": 314,
            "anchor_tag_count": 55,
            "anchor_tagst": ["https://example.com/about/"],
            "img_tag_count": 23,
            "url_raw_body": f"<title>Example, Site!</title><p>{paragraph}</p>",
        }
        compressed = brotli.compress(json.dumps(artifact).encode())
        wrapped = "http://internal/decom?s3link=https%3A%2F%2Fbucket%2Ffile.json.br"

        with patch.object(main, "fetch_bytes", return_value=compressed) as fetch:
            result = main.process_line(wrapped)

        self.assertEqual(result["input_url"], "https://example.com/")
        self.assertEqual(result["word_count"], 314)
        self.assertEqual(result["title"], "Example Site")
        self.assertEqual(result["page_text_snippet"], [paragraph])
        self.assertNotIn("url_raw_body", result)
        fetch.assert_called_once_with("https://bucket/file.json.br")

    def test_process_line_rejects_non_object_json(self):
        compressed = brotli.compress(b"[]")

        with patch.object(main, "fetch_bytes", return_value=compressed):
            with self.assertRaisesRegex(ValueError, "JSON artifact is not an object"):
                main.process_line("https://bucket/file.json.br")

    def test_saves_processed_json_and_skips_existing_file(self):
        result = {"input_url": "https://example.com/", "page_text_snippet": []}

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            row = {"hashval": "abc", "s3status": "https://bucket/abc.json.br"}
            with patch.object(main, "process_line", return_value=result) as process:
                self.assertEqual(main.download_one(row, output_dir)[0], "downloaded")
                self.assertEqual(main.download_one(row, output_dir)[0], "skipped")

            self.assertEqual(json.loads((output_dir / "abc.json").read_text()), result)
            process.assert_called_once_with(row["s3status"])

    def test_failed_row_does_not_stop_later_rows(self):
        rows = [
            {"hashval": "bad", "s3status": ""},
            {"hashval": "good", "s3status": "https://bucket/good.json.br"},
        ]

        with tempfile.TemporaryDirectory() as directory:
            with redirect_stderr(io.StringIO()), patch.object(
                main, "process_line", return_value={"ok": True}
            ):
                counts = main.process_rows(rows, Path(directory), workers=1)

            self.assertEqual(counts, {"downloaded": 1, "skipped": 0, "failed": 1})
            self.assertTrue((Path(directory) / "good.json").exists())


if __name__ == "__main__":
    unittest.main()
