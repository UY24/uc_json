import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")


def _positive_env(name, default, convert):
    try:
        value = convert(os.environ.get(name, default))
    except ValueError as error:
        raise ValueError(f"{name} must be a positive number") from error
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
BATCH_SIZE = _positive_env("GEMINI_BATCH_SIZE", 5000, int)
CONCURRENCY = _positive_env("GEMINI_CONCURRENCY", 3, int)
INPUT_USD_PER_MILLION = _positive_env(
    "GEMINI_INPUT_COST_PER_MILLION", 0.125, float
)
OUTPUT_USD_PER_MILLION = _positive_env(
    "GEMINI_OUTPUT_COST_PER_MILLION", 0.75, float
)
TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
    "SUBMIT_FAILED",
}
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["working", "not_working"],
        },
        "reason": {"type": "string"},
    },
    "required": ["status", "reason"],
}


def build_request(hashval, prompt, website):
    website_text = json.dumps(
        website,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "key": hashval,
        "request": {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"{prompt}\n\nWebsite JSON:\n{website_text}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
                "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            },
        },
    }


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def prepare_batches(input_dir, prompt_path, work_dir, batch_size=5000):
    input_dir = Path(input_dir)
    prompt_path = Path(prompt_path)
    work_dir = Path(work_dir)
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"prompt is empty: {prompt_path}")

    manifest_path = work_dir / "jobs.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(job.get("job_name") for job in manifest.get("jobs", [])):
            raise ValueError("submitted jobs already exist")

    input_paths = sorted(input_dir.glob("*.json"))
    if not input_paths:
        raise ValueError(f"no JSON files found: {input_dir}")

    inputs_dir = work_dir / "inputs"
    shutil.rmtree(inputs_dir, ignore_errors=True)
    inputs_dir.mkdir(parents=True)
    jobs = []
    seen = set()
    for index, start in enumerate(range(0, len(input_paths), batch_size), 1):
        input_path = inputs_dir / f"batch-{index:05d}.jsonl"
        batch = []
        for website_path in input_paths[start:start + batch_size]:
            hashval = website_path.stem
            if hashval in seen:
                raise ValueError(f"duplicate hashval: {hashval}")
            seen.add(hashval)
            try:
                website = json.loads(website_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON: {website_path}") from error
            if not isinstance(website, dict):
                raise ValueError(f"JSON is not an object: {website_path}")
            batch.append(build_request(hashval, prompt, website))
        input_path.write_text(
            "".join(
                json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                + "\n"
                for item in batch
            ),
            encoding="utf-8",
        )
        jobs.append(
            {
                "input_file": str(input_path.relative_to(work_dir)),
                "request_count": len(batch),
                "uploaded_file": None,
                "job_name": None,
                "state": "PREPARED",
                "error": None,
                "raw_result": None,
            }
        )

    _write_json(manifest_path, {"model": MODEL, "jobs": jobs})
    return jobs


def gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is required")
    from google import genai

    return genai.Client(api_key=api_key)


def _state_name(state):
    return getattr(state, "name", state) or "JOB_STATE_PENDING"


def _submit_one(work_dir, entry, client, model):
    uploaded_file = entry.get("uploaded_file")
    try:
        if not uploaded_file:
            input_path = work_dir / entry["input_file"]
            uploaded = client.files.upload(
                file=str(input_path),
                config={
                    "display_name": input_path.stem,
                    "mime_type": "jsonl",
                },
            )
            uploaded_file = uploaded.name
        job = client.batches.create(
            model=model,
            src=uploaded_file,
            config={"display_name": Path(entry["input_file"]).stem},
        )
        return {
            "uploaded_file": uploaded_file,
            "job_name": job.name,
            "state": _state_name(job.state),
            "error": None,
        }
    except Exception as error:
        return {
            "uploaded_file": uploaded_file,
            "job_name": None,
            "state": "SUBMIT_FAILED",
            "error": str(error),
        }


def submit_batches(work_dir, concurrency=3, client=None):
    work_dir = Path(work_dir)
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    manifest_path = work_dir / "jobs.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model = manifest.get("model") or MODEL
    pending = [
        (index, entry.copy())
        for index, entry in enumerate(manifest.get("jobs", []))
        if not entry.get("job_name")
    ]
    if not pending:
        return manifest

    client = client or gemini_client()
    with ThreadPoolExecutor(max_workers=min(concurrency, len(pending))) as pool:
        futures = {
            pool.submit(_submit_one, work_dir, entry, client, model): index
            for index, entry in pending
        }
        for future in as_completed(futures):
            manifest["jobs"][futures[future]].update(future.result())
            _write_json(manifest_path, manifest)
    return manifest


def _error_text(error):
    if isinstance(error, str):
        return error
    return json.dumps(error, ensure_ascii=False, separators=(",", ":"))


def normalize_response(item):
    response = item.get("response") or {}
    usage = response.get("usageMetadata") or {}
    input_tokens = int(usage.get("promptTokenCount") or 0)
    output_tokens = int(usage.get("candidatesTokenCount") or 0)
    thinking_tokens = int(usage.get("thoughtsTokenCount") or 0)
    total_tokens = int(
        usage.get("totalTokenCount")
        or input_tokens + output_tokens + thinking_tokens
    )
    input_cost = input_tokens / 1_000_000 * INPUT_USD_PER_MILLION
    output_cost = (
        (output_tokens + thinking_tokens)
        / 1_000_000
        * OUTPUT_USD_PER_MILLION
    )
    row = {
        "hashval": item.get("key"),
        "status": None,
        "reason": None,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens,
        "total_tokens": total_tokens,
        "input_cost_usd": input_cost,
        "output_cost_usd": output_cost,
        "total_cost_usd": input_cost + output_cost,
        "error": None,
    }

    if item.get("error"):
        row["error"] = _error_text(item["error"])
        return row

    try:
        parts = response["candidates"][0]["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts)
        classification = json.loads(text)
        status = classification.get("status")
        reason = classification.get("reason")
        if status not in {"working", "not_working"}:
            raise ValueError(f"invalid status: {status}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason is empty")
        row["status"] = status
        row["reason"] = reason.strip()
    except Exception as error:
        row["error"] = f"invalid model output: {error}"
    return row


def _input_keys(work_dir, entry):
    input_path = work_dir / entry["input_file"]
    return [
        json.loads(line)["key"]
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def rebuild_results(work_dir, manifest):
    work_dir = Path(work_dir)
    rows_by_key = {}
    terminal_errors = {
        "JOB_STATE_FAILED",
        "JOB_STATE_CANCELLED",
        "JOB_STATE_EXPIRED",
    }
    for entry in manifest.get("jobs", []):
        raw_result = entry.get("raw_result")
        if raw_result:
            raw_path = work_dir / raw_result
            for line in raw_path.read_text(encoding="utf-8").splitlines():
                if not line:
                    continue
                row = normalize_response(json.loads(line))
                if row["hashval"] in rows_by_key:
                    raise ValueError(f"duplicate result key: {row['hashval']}")
                rows_by_key[row["hashval"]] = row
        elif entry.get("state") in terminal_errors:
            for key in _input_keys(work_dir, entry):
                rows_by_key[key] = normalize_response(
                    {
                        "key": key,
                        "error": entry.get("error") or entry["state"],
                    }
                )

    rows = [rows_by_key[key] for key in sorted(rows_by_key)]
    results_path = work_dir / "results.jsonl"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = results_path.with_suffix(".jsonl.tmp")
    temporary_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    temporary_path.replace(results_path)

    summary = {
        "model": manifest.get("model", MODEL),
        "input_usd_per_million_tokens": INPUT_USD_PER_MILLION,
        "output_usd_per_million_tokens": OUTPUT_USD_PER_MILLION,
        "total_requests": len(rows),
        "successful_requests": sum(row["error"] is None for row in rows),
        "failed_requests": sum(row["error"] is not None for row in rows),
        "input_tokens": sum(row["input_tokens"] for row in rows),
        "output_tokens": sum(row["output_tokens"] for row in rows),
        "thinking_tokens": sum(row["thinking_tokens"] for row in rows),
        "total_tokens": sum(row["total_tokens"] for row in rows),
        "input_cost_usd": sum(row["input_cost_usd"] for row in rows),
        "output_cost_usd": sum(row["output_cost_usd"] for row in rows),
        "total_cost_usd": sum(row["total_cost_usd"] for row in rows),
    }
    _write_json(work_dir / "cost_summary.json", summary)
    return rows, summary


def collect_batches(
    work_dir,
    wait=False,
    poll_seconds=30,
    client=None,
):
    work_dir = Path(work_dir)
    if poll_seconds < 0:
        raise ValueError("poll_seconds cannot be negative")
    manifest_path = work_dir / "jobs.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if any(entry.get("job_name") for entry in manifest.get("jobs", [])):
        client = client or gemini_client()

    while True:
        all_terminal = True
        for entry in manifest.get("jobs", []):
            if entry.get("raw_result") or not entry.get("job_name"):
                continue
            job = client.batches.get(name=entry["job_name"])
            state = _state_name(job.state)
            entry["state"] = state
            job_error = getattr(job, "error", None)
            entry["error"] = _error_text(job_error) if job_error else None
            if state not in TERMINAL_STATES:
                all_terminal = False
                continue
            if state == "JOB_STATE_SUCCEEDED":
                destination = getattr(job, "dest", None)
                result_file = getattr(destination, "file_name", None)
                if not result_file:
                    entry["error"] = "succeeded job has no result file"
                    continue
                result = client.files.download(file=result_file)
                raw_path = (
                    work_dir
                    / "raw_results"
                    / f"{Path(entry['input_file']).stem}-results.jsonl"
                )
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(result)
                entry["raw_result"] = str(raw_path.relative_to(work_dir))

        _write_json(manifest_path, manifest)
        rows, summary = rebuild_results(work_dir, manifest)
        if not wait or all_terminal:
            return manifest, rows, summary
        time.sleep(poll_seconds)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Classify compact website JSON with Gemini Batch API"
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=BASE_DIR / "llm_batches",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--input-dir", type=Path, default=BASE_DIR / "output")
    prepare.add_argument(
        "--prompt",
        type=Path,
        default=BASE_DIR / "website_status_prompt.txt",
    )
    prepare.add_argument("--batch-size", type=int, default=BATCH_SIZE)

    submit = commands.add_parser("submit")
    submit.add_argument("--concurrency", type=int, default=CONCURRENCY)

    collect = commands.add_parser("collect")
    collect.add_argument("--wait", action="store_true")
    collect.add_argument("--poll-seconds", type=int, default=30)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            jobs = prepare_batches(
                args.input_dir,
                args.prompt,
                args.work_dir,
                args.batch_size,
            )
            print(
                f"prepared_requests={sum(job['request_count'] for job in jobs)} "
                f"batches={len(jobs)}"
            )
            return 0
        if args.command == "submit":
            manifest = submit_batches(
                args.work_dir,
                args.concurrency,
            )
            failed = sum(job.get("error") is not None for job in manifest["jobs"])
            submitted = sum(job.get("job_name") is not None for job in manifest["jobs"])
            print(f"submitted={submitted} failed={failed}")
            return 1 if failed else 0

        manifest, rows, summary = collect_batches(
            args.work_dir,
            args.wait,
            args.poll_seconds,
        )
        states = sorted({job["state"] for job in manifest["jobs"]})
        print(
            f"states={','.join(states)} results={len(rows)} "
            f"cost_usd={summary['total_cost_usd']:.8f}"
        )
        return 1 if summary["failed_requests"] else 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
