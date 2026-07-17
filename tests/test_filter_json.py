import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import processor


class FilterJsonTests(unittest.TestCase):
    def test_anchor_paths_keep_full_path_and_remove_query(self):
        with patch("random.sample", side_effect=lambda values, count: values):
            result = processor._anchor_paths(
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
            result = processor._filter_artifact(artifact)

        self.assertEqual(
            set(result),
            {
                "input_url",
                "word_count",
                "anchor_tag_count",
                "anchor_tags_list",
                "img_tag_count",
                "title",
                "headers",
                "page_text_snippet",
            },
        )
        self.assertEqual(result["input_url"], artifact["input_url"])
        self.assertEqual(result["word_count"], 500)
        self.assertEqual(result["title"], "Example Company")
        self.assertEqual(
            result["headers"],
            [
                "Main Heading",
                "Second Heading",
                "Third Heading",
                "Fourth Heading",
                "Our Services",
                "About Us",
                "News",
                "Contact",
                "Careers",
                "Sixth Heading",
            ],
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

        result = processor._filter_artifact(artifact)

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

        result = processor._filter_artifact(artifact)

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
            result = processor._filter_artifact(artifact)

        self.assertEqual(result["page_text_snippet"], paragraphs[:5])

    def test_missing_html_returns_empty_extracted_fields(self):
        result = processor._filter_artifact({"url_raw_body": ""})

        self.assertEqual(result["title"], "")
        self.assertEqual(result["headers"], [])
        self.assertEqual(result["page_text_snippet"], [])

    def test_headers_include_h1_through_h6_in_page_order(self):
        html = "".join(
            f"<h{number}>Heading {number}!</h{number}>"
            for number in range(1, 7)
        )

        result = processor._filter_artifact({"url_raw_body": html})

        self.assertEqual(
            result["headers"],
            [f"Heading {number}" for number in range(1, 7)],
        )

if __name__ == "__main__":
    unittest.main()
