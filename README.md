# uc_json

Downloads Brotli-compressed JSON files from the `s3status` column of a CSV, then creates filtered JSON files for later LLM processing.

## Setup

Run from `/Users/ujjwalyadav/coding/forage`:

```bash
python3 -m venv uc_json/.venv
uc_json/.venv/bin/python -m pip install -r uc_json/requirements.txt
```

## Run

Download JSON files from the full CSV:

```bash
uc_json/.venv/bin/python uc_json/main.py uc_json/csv/tmp_full.csv
```

For the three-row sample, use:

```bash
uc_json/.venv/bin/python uc_json/main.py uc_json/csv/tmp3.csv
```

Create filtered JSON files:

```bash
uc_json/.venv/bin/python uc_json/filter_json.py
```

Downloaded files are written to `uc_json/json`. Filtered files are written to `uc_json/output`.

The filter keeps `status_code`, `error-comment`, `is_go_daddy`, `wc`, `anchor_tag_count`, up to five short `anchor_tagst` paths, `img_tag_count`, `lang_detected`, and a cleaned, representative `url_visible_text` limited to 900 words. Text with 900 words or fewer is preserved after basic symbol and whitespace cleanup.

## Test

```bash
uc_json/.venv/bin/python -m unittest discover -s uc_json/tests -v
```
