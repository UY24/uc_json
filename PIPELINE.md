# UC JSON Pipeline

## Full Process

1. Read every row from the CSV.
2. Get the compressed S3 URL from `s3status`.
3. Download and Brotli-decompress the `.json.br` file.
4. Validate the JSON and save it as `json/{hashval}.json`.
5. Skip files already downloaded and continue past failed rows.
6. Parse each downloaded file's `url_raw_body`.
7. Write the compact result as `output/{hashval}.json`.

## Output Fields

```text
input_url
word_count
anchor_tag_count
anchor_tags_list
img_tag_count
lang_detected
title
h1_tags
h2_tags
url_visible_text
```

### Why These Fields Are Retained

- `input_url`: Identifies the website that was checked.
- `word_count`: Keeps the original page word count and indicates whether the page has substantial content.
- `anchor_tag_count`: Shows how many links and navigation elements exist.
- `anchor_tags_list`: Provides up to five example website sections from randomly sampled anchor paths.
- `img_tag_count`: Shows whether the page has visual content and normal website structure.
- `lang_detected`: Identifies the page language for the later LLM check.
- `title`: Provides the page's main browser title.
- `h1_tags`: Keeps up to three primary page headings.
- `h2_tags`: Keeps up to three secondary page headings.
- `url_visible_text`: Provides one complete content paragraph closest to 40 words.

`status_code`, `error-comment`, `is_go_daddy`, `final_result`, raw HTML and all other source fields are excluded.

## Anchor Processing

1. Take the last non-empty path segment from every anchor URL.
2. Remove file extensions and URL encoding.
3. Replace punctuation with spaces and convert text to lowercase.
4. Remove blanks, `index`, and duplicates.
5. Randomly select up to five values. Long names are allowed.

## HTML Content Extraction

1. Parse `url_raw_body` with the free `lxml` library.
2. Extract the page `<title>`.
3. Keep the first three unique, non-empty `<h1>` values.
4. Keep the first three unique, non-empty `<h2>` values.
5. Find the complete `<p>` whose word count is closest to 40.
6. Use a leaf `<div>` only when no paragraph exists.
7. Ignore paragraphs and divs inside navigation, header, footer, aside, script and style elements.
8. Return empty HTML fields when the body is missing or cannot be parsed.

## Text Cleanup

For `title`, headings, anchor paths and `url_visible_text`:

1. Normalize Unicode and whitespace.
2. Remove control characters, emojis and special symbols.
3. Replace every punctuation character with a space.
4. Collapse repeated spaces.

`input_url` remains unchanged because removing its punctuation would break the URL.

## Run the Complete Pipeline

From inside `uc_json` with the virtual environment active:

```bash
python main.py csv/tmp_full.csv && python filter_json.py
```

To download one file at a time:

```bash
python main.py csv/tmp_full.csv --concurrency 1 && python filter_json.py
```

## Run Tests

```bash
python -m unittest discover -s tests -v
```
