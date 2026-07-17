import json
import sys
from pathlib import Path

from processor import _filter_artifact


BASE_DIR = Path(__file__).parent
def filter_directory(input_dir, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {"written": 0, "failed": 0}
    for input_path in sorted(input_dir.glob("*.json")):
        try:
            artifact = json.loads(input_path.read_text(encoding="utf-8"))
            if not isinstance(artifact, dict):
                raise ValueError("JSON artifact is not an object")
            output = json.dumps(_filter_artifact(artifact), ensure_ascii=False, indent=2)
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
