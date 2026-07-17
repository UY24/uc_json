# UC JSON Pipeline

## Full Process

1. Read every row from the CSV.
2. Get the compressed S3 URL from `s3status`.
3. Pass the URL to `process_line(s3link)`.
4. Download and Brotli-decompress the `.json.br` file.
5. Validate the JSON and parse its `url_raw_body`.
6. Return the compact dictionary from `process_line`.
7. Save that dictionary as `output/{hashval}.json`.
8. Skip files already processed and continue past failed rows.

All download and filtering logic lives in `processor.py`. Its only public
function is `process_line`; `main.py` handles CSV rows and saving separately.

## Output Fields

```text
input_url
word_count
anchor_tag_count
anchor_tags_list
img_tag_count
title
h1_tags
h2_tags
page_text_snippet
```

### Why These Fields Are Retained

- `input_url`: Identifies the website that was checked.
- `word_count`: Keeps the original page word count and indicates whether the page has substantial content.
- `anchor_tag_count`: Shows how many links and navigation elements exist.
- `anchor_tags_list`: Provides up to five randomly sampled complete paths without domains, query strings, or fragments.
- `img_tag_count`: Shows whether the page has visual content and normal website structure.
- `title`: Provides the page's main browser title.
- `h1_tags`: Keeps up to three primary page headings.
- `h2_tags`: Keeps up to five secondary page headings.
- `page_text_snippet`: Provides up to five random, unique page-content items containing 41 to 50 cleaned words.

`status_code`, `error-comment`, `is_go_daddy`, `final_result`, raw HTML and all other source fields are excluded.

## Anchor Processing

1. Keep the complete decoded path from every anchor URL.
2. Remove the domain, query string, and fragment.
3. Preserve nested segments, slashes, punctuation, and file extensions.
4. Remove duplicate paths and the exact root path `/`.
5. Randomly select up to five values.

Example:

```text
https://www.goodreads.com/blog/show/3146?ref=literalsummer_eb
-> /blog/show/3146
```

## HTML Content Extraction

1. Parse `url_raw_body` with the free `lxml` library.
2. Extract the page `<title>`.
3. Keep the first three unique, non-empty `<h1>` values.
4. Keep the first five unique, non-empty `<h2>` values.
5. Collect valid `<p>` elements and leaf `<div>` and `<span>` elements.
6. Keep unique candidates containing more than 40 cleaned words.
7. Truncate each candidate to its first 50 words.
8. Randomly select up to five candidates and return them as a list.
9. Ignore candidates inside navigation, header, footer, aside, script and style elements.
10. Return an empty snippet list when the body is missing or cannot be parsed.

## Text Cleanup

For `title`, headings and `page_text_snippet`:

1. Normalize Unicode and whitespace.
2. Remove control characters, emojis and special symbols.
3. Replace every punctuation character with a space.
4. Collapse repeated spaces.

`input_url` remains unchanged because removing its punctuation would break the URL.
`anchor_tags_list` also preserves punctuation because it stores URL paths.

## Run the Complete Pipeline

From inside `uc_json` with the virtual environment active:

```bash
python main.py csv/tmp_full.csv
```

To download one file at a time:

```bash
python main.py csv/tmp_full.csv --concurrency 1
```

## Run Tests

```bash
python -m unittest discover -s tests -v
```
