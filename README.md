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

Compact files are written directly to `uc_json/output`.

In Python, `process_line(s3link)` downloads one artifact and returns its compact dictionary without saving it. The CSV flow uses `save_result` to write that returned dictionary.

The filter keeps `input_url`, `word_count`, `anchor_tag_count`, up to five random non-root paths without domains or query strings in `anchor_tags_list`, `img_tag_count`, the page `title`, up to three `h1_tags`, up to five `h2_tags`, and `page_text_snippet`. The snippet field is a list of up to five random, unique paragraphs or leaf divs/spans containing more than 40 words, truncated to 50 words each. Punctuation and decorative symbols are removed from extracted human-readable text.

## Test

```bash
uc_json/.venv/bin/python -m unittest discover -s uc_json/tests -v
```
