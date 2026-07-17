import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from processor import process_line


BASE_DIR = Path(__file__).parent


def save_result(result, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def download_one(row, output_dir, raw_dir):
    hashval = row.get("hashval", "").strip()
    s3status = row.get("s3status", "").strip()
    if not hashval or not s3status:
        raise ValueError("missing hashval or s3status")

    output_path = output_dir / f"{hashval}.json"
    raw_path = raw_dir / f"{hashval}.json"
    if output_path.exists() and raw_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and "headers" in existing:
                return "skipped", hashval
        except (OSError, json.JSONDecodeError):
            pass

    save_result(process_line(s3status, raw_path), output_path)
    return "downloaded", hashval


def process_rows(rows, output_dir, workers=10, raw_dir=BASE_DIR / "json"):
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(download_one, row, output_dir, raw_dir): row
            for row in rows
        }
        for future in as_completed(futures):
            try:
                status, _ = future.result()
                counts[status] += 1
            except Exception as error:
                counts["failed"] += 1
                print(f"FAILED {futures[future].get('hashval', '')}: {error}", file=sys.stderr)
    return counts


def main():
    parser = argparse.ArgumentParser(description="Download s3status JSON artifacts from a CSV")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=BASE_DIR / "output")
    parser.add_argument("--raw-dir", type=Path, default=BASE_DIR / "json")
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    with args.csv_path.open(newline="", encoding="utf-8", errors="replace") as file:
        counts = process_rows(
            list(csv.DictReader(file)),
            args.output_dir,
            args.concurrency,
            args.raw_dir,
        )

    print(" ".join(f"{name}={count}" for name, count in counts.items()))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
