import json
import random
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import urlopen

import brotli
from lxml import etree, html


_EXCLUDED_TAGS = {"nav", "header", "footer", "aside", "script", "style"}


def process_line(s3link: str, raw_path=None) -> dict:
    text = brotli.decompress(
        _fetch_bytes(_extract_s3_link(s3link.strip()))
    ).decode("utf-8")
    artifact = json.loads(text)
    if not isinstance(artifact, dict):
        raise ValueError("JSON artifact is not an object")
    if raw_path:
        raw_path = Path(raw_path)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(text, encoding="utf-8")
    return _filter_artifact(artifact)


def _extract_s3_link(value):
    return parse_qs(urlparse(value).query).get("s3link", [value])[0]


def _fetch_bytes(url):
    with urlopen(url, timeout=30) as response:
        return response.read()


def _clean_text(value):
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


def _anchor_paths(urls):
    paths = []
    for url in urls:
        path = unquote(urlparse(str(url)).path) or "/"
        if path != "/" and path not in paths:
            paths.append(path)
    return random.sample(paths, min(5, len(paths)))


def _allowed(element):
    return not any(
        str(node.tag).lower() in _EXCLUDED_TAGS
        for node in (element, *element.iterancestors())
    )


def _headers(root):
    values = []
    for element in root.xpath("//h1 | //h2 | //h3 | //h4 | //h5 | //h6"):
        value = _clean_text(element.text_content())
        if value and value not in values:
            values.append(value)
        if len(values) == 10:
            break
    return values


def _image_alt_tags(root):
    values = []
    for element in root.xpath("//img[@alt]"):
        value = _clean_text(element.get("alt"))
        if value and value not in values:
            values.append(value)
    return random.sample(values, min(15, len(values)))


def _page_text_snippets(root):
    candidates = []
    for element in root.xpath("//p | //div | //span"):
        tag = str(element.tag).lower()
        if not _allowed(element):
            continue
        if tag != "p" and element.xpath(".//p | .//div | .//span"):
            continue
        words = _clean_text(element.text_content()).split()
        value = " ".join(words[:50]) + ("..." if len(words) > 50 else "")
        if len(words) > 10 and value not in candidates:
            candidates.append(value)
    return random.sample(candidates, min(5, len(candidates)))


def _extract_html_summary(raw_html):
    empty = {
        "title": "",
        "headers": [],
        "image_alt_tags": [],
        "page_text_snippet": [],
    }
    if not raw_html:
        return empty
    try:
        root = html.document_fromstring(raw_html)
    except (etree.ParserError, TypeError, ValueError):
        return empty

    titles = root.xpath("//title")
    return {
        "title": _clean_text(titles[0].text_content()) if titles else "",
        "headers": _headers(root),
        "image_alt_tags": _image_alt_tags(root),
        "page_text_snippet": _page_text_snippets(root),
    }


def _filter_artifact(artifact):
    summary = _extract_html_summary(artifact.get("url_raw_body") or "")
    return {
        "word_count": artifact.get("wc"),
        "anchor_tag_count": artifact.get("anchor_tag_count"),
        "anchor_tags_list": _anchor_paths(artifact.get("anchor_tagst") or []),
        **summary,
    }
