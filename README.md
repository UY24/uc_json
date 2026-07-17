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

The filter keeps `word_count`, `anchor_tag_count`, up to five random non-root paths without domains or query strings in `anchor_tags_list`, the page `title`, up to ten `headers`, up to fifteen random cleaned `image_alt_tags`, and `page_text_snippet`. Navigation/sidebar/footer headings and global site-header headings are excluded, while article headers inside `main` or `article` remain valid. Up to five H1 values are kept first, then remaining header slots are filled from H2 through H6. The snippet field keeps up to five unique paragraphs or leaf divs/spans, largest first. Text over 10 words is prioritized, then remaining slots use text with at least 5 words. Each item is limited to 50 words and receives `...` when truncated. Punctuation, decorative symbols, and extra whitespace are removed from extracted text.

## Test

```bash
uc_json/.venv/bin/python -m unittest discover -s uc_json/tests -v
```

## Gemini Batch Classification

Create the local environment file and add your real API key:

```bash
cp .env.example .env
```

`.env` also controls the model, requests per batch, concurrent batch-job
submissions, and the input/output token prices used for cost reporting. It is
gitignored; `.env.example` contains the defaults. Explicit `--batch-size` and
`--concurrency` command-line values override `.env`.

Prepare keyed JSONL files from compact `output/*.json` files without making a
network request:

```bash
python llm_categoriser.py prepare --input-dir output --batch-size 5000
```

Upload the prepared files and create asynchronous Batch jobs:

```bash
python llm_categoriser.py submit --concurrency 3
```

Check once, or wait until every job is terminal:

```bash
python llm_categoriser.py collect
python llm_categoriser.py collect --wait
```

Generated inputs, job state, raw responses, normalized `results.jsonl`, and
`cost_summary.json` are stored under ignored `llm_batches/`. Only `submit`
creates billable work. The default stable `gemini-3.1-flash-lite` Batch prices
verified on 2026-07-17 are $0.125 per million input tokens and $0.75 per million
output/thinking tokens.
