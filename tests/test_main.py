import json
import io
import inspect
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import brotli

sys.path.insert(0, str(Path(__file__).parents[1]))
import main
import processor


class DownloaderTests(unittest.TestCase):
    def test_process_line_comes_from_portable_processor_module(self):
        self.assertEqual(main.process_line.__module__, "processor")
        public_functions = [
            name
            for name, value in vars(processor).items()
            if inspect.isfunction(value)
            and value.__module__ == processor.__name__
            and not name.startswith("_")
        ]
        self.assertEqual(public_functions, ["process_line"])

    def test_extracts_nested_s3_link(self):
        wrapped = "http://internal/decom?s3link=https%3A%2F%2Fbucket%2Ffile.json.br"
        self.assertEqual(
            processor._extract_s3_link(wrapped),
            "https://bucket/file.json.br",
        )

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

        with tempfile.TemporaryDirectory() as directory, patch.object(
            processor, "_fetch_bytes", return_value=compressed
        ) as fetch:
            raw_path = Path(directory) / "raw.json"
            result = processor.process_line(wrapped, raw_path)
            saved_raw = json.loads(raw_path.read_text())

        self.assertEqual(result["word_count"], 314)
        self.assertEqual(result["title"], "Example Site")
        self.assertEqual(result["page_text_snippet"], [paragraph])
        self.assertNotIn("url_raw_body", result)
        self.assertNotIn("input_url", result)
        self.assertNotIn("img_tag_count", result)
        self.assertEqual(saved_raw, artifact)
        fetch.assert_called_once_with("https://bucket/file.json.br")

    def test_process_line_rejects_non_object_json(self):
        compressed = brotli.compress(b"[]")

        with patch.object(processor, "_fetch_bytes", return_value=compressed):
            with self.assertRaisesRegex(ValueError, "JSON artifact is not an object"):
                processor.process_line("https://bucket/file.json.br")

    def test_saves_processed_json_and_skips_existing_file(self):
        result = {
            "headers": [],
            "image_alt_tags": [],
            "page_text_snippet": [],
        }

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "output"
            raw_dir = Path(directory) / "json"
            row = {"hashval": "abc", "s3status": "https://bucket/abc.json.br"}
            def process_line(s3link, raw_path):
                main.save_result({"raw": True}, raw_path)
                return result

            with patch.object(main, "process_line", side_effect=process_line) as process:
                self.assertEqual(
                    main.download_one(row, output_dir, raw_dir)[0],
                    "downloaded",
                )
                self.assertEqual(
                    main.download_one(row, output_dir, raw_dir)[0],
                    "skipped",
                )

            self.assertEqual(json.loads((output_dir / "abc.json").read_text()), result)
            self.assertEqual(json.loads((raw_dir / "abc.json").read_text()), {"raw": True})
            process.assert_called_once_with(row["s3status"], raw_dir / "abc.json")

    def test_reprocesses_existing_output_with_old_heading_schema(self):
        result = {
            "headers": ["Current Heading"],
            "image_alt_tags": [],
        }

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "output"
            raw_dir = Path(directory) / "json"
            main.save_result(
                {
                    "headers": ["Old Heading"],
                    "input_url": "https://example.com/",
                    "img_tag_count": 2,
                },
                output_dir / "abc.json",
            )
            main.save_result({"raw": True}, raw_dir / "abc.json")
            row = {"hashval": "abc", "s3status": "https://bucket/abc.json.br"}

            with patch.object(main, "process_line", return_value=result) as process:
                status, _ = main.download_one(row, output_dir, raw_dir)

            self.assertEqual(status, "downloaded")
            self.assertEqual(
                json.loads((output_dir / "abc.json").read_text()),
                result,
            )
            process.assert_called_once_with(row["s3status"], raw_dir / "abc.json")

    def test_failed_row_does_not_stop_later_rows(self):
        rows = [
            {"hashval": "bad", "s3status": ""},
            {"hashval": "good", "s3status": "https://bucket/good.json.br"},
        ]

        with tempfile.TemporaryDirectory() as directory:
            with redirect_stderr(io.StringIO()), patch.object(
                main, "process_line", return_value={"ok": True}
            ):
                counts = main.process_rows(
                    rows,
                    Path(directory) / "output",
                    workers=1,
                    raw_dir=Path(directory) / "json",
                )

            self.assertEqual(counts, {"downloaded": 1, "skipped": 0, "failed": 1})
            self.assertTrue((Path(directory) / "output" / "good.json").exists())


if __name__ == "__main__":
    unittest.main()
