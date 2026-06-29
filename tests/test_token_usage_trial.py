from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.run_token_usage_trial import (
    build_artifact_summary,
    summarize_token_log,
)


class TokenUsageTrialTest(unittest.TestCase):
    def test_summarize_token_log_groups_usage_by_mode(self) -> None:
        records = [
            {"mode": "extractor", "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            {"mode": "extractor", "prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            {"mode": "baseline", "prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        ]

        summary = summarize_token_log(records)

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["total_calls"], 3)
        self.assertEqual(summary["total_tokens"], 45)
        self.assertEqual(summary["by_mode"]["extractor"]["calls"], 2)
        self.assertEqual(summary["by_mode"]["extractor"]["total_tokens"], 35)
        self.assertEqual(summary["by_mode"]["extractor"]["average_total_tokens"], 17.5)
        self.assertEqual(summary["by_mode"]["baseline"]["prompt_tokens"], 7)

    def test_build_artifact_summary_extracts_key_token_numbers(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            eval_dir = root / "outputs" / "eval"
            eval_dir.mkdir(parents=True)
            (eval_dir / "pipeline_token_budget.json").write_text(
                json.dumps(
                    {
                        "naive_direct_llm_full_excel": {"estimated_input_tokens": 1000},
                        "naive_direct_llm_required_columns": {"estimated_input_tokens": 100},
                    }
                ),
                encoding="utf-8",
            )
            (eval_dir / "eval_modes.json").write_text(
                json.dumps(
                    {
                        "modes": {
                            "regex_extractor_symbolic_verifier": {
                                "status": "ok",
                                "result_count": 93,
                                "total_tokens": 0,
                            },
                            "deepseek_extractor_symbolic_verifier": {
                                "status": "ok",
                                "result_count": 93,
                                "total_tokens": 834,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            (eval_dir / "fuzzy_deepseek_extractor_results.json").write_text(
                json.dumps(
                    {
                        "aggregate": {
                            "deepseek_extractor_symbolic_verifier": {
                                "score": 320,
                                "max": 320,
                                "tokens": 25334,
                                "cases": 40,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (eval_dir / "deepseek_token_usage.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "mode": "deepseek_extractor_symbolic_verifier",
                                "prompt_tokens": 300,
                                "completion_tokens": 534,
                                "total_tokens": 834,
                            }
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            summary = build_artifact_summary(root)

        self.assertEqual(summary["pipeline_token_budget"]["status"], "ok")
        self.assertEqual(
            summary["pipeline_token_budget"]["naive_full_excel_input_tokens"],
            1000,
        )
        self.assertEqual(summary["eval_modes"]["modes"]["regex_extractor_symbolic_verifier"]["total_tokens"], 0)
        self.assertEqual(summary["fuzzy_deepseek_extractor_results"]["aggregate"]["deepseek_extractor_symbolic_verifier"]["tokens"], 25334)
        self.assertEqual(summary["token_usage_log"]["total_tokens"], 834)

    def test_build_artifact_summary_marks_missing_files(self) -> None:
        with TemporaryDirectory() as directory:
            summary = build_artifact_summary(Path(directory))

        self.assertEqual(summary["pipeline_token_budget"]["status"], "missing")
        self.assertEqual(summary["eval_modes"]["status"], "missing")
        self.assertEqual(summary["token_usage_log"]["status"], "missing")


if __name__ == "__main__":
    unittest.main()
