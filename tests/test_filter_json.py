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
                <img alt="Example, Logo!">
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
                "word_count",
                "anchor_tag_count",
                "anchor_tags_list",
                "title",
                "headers",
                "image_alt_tags",
                "page_text_snippet",
            },
        )
        self.assertEqual(result["word_count"], 500)
        self.assertEqual(result["title"], "Example Company")
        self.assertEqual(result["image_alt_tags"], ["Example Logo"])
        self.assertEqual(
            result["headers"],
            [
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
                " ".join(long.split()[:50]) + "...",
                closest.replace(",", ""),
                short,
            ],
        )
        self.assertEqual(len(result["anchor_tags_list"]), 5)
        self.assertIn(
            "/products/really-long-product-name/",
            result["anchor_tags_list"],
        )

    def test_collects_paragraph_leaf_div_and_leaf_span_over_10_words(self):
        paragraph = " ".join(f"paragraph{i}" for i in range(60))
        division = " ".join(f"division{i}" for i in range(44))
        span = " ".join(f"span{i}" for i in range(41))
        artifact = {
            "url_raw_body": (
                f"<p>{paragraph}</p><div>{division}</div><span>{span}</span>"
            )
        }

        result = processor._filter_artifact(artifact)

        self.assertEqual(
            result["page_text_snippet"],
            [" ".join(paragraph.split()[:50]) + "...", division, span],
        )

    def test_fills_remaining_slots_with_five_to_ten_word_content(self):
        short = " ".join(f"short{i}" for i in range(10))
        five = "one two three four five"
        four = "one two three four"
        excerpt = " ".join(f"detail{i}." for i in range(42))
        artifact = {
            "url_raw_body": (
                f"<header><p>{'header ' * 45}</p></header>"
                f"<p>{short}</p>"
                f"<p>{five}</p><p>{four}</p>"
                f"<div><span>{excerpt}</span></div>"
                f"<div>{excerpt}</div>"
            )
        }

        result = processor._filter_artifact(artifact)

        self.assertEqual(
            result["page_text_snippet"],
            [excerpt.replace(".", ""), short, five],
        )

    def test_keeps_five_largest_page_text_snippets(self):
        sizes = [11, 30, 60, 20, 12, 25]
        paragraphs = {
            size: " ".join(f"content{size}x{word}" for word in range(size))
            for size in sizes
        }
        artifact = {
            "url_raw_body": "".join(
                f"<p>{paragraphs[size]}</p>" for size in sizes
            )
        }

        result = processor._filter_artifact(artifact)

        self.assertEqual(
            result["page_text_snippet"],
            [
                " ".join(paragraphs[60].split()[:50]) + "...",
                paragraphs[30],
                paragraphs[25],
                paragraphs[20],
                paragraphs[12],
            ],
        )

    def test_missing_html_returns_empty_extracted_fields(self):
        result = processor._filter_artifact({"url_raw_body": ""})

        self.assertEqual(result["title"], "")
        self.assertEqual(result["headers"], [])
        self.assertEqual(result["image_alt_tags"], [])
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

    def test_headers_exclude_layout_and_prioritize_five_h1_values(self):
        html = """
            <nav><h1>Navigation Heading</h1></nav>
            <header><h2>Header Menu</h2></header>
            <footer><h3>Footer Heading</h3></footer>
            <aside><h4>Sidebar Heading</h4></aside>
            <h3>Third Level</h3>
            <h2>Second Level One</h2>
            <main><article><header><h1>Primary One!</h1></header></article></main>
            <h1>Primary Two!</h1>
            <h1>Primary Three!</h1>
            <h1>Primary Four!</h1>
            <h1>Primary Five!</h1>
            <h1>Primary Six!</h1>
            <h2>Second Level Two</h2>
            <h4>Fourth Level</h4>
            <h5>Fifth Level</h5>
            <h6>Sixth Level</h6>
        """

        result = processor._filter_artifact({"url_raw_body": html})

        self.assertEqual(
            result["headers"],
            [
                "Primary One",
                "Primary Two",
                "Primary Three",
                "Primary Four",
                "Primary Five",
                "Second Level One",
                "Second Level Two",
                "Third Level",
                "Fourth Level",
                "Fifth Level",
            ],
        )

    def test_randomly_keeps_fifteen_unique_cleaned_image_alt_tags(self):
        images = "".join(
            f'<img alt="Image, {number}!">'
            for number in range(17)
        )
        images += '<img alt="Image, 0!"><img alt="   ">'

        with patch("random.sample", side_effect=lambda values, count: values[:count]):
            result = processor._filter_artifact({"url_raw_body": images})

        self.assertEqual(
            result["image_alt_tags"],
            [f"Image {number}" for number in range(15)],
        )

if __name__ == "__main__":
    unittest.main()
