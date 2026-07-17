# uc_json

Downloads Brotli-compressed JSON files from the `s3status` column of a CSV and saves compact JSON files for later LLM processing.

## Setup

Run from `/Users/ujjwalyadav/coding/forage`:

```bash
python3 -m venv uc_json/.venv
uc_json/.venv/bin/python -m pip install -r uc_json/requirements.txt
```

## Run

Process every S3 link from the full CSV:

```bash
uc_json/.venv/bin/python uc_json/main.py uc_json/csv/tmp_full.csv
```

For the three-row sample, use:

```bash
uc_json/.venv/bin/python uc_json/main.py uc_json/csv/tmp3.csv
```

Downloaded raw JSON files are written to `uc_json/json`. Compact files are written to `uc_json/output`.

In Python, `process_line(s3link)` downloads one artifact and returns its compact dictionary without saving it:

```python
from processor import process_line

result = process_line(s3link)
```

To embed it in another codebase, copy `processor.py` and install `brotli` and `lxml`. `process_line` is the file's only public function. Pass an optional path as `process_line(s3link, raw_path)` when the decompressed source JSON should also be saved.

The filter keeps `word_count`, `anchor_tag_count`, up to five random non-root paths without domains or query strings in `anchor_tags_list`, the page `title`, up to ten `headers` from `h1` through `h6`, up to fifteen random cleaned `image_alt_tags`, and `page_text_snippet`. The snippet field is a list of up to five random, unique paragraphs or leaf divs/spans containing more than 10 words. Each is limited to 50 words and receives `...` when truncated. Punctuation, decorative symbols, and extra whitespace are removed from extracted text.

## Test

```bash
uc_json/.venv/bin/python -m unittest discover -s uc_json/tests -v
```
