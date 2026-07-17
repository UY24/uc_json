import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import llm_categoriser as categoriser


class ConfigTests(unittest.TestCase):
    def test_rejects_non_positive_numeric_environment_value(self):
        with patch.dict(os.environ, {"GEMINI_BATCH_SIZE": "0"}):
            with self.assertRaisesRegex(ValueError, "GEMINI_BATCH_SIZE"):
                categoriser._positive_env("GEMINI_BATCH_SIZE", 5000, int)

        with patch.dict(os.environ, {"GEMINI_BATCH_SIZE": "many"}):
            with self.assertRaisesRegex(ValueError, "GEMINI_BATCH_SIZE"):
                categoriser._positive_env("GEMINI_BATCH_SIZE", 5000, int)


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.input_dir = self.root / "output"
        self.work_dir = self.root / "llm_batches"
        self.prompt_path = self.root / "prompt.txt"
        self.input_dir.mkdir()
        self.prompt_path.write_text("classifier prompt", encoding="utf-8")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_website(self, hashval, value):
        (self.input_dir / f"{hashval}.json").write_text(
            json.dumps(value),
            encoding="utf-8",
        )

    def test_prepare_uses_filename_key_full_prompt_and_chunks_in_order(self):
        self.write_website("bbb", {"title": "Second"})
        self.write_website("aaa", {"title": "First"})

        batches = categoriser.prepare_batches(
            self.input_dir,
            self.prompt_path,
            self.work_dir,
            batch_size=1,
        )

        self.assertEqual(len(batches), 2)
        first_line = json.loads(
            (self.work_dir / "inputs" / "batch-00001.jsonl").read_text()
        )
        self.assertEqual(first_line["key"], "aaa")
        request = first_line["request"]
        text = request["contents"][0]["parts"][0]["text"]
        self.assertEqual(
            text,
            'classifier prompt\n\nWebsite JSON:\n{"title":"First"}',
        )
        config = request["generationConfig"]
        self.assertEqual(config["responseMimeType"], "application/json")
        self.assertEqual(
            config["responseSchema"]["properties"]["status"]["enum"],
            ["working", "not_working"],
        )
        self.assertEqual(
            config["thinkingConfig"],
            {"thinkingLevel": "MINIMAL"},
        )

        manifest = json.loads((self.work_dir / "jobs.json").read_text())
        self.assertEqual(manifest["model"], "gemini-3.1-flash-lite")
        self.assertEqual(
            [job["request_count"] for job in manifest["jobs"]],
            [1, 1],
        )
        self.assertEqual(manifest["jobs"][0]["state"], "PREPARED")
        self.assertIsNone(manifest["jobs"][0]["submitted_at"])
        self.assertIsNone(manifest["jobs"][0]["completed_at"])
        self.assertIsNone(manifest["jobs"][0]["elapsed_seconds"])

    def test_prepare_rejects_empty_prompt_invalid_json_and_batch_size(self):
        self.write_website("aaa", [])

        with self.assertRaisesRegex(ValueError, "batch_size"):
            categoriser.prepare_batches(
                self.input_dir,
                self.prompt_path,
                self.work_dir,
                batch_size=0,
            )

        self.prompt_path.write_text("   ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "prompt"):
            categoriser.prepare_batches(
                self.input_dir,
                self.prompt_path,
                self.work_dir,
                batch_size=1,
            )

        self.prompt_path.write_text("prompt", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "aaa.json"):
            categoriser.prepare_batches(
                self.input_dir,
                self.prompt_path,
                self.work_dir,
                batch_size=1,
            )

    def test_prepare_refuses_to_replace_submitted_jobs(self):
        self.write_website("aaa", {"title": "Site"})
        self.work_dir.mkdir()
        (self.work_dir / "jobs.json").write_text(
            json.dumps({"jobs": [{"job_name": "batches/existing"}]}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "submitted"):
            categoriser.prepare_batches(
                self.input_dir,
                self.prompt_path,
                self.work_dir,
                batch_size=1,
            )


class FakeFiles:
    def __init__(self):
        self.upload_calls = []

    def upload(self, file, config):
        self.upload_calls.append((file, config))
        return SimpleNamespace(name=f"files/{Path(file).stem}")


class FakeBatches:
    def __init__(self, fail_src=None):
        self.create_calls = []
        self.fail_src = fail_src

    def create(self, model, src, config):
        self.create_calls.append((model, src, config))
        if src == self.fail_src:
            raise RuntimeError("creation failed")
        return SimpleNamespace(
            name=f"batches/{Path(src).name}",
            state=SimpleNamespace(name="JOB_STATE_PENDING"),
        )


class FakeClient:
    def __init__(self, fail_src=None):
        self.files = FakeFiles()
        self.batches = FakeBatches(fail_src)


class SubmitTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temporary_directory.name)
        inputs_dir = self.work_dir / "inputs"
        inputs_dir.mkdir()
        jobs = []
        for number in (1, 2):
            name = f"batch-{number:05d}.jsonl"
            (inputs_dir / name).write_text("{}\n", encoding="utf-8")
            jobs.append(
                {
                    "input_file": f"inputs/{name}",
                    "request_count": 1,
                    "uploaded_file": None,
                    "job_name": None,
                    "state": "PREPARED",
                    "error": None,
                    "raw_result": None,
                }
            )
        (self.work_dir / "jobs.json").write_text(
            json.dumps({"model": categoriser.MODEL, "jobs": jobs}),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_submit_records_jobs_and_does_not_submit_twice(self):
        client = FakeClient()

        with patch("llm_categoriser.time.time", return_value=100.0):
            categoriser.submit_batches(self.work_dir, concurrency=2, client=client)
            categoriser.submit_batches(self.work_dir, concurrency=2, client=client)

        manifest = json.loads((self.work_dir / "jobs.json").read_text())
        self.assertEqual(
            [job["uploaded_file"] for job in manifest["jobs"]],
            ["files/batch-00001", "files/batch-00002"],
        )
        self.assertEqual(
            [job["job_name"] for job in manifest["jobs"]],
            ["batches/batch-00001", "batches/batch-00002"],
        )
        self.assertEqual(len(client.files.upload_calls), 2)
        self.assertEqual(len(client.batches.create_calls), 2)
        self.assertEqual(
            [job["submitted_at"] for job in manifest["jobs"]],
            [100.0, 100.0],
        )

    def test_submit_keeps_other_jobs_when_one_creation_fails(self):
        client = FakeClient(fail_src="files/batch-00001")

        categoriser.submit_batches(self.work_dir, concurrency=2, client=client)

        jobs = json.loads((self.work_dir / "jobs.json").read_text())["jobs"]
        self.assertEqual(jobs[0]["uploaded_file"], "files/batch-00001")
        self.assertIsNone(jobs[0]["job_name"])
        self.assertIn("creation failed", jobs[0]["error"])
        self.assertEqual(jobs[1]["job_name"], "batches/batch-00002")

    def test_submit_uses_model_saved_in_manifest(self):
        manifest_path = self.work_dir / "jobs.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["model"] = "gemini-test-model"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        client = FakeClient()

        categoriser.submit_batches(self.work_dir, client=client)

        self.assertEqual(
            [call[0] for call in client.batches.create_calls],
            ["gemini-test-model", "gemini-test-model"],
        )


class ResultTests(unittest.TestCase):
    def success_item(self, key="aaa", thoughts=5):
        usage = {
            "promptTokenCount": 100,
            "candidatesTokenCount": 20,
            "totalTokenCount": 125,
        }
        if thoughts is not None:
            usage["thoughtsTokenCount"] = thoughts
        return {
            "key": key,
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "status": "working",
                                            "reason": "The page has coherent business content.",
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": usage,
            },
        }

    def test_normalizes_classification_tokens_and_cost(self):
        row = categoriser.normalize_response(self.success_item())

        self.assertEqual(row["hashval"], "aaa")
        self.assertEqual(row["status"], "working")
        self.assertEqual(row["input_tokens"], 100)
        self.assertEqual(row["output_tokens"], 20)
        self.assertEqual(row["thinking_tokens"], 5)
        self.assertEqual(row["total_tokens"], 125)
        self.assertAlmostEqual(
            row["input_cost_usd"],
            100 / 1_000_000 * categoriser.INPUT_USD_PER_MILLION,
        )
        self.assertAlmostEqual(
            row["output_cost_usd"],
            25 / 1_000_000 * categoriser.OUTPUT_USD_PER_MILLION,
        )
        self.assertAlmostEqual(
            row["total_cost_usd"],
            row["input_cost_usd"] + row["output_cost_usd"],
        )
        self.assertIsNone(row["error"])

    def test_normalizes_request_and_malformed_response_errors(self):
        request_error = categoriser.normalize_response(
            {"key": "bbb", "error": {"code": 400, "message": "bad request"}}
        )
        malformed = self.success_item("ccc")
        malformed["response"]["candidates"][0]["content"]["parts"][0][
            "text"
        ] = "not json"

        malformed_row = categoriser.normalize_response(malformed)

        self.assertIsNone(request_error["status"])
        self.assertIn("bad request", request_error["error"])
        self.assertIsNone(malformed_row["status"])
        self.assertIn("model output", malformed_row["error"])

    def test_missing_thinking_tokens_default_to_zero(self):
        row = categoriser.normalize_response(self.success_item(thoughts=None))

        self.assertEqual(row["thinking_tokens"], 0)

    def test_rebuilds_sorted_results_and_cost_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            work_dir = Path(directory)
            raw_dir = work_dir / "raw_results"
            raw_dir.mkdir()
            raw_path = raw_dir / "batch-00001-results.jsonl"
            raw_path.write_text(
                "\n".join(
                    [
                        json.dumps(self.success_item("bbb")),
                        json.dumps(
                            {
                                "key": "aaa",
                                "error": {"message": "blocked"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            manifest = {
                "model": categoriser.MODEL,
                "jobs": [
                    {
                        "state": "JOB_STATE_SUCCEEDED",
                        "raw_result": "raw_results/batch-00001-results.jsonl",
                    }
                ],
            }

            rows, summary = categoriser.rebuild_results(work_dir, manifest)

            self.assertEqual([row["hashval"] for row in rows], ["aaa", "bbb"])
            self.assertEqual(summary["total_requests"], 2)
            self.assertEqual(summary["successful_requests"], 1)
            self.assertEqual(summary["failed_requests"], 1)
            self.assertEqual(summary["input_tokens"], 100)
            self.assertAlmostEqual(
                summary["total_cost_usd"],
                rows[1]["total_cost_usd"],
            )
            self.assertTrue((work_dir / "results.jsonl").exists())
            self.assertTrue((work_dir / "cost_summary.json").exists())


class CollectFiles:
    def __init__(self, content):
        self.content = content
        self.download_calls = []

    def download(self, file):
        self.download_calls.append(file)
        return self.content


class CollectBatches:
    def __init__(self, jobs):
        self.jobs = list(jobs)
        self.get_calls = []

    def get(self, name):
        self.get_calls.append(name)
        return self.jobs.pop(0) if len(self.jobs) > 1 else self.jobs[0]


class CollectClient:
    def __init__(self, jobs, content):
        self.batches = CollectBatches(jobs)
        self.files = CollectFiles(content)


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temporary_directory.name)
        inputs_dir = self.work_dir / "inputs"
        inputs_dir.mkdir()
        (inputs_dir / "batch-00001.jsonl").write_text(
            json.dumps({"key": "aaa", "request": {}}) + "\n",
            encoding="utf-8",
        )
        (self.work_dir / "jobs.json").write_text(
            json.dumps(
                {
                    "model": categoriser.MODEL,
                    "jobs": [
                        {
                            "input_file": "inputs/batch-00001.jsonl",
                            "request_count": 1,
                            "uploaded_file": "files/input",
                            "job_name": "batches/job-1",
                            "state": "JOB_STATE_PENDING",
                            "error": None,
                            "raw_result": None,
                            "submitted_at": 100.0,
                            "completed_at": None,
                            "elapsed_seconds": None,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.result_content = (
            json.dumps(ResultTests().success_item("aaa")) + "\n"
        ).encode()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def job(self, state, result_file=None):
        dest = SimpleNamespace(file_name=result_file) if result_file else None
        return SimpleNamespace(
            state=SimpleNamespace(name=state),
            dest=dest,
            error=None,
        )

    def test_collect_downloads_success_once_and_builds_results(self):
        client = CollectClient(
            [self.job("JOB_STATE_SUCCEEDED", "files/results")],
            self.result_content,
        )

        with patch("llm_categoriser.time.time", return_value=112.5):
            categoriser.collect_batches(self.work_dir, client=client)
            categoriser.collect_batches(self.work_dir, client=client)

        manifest = json.loads((self.work_dir / "jobs.json").read_text())
        self.assertEqual(
            manifest["jobs"][0]["raw_result"],
            "raw_results/batch-00001-results.jsonl",
        )
        self.assertEqual(client.files.download_calls, ["files/results"])
        self.assertEqual(manifest["jobs"][0]["completed_at"], 112.5)
        self.assertEqual(manifest["jobs"][0]["elapsed_seconds"], 12.5)
        row = json.loads((self.work_dir / "results.jsonl").read_text())
        self.assertEqual(row["status"], "working")

    def test_collect_waits_until_job_is_terminal(self):
        client = CollectClient(
            [
                self.job("JOB_STATE_RUNNING"),
                self.job("JOB_STATE_SUCCEEDED", "files/results"),
            ],
            self.result_content,
        )

        with patch("llm_categoriser.time.sleep") as sleep:
            categoriser.collect_batches(
                self.work_dir,
                wait=True,
                poll_seconds=1,
                client=client,
            )

        sleep.assert_called_once_with(1)
        self.assertEqual(client.files.download_calls, ["files/results"])

    def test_cli_parser_supports_prepare_submit_and_collect(self):
        with (
            patch.object(categoriser, "BATCH_SIZE", 7),
            patch.object(categoriser, "CONCURRENCY", 4),
        ):
            parser = categoriser.build_parser()

        self.assertEqual(parser.parse_args(["prepare"]).batch_size, 7)
        self.assertEqual(parser.parse_args(["submit"]).concurrency, 4)
        self.assertEqual(
            parser.parse_args(["prepare", "--batch-size", "9"]).batch_size,
            9,
        )
        self.assertEqual(
            parser.parse_args(["submit", "--concurrency", "2"]).concurrency,
            2,
        )
        collect = parser.parse_args(["collect", "--wait"])
        self.assertTrue(collect.wait)
        self.assertEqual(collect.poll_seconds, 30)

    def test_run_prepares_submits_collects_and_prints_batch_timing(self):
        submitted = {
            "jobs": [
                {
                    "input_file": f"inputs/batch-{index:05d}.jsonl",
                    "job_name": f"batches/job-{index}",
                    "state": "JOB_STATE_PENDING",
                    "error": None,
                }
                for index in range(1, 4)
            ]
        }
        completed = {
            "jobs": [
                {
                    **job,
                    "state": "JOB_STATE_SUCCEEDED",
                    "elapsed_seconds": 12.5 + index,
                }
                for index, job in enumerate(submitted["jobs"])
            ]
        }
        client = object()
        with (
            patch(
                "llm_categoriser.prepare_batches",
                return_value=[{"request_count": 5}] * 3,
            ) as prepare,
            patch("llm_categoriser.submit_batches", return_value=submitted) as submit,
            patch(
                "llm_categoriser.collect_batches",
                return_value=(completed, [{}] * 15, {"total_cost_usd": 0.01, "failed_requests": 0}),
            ) as collect,
            patch("llm_categoriser.gemini_client", return_value=client),
            patch("llm_categoriser.time.monotonic", side_effect=[10.0, 16.0]),
            patch("builtins.print") as output,
        ):
            status = categoriser.main(
                [
                    "--work-dir",
                    "/tmp/batches",
                    "run",
                    "--input-dir",
                    "/tmp/output",
                    "--prompt",
                    "/tmp/prompt.txt",
                    "--batch-size",
                    "5",
                    "--concurrency",
                    "3",
                    "--poll-seconds",
                    "0",
                ]
            )

        self.assertEqual(status, 0)
        prepare.assert_called_once_with(
            Path("/tmp/output"),
            Path("/tmp/prompt.txt"),
            Path("/tmp/batches"),
            5,
        )
        submit.assert_called_once_with(Path("/tmp/batches"), 3, client)
        collect.assert_called_once_with(Path("/tmp/batches"), True, 0, client)
        text = "\n".join(str(call.args[0]) for call in output.call_args_list)
        self.assertIn("batches/job-1", text)
        self.assertIn("elapsed_seconds=12.5", text)
        self.assertIn("results=15", text)
        self.assertIn("total_seconds=6.0", text)


if __name__ == "__main__":
    unittest.main()
