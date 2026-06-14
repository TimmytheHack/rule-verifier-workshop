from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.extractors.llm_slot_adapter import (
    DeepSeekSlotAdapter,
    deepseek_slot_adapter_enabled,
    llm_runtime_enabled,
)


class FakeDeepSeekExtractor:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def extract(self, text: str, **_kwargs: object) -> dict[str, object]:
        payload = dict(self.payload)
        payload.setdefault("input", text)
        return payload


class LlmSlotAdapterTest(unittest.TestCase):
    def test_adapter_validates_and_strips_rule_shaped_output(self) -> None:
        adapter = DeepSeekSlotAdapter(
            extractor=FakeDeepSeekExtractor(
                {
                    "user_context": {
                        "source_province": "广东",
                        "subject_type": "物理",
                        "reselected_subjects": [],
                        "user_rank": "12345",
                    },
                    "preferences": {
                        "major_keyword": "环境工程",
                        "major_exact_terms": ["环境工程"],
                        "preferred_cities": ["广州"],
                        "preferred_school_provinces": [],
                    },
                    "proposed_rules": [
                        {
                            "rule_id": "p_major",
                            "field_id": "major_name",
                            "operator": "contains",
                            "value": "环境工程",
                        }
                    ],
                    "unmapped_preferences": [
                        {"source_text": "宿舍好", "reason": "缺少字段。"}
                    ],
                    "deepseek_usage": {"total_tokens": 9},
                }
            )
        )

        slots = adapter.extract("广东物理，排位12345，想学环境工程。")

        self.assertEqual(slots["proposed_rules"], [])
        self.assertEqual(slots["user_context"]["user_rank"], 12345)
        self.assertEqual(slots["preferences"]["major_exact_terms"], ["环境工程"])
        self.assertEqual(slots["unmapped_preferences"][0]["source_text"], "宿舍好")
        self.assertTrue(slots["llm_slot_adapter"]["validated"])

    def test_adapter_rejects_forbidden_executable_output(self) -> None:
        adapter = DeepSeekSlotAdapter(
            extractor=FakeDeepSeekExtractor(
                {
                    "user_context": {},
                    "preferences": {},
                    "executable_rules": [{"field": "专业名称"}],
                }
            )
        )

        with self.assertRaisesRegex(ValueError, "禁止字段"):
            adapter.extract("demo")

    def test_enable_llm_env_gate_defaults_off(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "src.extractors.deepseek_extractor._dotenv_paths",
            return_value=[],
        ):
            self.assertFalse(llm_runtime_enabled())
            self.assertFalse(deepseek_slot_adapter_enabled())

    def test_enable_llm_true_and_key_enable_deepseek_adapter(self) -> None:
        with patch.dict(
            os.environ,
            {"ENABLE_LLM": "true", "DEEPSEEK_API_KEY": "test-key"},
            clear=True,
        ):
            self.assertTrue(llm_runtime_enabled())
            self.assertTrue(deepseek_slot_adapter_enabled())

if __name__ == "__main__":
    unittest.main()
