import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import filter_json


class FilterJsonTests(unittest.TestCase):
    def test_visible_text_cleanup_keeps_readable_stopwords(self):
        text = "The café ☰ is open!!!\nVisit... a trusted site 🙂"

        result = filter_json.process_visible_text(text)

        self.assertEqual(result, "The café is open! Visit. a trusted site")

    def test_long_visible_text_keeps_representative_chunks_under_900_words(self):
        chunks = [
            " ".join([f"chunk{number}"] + [f"word{number}"] * 98)
            for number in range(41)
        ]
        chunks[27] = " ".join(["captcha"] + ["failure"] * 98)

        result = filter_json.process_visible_text(" ".join(chunks))

        self.assertLessEqual(len(result.split()), 900)
        self.assertIn("chunk0", result)
        self.assertIn("chunk1", result)
        self.assertIn("captcha", result)
        self.assertIn("chunk40", result)

    def test_filters_fields_paths_and_preserves_short_text_content(self):
        text = "This full text must remain unchanged. " * 100
        artifact = {
            "status_code": 200,
            "error-comment": "OK",
            "is_go_daddy": False,
            "wc": 500,
            "anchor_tag_count": 20,
            "anchor_tagst": [
                "https://example.com/",
                "https://example.com/live",
                "https://example.com/news",
                "https://example.com/weather/",
                "https://example.com/good-day-atlanta",
                "https://example.com/sports",
                "https://example.com/contest",
                "https://example.com/live",
            ],
            "img_tag_count": 7,
            "lang_detected": "en",
            "url_visible_text": text,
            "final_result": "WORKING_OLD",
            "url_raw_body": "<html>large</html>",
        }

        result = filter_json.filter_artifact(artifact)

        self.assertEqual(
            result,
            {
                "status_code": 200,
                "error-comment": "OK",
                "is_go_daddy": False,
                "wc": 500,
                "anchor_tag_count": 20,
                "anchor_tagst": ["live", "news", "weather", "sports", "contest"],
                "img_tag_count": 7,
                "lang_detected": "en",
                "url_visible_text": text.strip(),
            },
        )

    def test_directory_continues_after_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "json"
            output_dir = root / "output"
            input_dir.mkdir()
            (input_dir / "bad.json").write_text("not json")
            (input_dir / "good.json").write_text(
                json.dumps({"url_visible_text": "complete text"})
            )

            with redirect_stderr(io.StringIO()):
                counts = filter_json.filter_directory(input_dir, output_dir)

            self.assertEqual(counts, {"written": 1, "failed": 1})
            self.assertEqual(
                json.loads((output_dir / "good.json").read_text())["url_visible_text"],
                "complete text",
            )


if __name__ == "__main__":
    unittest.main()
