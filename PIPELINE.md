# UC JSON Pipeline

## Full Process

1. Read every row from the CSV.
2. Get the compressed S3 URL from `s3status`.
3. Pass the URL to `process_line(s3link)`.
4. Download and Brotli-decompress the `.json.br` file.
5. Save the decompressed source as `json/{hashval}.json`.
6. Validate the JSON and parse its `url_raw_body`.
7. Return the compact dictionary from `process_line`.
8. Save that dictionary as `output/{hashval}.json`.
9. Skip rows only when both files already exist and continue past failed rows.

All download and filtering logic lives in `processor.py`. Its only public
function is `process_line`; `main.py` handles CSV rows and saving separately.

## Output Fields

```text
word_count
anchor_tag_count
anchor_tags_list
title
headers
image_alt_tags
page_text_snippet
```

### Why These Fields Are Retained

- `word_count`: Keeps the original page word count and indicates whether the page has substantial content.
- `anchor_tag_count`: Shows how many links and navigation elements exist.
- `anchor_tags_list`: Provides up to five randomly sampled complete paths without domains, query strings, or fragments.
- `title`: Provides the page's main browser title.
- `headers`: Keeps up to five cleaned H1 values first, then fills the ten-item limit from H2 through H6.
- `image_alt_tags`: Keeps up to fifteen random, unique, cleaned, non-empty image alt texts.
- `page_text_snippet`: Provides up to five unique page-content items, prioritized by cleaned word count from largest to smallest.

`input_url`, `img_tag_count`, `status_code`, `error-comment`, `is_go_daddy`, `final_result`, raw HTML and all other source fields are excluded.

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
3. Ignore navigation, footer, aside and global site-header headings; allow article headers inside `main` or `article`.
4. Keep up to five unique H1 values first, then fill the ten-item limit from H2 through H6.
5. Keep up to fifteen random, unique, cleaned, non-empty `<img alt>` values.
6. Collect valid `<p>` elements and leaf `<div>` and `<span>` elements.
7. Rank candidates containing more than 10 cleaned words from largest to smallest.
8. Fill remaining slots with candidates containing 5 to 10 words, also largest first.
9. Keep at most five unique candidates.
10. Truncate each candidate to its first 50 words and append `...` when truncated.
11. Ignore candidates inside navigation, header, footer, aside, script and style elements.
12. Return empty lists when the body is missing or cannot be parsed.

## Text Cleanup

For `title`, `headers`, `image_alt_tags` and `page_text_snippet`:

1. Normalize Unicode and whitespace.
2. Remove control characters, emojis and special symbols.
3. Replace every punctuation character with a space.
4. Collapse repeated spaces.

The truncation marker `...` is added to long snippets after cleanup.
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
