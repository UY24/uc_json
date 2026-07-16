import json
import random
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

from lxml import etree, html


BASE_DIR = Path(__file__).parent
EXCLUDED_TAGS = {"nav", "header", "footer", "aside", "script", "style"}
TAG_PRIORITY = {"p": 0, "div": 1, "span": 2}


def clean_text(value):
    characters = []
    for character in unicodedata.normalize("NFKC", value or ""):
        category = unicodedata.category(character)
        if character.isspace() or category.startswith("P"):
            characters.append(" ")
        elif (
            not category.startswith("C")
            and not category.startswith("S")
            and character not in {"\ufe0e", "\ufe0f"}
        ):
            characters.append(character)
    return " ".join("".join(characters).split())


def anchor_paths(urls):
    paths = []
    for url in urls:
        path = unquote(urlparse(str(url)).path) or "/"
        if path != "/" and path not in paths:
            paths.append(path)
    return random.sample(paths, min(5, len(paths)))


def _allowed(element):
    return not any(
        str(node.tag).lower() in EXCLUDED_TAGS
        for node in (element, *element.iterancestors())
    )


def _unique_tag_texts(root, tag, limit=3):
    values = []
    for element in root.xpath(f"//{tag}"):
        value = clean_text(element.text_content())
        if value and value not in values:
            values.append(value)
        if len(values) == limit:
            break
    return values


def _closest_content(root):
    candidates = []
    for order, element in enumerate(root.xpath("//p | //div | //span")):
        tag = str(element.tag).lower()
        if not _allowed(element):
            continue
        if tag != "p" and element.xpath(".//p | .//div | .//span"):
            continue
        value = clean_text(element.text_content())
        if value:
            candidates.append(
                (abs(len(value.split()) - 40), TAG_PRIORITY[tag], order, value)
            )
    return min(candidates)[3] if candidates else ""


def extract_html_summary(raw_html):
    empty = {"title": "", "h1_tags": [], "h2_tags": [], "url_visible_text": ""}
    if not raw_html:
        return empty
    try:
        root = html.document_fromstring(raw_html)
    except (etree.ParserError, TypeError, ValueError):
        return empty

    titles = root.xpath("//title")
    return {
        "title": clean_text(titles[0].text_content()) if titles else "",
        "h1_tags": _unique_tag_texts(root, "h1"),
        "h2_tags": _unique_tag_texts(root, "h2", 5),
        "url_visible_text": _closest_content(root),
    }


def filter_artifact(artifact):
    summary = extract_html_summary(artifact.get("url_raw_body") or "")
    return {
        "input_url": artifact.get("input_url") or "",
        "word_count": artifact.get("wc"),
        "anchor_tag_count": artifact.get("anchor_tag_count"),
        "anchor_tags_list": anchor_paths(artifact.get("anchor_tagst") or []),
        "img_tag_count": artifact.get("img_tag_count"),
        **summary,
    }


def filter_directory(input_dir, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {"written": 0, "failed": 0}
    for input_path in sorted(input_dir.glob("*.json")):
        try:
            artifact = json.loads(input_path.read_text(encoding="utf-8"))
            if not isinstance(artifact, dict):
                raise ValueError("JSON artifact is not an object")
            output = json.dumps(filter_artifact(artifact), ensure_ascii=False, indent=2)
            (output_dir / input_path.name).write_text(output, encoding="utf-8")
            counts["written"] += 1
        except Exception as error:
            counts["failed"] += 1
            print(f"FAILED {input_path.name}: {error}", file=sys.stderr)
    return counts


def main():
    counts = filter_directory(BASE_DIR / "json", BASE_DIR / "output")
    print(" ".join(f"{name}={count}" for name, count in counts.items()))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
