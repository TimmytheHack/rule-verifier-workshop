from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from scripts.eval_modes import run_eval
from src.extractors.deepseek_extractor import DeepSeekExtractor, DeepSeekJSONResponse
from src.rules.rule_classifier import RuleClassifier
from src.rules.rule_verifier import RuleVerifier
from src.schema.schema_registry import SchemaRegistry


SCHEMA_PATH = "schemas/schema_registry.json"
TAXONOMY_PATH = "rules/rule_taxonomy.json"
AVAILABLE_COLUMNS = ["生源地", "科类", "专业名称", "城市", "专业组最低位次1", "学费"]


class FakeDeepSeekClient:
    def chat_json(self, system_prompt: str, user_prompt: str) -> DeepSeekJSONResponse:
        return DeepSeekJSONResponse(
            payload={
                "input": "我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。",
                "user_context": {
                    "source_province": "广东",
                    "subject_type": "物理",
                    "user_rank": 32000,
                },
                "preferences": {
                    "major_keyword": "计算机",
                    "preferred_cities": ["广州", "深圳"],
                    "risk_preference_raw": "稳一点",
                    "tuition_preference_raw": "太贵",
                    "major_expansion_raw": "计算机相关扩展",
                    "cooperation_preference_raw": "不想去太贵的中外合作",
                },
                "raw_phrases": [
                    "广东物理类",
                    "排位32000",
                    "想学计算机",
                    "最好在广州深圳",
                    "学校稳一点",
                    "不想去太贵的中外合作",
                ],
                "source_spans": [
                    {"path": "user_context.subject_type", "text": "物理类", "start": 4, "end": 7}
                ],
            },
            usage={"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33},
        )


class DeepSeekEvalModesTest(unittest.TestCase):
    def test_deepseek_extractor_output_still_goes_through_symbolic_verifier(self) -> None:
        slots = DeepSeekExtractor(client=FakeDeepSeekClient()).extract("demo")
        self.assertEqual(slots["deepseek_usage"]["total_tokens"], 33)
        self.assertIn("source_spans", slots)
        self.assertEqual(slots["user_context"]["subject_type"], "物理")
        self.assertEqual(slots["preferences"]["preferred_cities"], ["广州", "深圳"])

        registry = SchemaRegistry.from_file(SCHEMA_PATH, AVAILABLE_COLUMNS)
        classified = RuleClassifier(TAXONOMY_PATH, RuleVerifier(registry)).classify(slots)

        self.assertTrue(all(rule["verification"]["executable"] for rule in classified["deterministic_rules"]))
        self.assertTrue(all(not rule["verification"]["executable"] for rule in classified["candidate_rules"]))
        self.assertFalse(classified["llm_needed_parts"][0]["verification"]["field_exists"])

    def test_eval_modes_skip_deepseek_without_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = run_eval()
        self.assertEqual(result["modes"]["regex_extractor_symbolic_verifier"]["status"], "ok")
        self.assertEqual(result["modes"]["regex_extractor_symbolic_verifier"]["result_count"], 93)
        self.assertEqual(
            result["modes"]["regex_extractor_symbolic_verifier"]["task_success"]["task_success_score"],
            5,
        )
        self.assertEqual(result["modes"]["regex_extractor_symbolic_verifier"]["total_tokens"], 0)
        self.assertIsNone(result["modes"]["regex_extractor_symbolic_verifier"]["task_success_per_total_token"])
        self.assertEqual(result["modes"]["deepseek_extractor_symbolic_verifier"]["status"], "skipped")
        self.assertEqual(result["modes"]["llm_only_baseline"]["status"], "skipped")
        self.assertEqual(result["evaluation_goal"], "Compare task success under token budget, not token usage alone.")
        self.assertEqual(result["efficiency_metric"], "task_success_score / total_tokens")
        self.assertEqual(result["main_safety_metric"], "deterministic over-promotion rate")


if __name__ == "__main__":
    unittest.main()
