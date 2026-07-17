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
                "page_text_snippet",
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
        self.assertEqual(
            result["page_text_snippet"],
            [
                closest.replace(",", ""),
                " ".join(long.split()[:50]),
            ],
        )
        self.assertEqual(len(result["anchor_tags_list"]), 5)
        self.assertIn(
            "/products/really-long-product-name/",
            result["anchor_tags_list"],
        )

    def test_collects_paragraph_leaf_div_and_leaf_span_over_40_words(self):
        paragraph = " ".join(f"paragraph{i}" for i in range(60))
        division = " ".join(f"division{i}" for i in range(44))
        span = " ".join(f"span{i}" for i in range(41))
        artifact = {
            "url_raw_body": (
                f"<p>{paragraph}</p><div>{division}</div><span>{span}</span>"
            )
        }

        result = filter_json.filter_artifact(artifact)

        self.assertCountEqual(
            result["page_text_snippet"],
            [" ".join(paragraph.split()[:50]), division, span],
        )

    def test_ignores_short_nested_duplicate_and_excluded_content(self):
        short = " ".join(f"short{i}" for i in range(40))
        excerpt = " ".join(f"detail{i}." for i in range(42))
        artifact = {
            "url_raw_body": (
                f"<header><p>{'header ' * 45}</p></header>"
                f"<p>{short}</p>"
                f"<div><span>{excerpt}</span></div>"
                f"<div>{excerpt}</div>"
            )
        }

        result = filter_json.filter_artifact(artifact)

        self.assertEqual(
            result["page_text_snippet"],
            [excerpt.replace(".", "")],
        )

    def test_randomly_limits_page_text_snippet_to_five_items(self):
        paragraphs = [
            " ".join(f"content{number}x{word}" for word in range(41))
            for number in range(7)
        ]
        artifact = {
            "url_raw_body": "".join(f"<p>{value}</p>" for value in paragraphs)
        }

        with patch("random.sample", side_effect=lambda values, count: values[:count]):
            result = filter_json.filter_artifact(artifact)

        self.assertEqual(result["page_text_snippet"], paragraphs[:5])

    def test_missing_html_returns_empty_extracted_fields(self):
        result = filter_json.filter_artifact({"url_raw_body": ""})

        self.assertEqual(result["title"], "")
        self.assertEqual(result["h1_tags"], [])
        self.assertEqual(result["h2_tags"], [])
        self.assertEqual(result["page_text_snippet"], [])

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
