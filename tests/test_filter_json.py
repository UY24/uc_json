import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import filter_json


class FilterJsonTests(unittest.TestCase):
    def test_anchor_paths_keep_full_path_and_remove_query(self):
        with patch("random.sample", side_effect=lambda values, count: values):
            result = filter_json.anchor_paths(
                [
                    "https://www.goodreads.com/",
                    "https://www.goodreads.com/blog/show/3146?"
                    "ref=literalsummer_eb"
                ]
            )

        self.assertEqual(result, ["/blog/show/3146"])

    def test_extracts_approved_schema_from_html(self):
        short = " ".join(f"short{i}" for i in range(10))
        closest = " ".join(f"context{i}," for i in range(41))
        long = " ".join(f"long{i}" for i in range(80))
        artifact = {
            "input_url": "https://example.com/about?a=1",
            "wc": 500,
            "anchor_tag_count": 20,
            "anchor_tagst": [
                "https://example.com/about-us/",
                "https://example.com/services/cloud.html",
                "https://example.com/news/latest-update",
                "https://example.com/contact/",
                "https://example.com/products/really-long-product-name/",
                "https://example.com/careers/jobs/",
            ],
            "img_tag_count": 7,
            "lang_detected": "en",
            "url_raw_body": f"""
                <html><head><title>Example, "Company"! | ☰</title></head><body>
                <header><p>{'footer ' * 40}</p><h1>Main, Heading!</h1></header>
                <h1>Second &amp; Heading</h1><h1>Second &amp; Heading</h1>
                <h1>Third. Heading</h1>
                <h1>Fourth Heading</h1>
                <h2>Our, Services!</h2><h2>About Us</h2><h2>News</h2>
                <h2>Contact</h2><h2>Careers</h2><h2>Sixth Heading</h2>
                <p>{short}</p><p>{closest}</p><p>{long}</p>
                </body></html>
            """,
        }

        with patch(
            "random.sample",
            side_effect=lambda values, count: values[-count:],
        ):
            result = filter_json.filter_artifact(artifact)

        self.assertEqual(
            set(result),
            {
                "input_url",
                "word_count",
                "anchor_tag_count",
                "anchor_tags_list",
                "img_tag_count",
                "title",
                "h1_tags",
                "h2_tags",
                "url_visible_text",
            },
        )
        self.assertEqual(result["input_url"], artifact["input_url"])
        self.assertEqual(result["word_count"], 500)
        self.assertEqual(result["title"], "Example Company")
        self.assertEqual(
            result["h1_tags"],
            ["Main Heading", "Second Heading", "Third Heading"],
        )
        self.assertEqual(
            result["h2_tags"],
            ["Our Services", "About Us", "News", "Contact", "Careers"],
        )
        self.assertEqual(result["url_visible_text"], closest.replace(",", ""))
        self.assertEqual(len(result["anchor_tags_list"]), 5)
        self.assertIn(
            "/products/really-long-product-name/",
            result["anchor_tags_list"],
        )

    def test_selects_closest_paragraph_leaf_div_or_leaf_span(self):
        paragraph = " ".join(f"paragraph{i}" for i in range(60))
        division = " ".join(f"division{i}" for i in range(44))
        span = " ".join(f"span{i}" for i in range(39))
        artifact = {
            "url_raw_body": (
                f"<p>{paragraph}</p><div>{division}</div><span>{span}</span>"
            )
        }

        result = filter_json.filter_artifact(artifact)

        self.assertEqual(result["url_visible_text"], span)

    def test_uses_leaf_div_only_when_no_paragraph_exists(self):
        excerpt = " ".join(f"detail{i}." for i in range(42))
        artifact = {
            "url_raw_body": (
                f"<div><div>nested container</div></div><div>{excerpt}</div>"
            )
        }

        result = filter_json.filter_artifact(artifact)

        self.assertEqual(result["url_visible_text"], excerpt.replace(".", ""))

    def test_missing_html_returns_empty_extracted_fields(self):
        result = filter_json.filter_artifact({"url_raw_body": ""})

        self.assertEqual(result["title"], "")
        self.assertEqual(result["h1_tags"], [])
        self.assertEqual(result["h2_tags"], [])
        self.assertEqual(result["url_visible_text"], "")

    def test_directory_continues_after_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "json"
            output_dir = root / "output"
            input_dir.mkdir()
            (input_dir / "bad.json").write_text("not json")
            (input_dir / "good.json").write_text(
                json.dumps({"url_raw_body": "<title>Working Site</title>"})
            )

            with redirect_stderr(io.StringIO()):
                counts = filter_json.filter_directory(input_dir, output_dir)

            self.assertEqual(counts, {"written": 1, "failed": 1})
            result = json.loads((output_dir / "good.json").read_text())
            self.assertEqual(result["title"], "Working Site")


if __name__ == "__main__":
    unittest.main()
