import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse


BASE_DIR = Path(__file__).parent
CHUNK_WORDS = 99
MAX_CHUNKS = 9
FAILURE_SIGNALS = (
    "404",
    "403",
    "not found",
    "access denied",
    "captcha",
    "verify you are human",
    "unavailable",
    "under construction",
    "parked",
    "forbidden",
    "server error",
)
FIELDS = (
    "status_code",
    "error-comment",
    "is_go_daddy",
    "wc",
    "anchor_tag_count",
    "anchor_tagst",
    "img_tag_count",
    "lang_detected",
    "url_visible_text",
)


def _clean_text(text):
    characters = []
    for character in unicodedata.normalize("NFKC", text):
        category = unicodedata.category(character)
        if character.isspace() or (
            not category.startswith("C")
            and category not in {"So", "Sk"}
            and character not in {"\ufe0e", "\ufe0f"}
        ):
            characters.append(character)
    text = re.sub(r"([.,!?])\1+", r"\1", "".join(characters))
    return " ".join(text.split())


def _unique_chunks(words):
    chunks = []
    seen = set()
    for start in range(0, len(words), CHUNK_WORDS):
        chunk = words[start : start + CHUNK_WORDS]
        key = " ".join(chunk).casefold()
        if key not in seen:
            seen.add(key)
            chunks.append(chunk)
    return chunks


def process_visible_text(text):
    text = _clean_text(text)
    words = text.split()
    if len(words) <= 900:
        return text

    chunks = _unique_chunks(words)
    if len(chunks) <= MAX_CHUNKS:
        return " ... ".join(" ".join(chunk) for chunk in chunks)

    selected = {0, 1, len(chunks) - 1}
    for index, chunk in enumerate(chunks):
        if len(selected) == MAX_CHUNKS:
            break
        lowered = " ".join(chunk).casefold()
        if any(signal in lowered for signal in FAILURE_SIGNALS):
            selected.add(index)

    candidates = [index for index in range(len(chunks)) if index not in selected]
    needed = MAX_CHUNKS - len(selected)
    for slot in range(needed):
        position = (slot + 1) * len(candidates) // (needed + 1)
        selected.add(candidates[position])

    return " ... ".join(" ".join(chunks[index]) for index in sorted(selected))


def anchor_paths(urls):
    paths = []
    for url in urls:
        segment = unquote(urlparse(str(url)).path).rstrip("/").rsplit("/", 1)[-1]
        name = segment.rsplit(".", 1)[0].replace("-", " ").replace("_", " ")
        name = " ".join(name.lower().split())
        if name and name != "index" and len(name) <= 10 and name not in paths:
            paths.append(name)
        if len(paths) == 5:
            break
    return paths


def filter_artifact(artifact):
    result = {field: artifact.get(field) for field in FIELDS}
    result["anchor_tagst"] = anchor_paths(artifact.get("anchor_tagst") or [])
    result["url_visible_text"] = process_visible_text(
        artifact.get("url_visible_text") or ""
    )
    return result


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
