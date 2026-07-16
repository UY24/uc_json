import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import brotli


BASE_DIR = Path(__file__).parent


def extract_s3_link(value):
    return parse_qs(urlparse(value).query).get("s3link", [value])[0]


def fetch_bytes(url):
    with urlopen(url, timeout=30) as response:
        return response.read()


def download_one(row, output_dir):
    hashval = row.get("hashval", "").strip()
    s3status = row.get("s3status", "").strip()
    if not hashval or not s3status:
        raise ValueError("missing hashval or s3status")

    path = output_dir / f"{hashval}.json"
    if path.exists():
        return "skipped", hashval

    text = brotli.decompress(fetch_bytes(extract_s3_link(s3status))).decode("utf-8")
    json.loads(text)
    path.write_text(text, encoding="utf-8")
    return "downloaded", hashval


def process_rows(rows, output_dir, workers=10):
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(download_one, row, output_dir): row for row in rows}
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
    parser.add_argument("--output-dir", type=Path, default=BASE_DIR / "json")
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    with args.csv_path.open(newline="", encoding="utf-8", errors="replace") as file:
        counts = process_rows(list(csv.DictReader(file)), args.output_dir, args.concurrency)

    print(" ".join(f"{name}={count}" for name, count in counts.items()))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
