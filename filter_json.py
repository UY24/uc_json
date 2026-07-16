import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


BASE_DIR = Path(__file__).parent
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


def process_visible_text(text):
    return text


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
