from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import urllib.error
from unittest.mock import patch

from scripts.eval_modes import run_eval
from src.baselines.llm_only_baseline import SchemaAwareLLMOnlyBaseline
from src.domains import DomainConfig
from src.extractors.deepseek_extractor import (
    DeepSeekClient,
    DeepSeekExtractor,
    DeepSeekJSONResponse,
    deepseek_usage_from_payload,
    normalize_slots,
)
from src.rules.rule_classifier import RuleClassifier
from src.rules.rule_verifier import RuleVerifier
from src.schema.schema_registry import SchemaRegistry


ADMISSIONS_DOMAIN = DomainConfig.load("admissions")
SCHEMA_PATH = ADMISSIONS_DOMAIN.schema_path
TAXONOMY_PATH = ADMISSIONS_DOMAIN.rule_taxonomy_path
AVAILABLE_COLUMNS = ADMISSIONS_DOMAIN.required_columns


class FakeDeepSeekClient:
    def __init__(self) -> None:
        self.last_system_prompt = ""
        self.last_user_prompt = ""

    def chat_json(self, system_prompt: str, user_prompt: str) -> DeepSeekJSONResponse:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
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
                "proposed_rules": [
                    {
                        "rule_id": "p_major",
                        "source_text": "想学计算机",
                        "category": "deterministic",
                        "field_id": "major_name",
                        "field": "专业名称",
                        "operator": "contains",
                        "value": "计算机",
                        "semantic_type": "explicit_user_fact",
                        "value_source": "explicit_user_fact",
                        "requires_human_confirmation": False,
                        "reason": "用户明确给出专业关键词。",
                    }
                ],
                "unmapped_preferences": [
                    {
                        "source_text": "中外合作",
                        "field_id": "cooperation_type",
                        "reason": "字段未激活。",
                    }
                ],
                "questions_needed": [
                    {
                        "source_text": "稳一点",
                        "question": "请选择位次窗口。",
                        "reason": "风险偏好需要边界。",
                    }
                ],
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


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class DeepSeekEvalModesTest(unittest.TestCase):
    def test_deepseek_extractor_output_still_goes_through_symbolic_verifier(self) -> None:
        fake_client = FakeDeepSeekClient()
        slots = DeepSeekExtractor(client=fake_client).extract(
            "demo",
            schema_context=[{"field_id": "major_name", "source_column": "专业名称"}],
            hard_context={"source_province": "广东"},
            boundary_context={"safety_margin_percent": 10},
        )
        self.assertEqual(slots["deepseek_usage"]["total_tokens"], 33)
        self.assertIn("source_spans", slots)
        self.assertIn("major_name", fake_client.last_user_prompt)
        self.assertIn("结构化硬信息", fake_client.last_user_prompt)
        self.assertIn("所有自然语言解释必须写中文", fake_client.last_user_prompt)
        self.assertEqual(slots["user_context"]["subject_type"], "物理")
        self.assertEqual(slots["preferences"]["major_exact_terms"], ["计算机"])
        self.assertEqual(slots["preferences"]["preferred_cities"], ["广州", "深圳"])
        self.assertEqual(slots["proposed_rules"][0]["field_id"], "major_name")
        self.assertEqual(slots["unmapped_preferences"][0]["source_text"], "中外合作")

        registry = SchemaRegistry.from_file(SCHEMA_PATH, AVAILABLE_COLUMNS)
        verifier = RuleVerifier(registry, domain_config=ADMISSIONS_DOMAIN)
        classified = RuleClassifier(
            TAXONOMY_PATH,
            verifier,
            domain_config=ADMISSIONS_DOMAIN,
        ).classify(slots)
        audited = verifier.audit_proposed_rules(slots["proposed_rules"])

        self.assertTrue(all(rule["verification"]["executable"] for rule in classified["deterministic_rules"]))
        self.assertTrue(all(not rule["verification"]["executable"] for rule in classified["candidate_rules"]))
        self.assertFalse(classified["llm_needed_parts"][0]["verification"]["field_exists"])
        self.assertTrue(audited[0]["verification"]["executable"])

    def test_eval_modes_skip_deepseek_without_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "scripts.eval_modes.has_deepseek_api_key",
            return_value=False,
        ):
            result = run_eval()
        self.assertEqual(result["modes"]["regex_extractor_symbolic_verifier"]["status"], "ok")
        self.assertEqual(result["modes"]["regex_extractor_symbolic_verifier"]["result_count"], 2)
        self.assertEqual(
            result["modes"]["regex_extractor_symbolic_verifier"]["task_success"]["task_success_score"],
            5,
        )
        self.assertEqual(result["modes"]["regex_extractor_symbolic_verifier"]["total_tokens"], 0)
        self.assertIsNone(result["modes"]["regex_extractor_symbolic_verifier"]["task_success_per_total_token"])
        self.assertEqual(result["modes"]["deepseek_extractor_symbolic_verifier"]["status"], "skipped")
        self.assertEqual(result["modes"]["llm_only_baseline"]["status"], "skipped")
        self.assertEqual(result["modes"]["schema_aware_llm_only_baseline"]["status"], "skipped")
        self.assertEqual(
            result["evaluation_goal"],
            "比较不同方法在 token 预算下的任务成功率，而不是只看 token 用量。",
        )
        self.assertEqual(result["efficiency_metric"], "任务成功分 / 总 token 数")
        self.assertEqual(result["main_safety_metric"], "确定性规则过度提升率")

    def test_deepseek_client_reads_dotenv_without_exposing_secret(self) -> None:
        with TemporaryDirectory() as directory:
            dotenv_path = Path(directory) / ".env"
            dotenv_path.write_text(
                'DEEPSEEK_API_KEY="test-key"\n'
                "DEEPSEEK_MODEL=custom-model\n"
                "DEEPSEEK_API_URL=https://example.test/chat/completions\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True), patch(
                "src.extractors.deepseek_extractor._dotenv_paths",
                return_value=[dotenv_path],
            ):
                client = DeepSeekClient()

        self.assertEqual(client.api_key, "test-key")
        self.assertEqual(client.model, "custom-model")
        self.assertEqual(client.api_url, "https://example.test/chat/completions")

    def test_deepseek_client_retries_transient_network_errors(self) -> None:
        calls = {"count": 0}
        api_payload = {
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }

        def fake_urlopen(_request: object, timeout: int) -> FakeHTTPResponse:
            self.assertEqual(timeout, 60)
            calls["count"] += 1
            if calls["count"] == 1:
                raise urllib.error.URLError(BrokenPipeError(32, "Broken pipe"))
            return FakeHTTPResponse(api_payload)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), patch("time.sleep"):
            client = DeepSeekClient(
                api_key="test-key",
                max_retries=1,
                retry_backoff_seconds=0,
            )
            response = client.chat_json("system", "user")

        self.assertEqual(calls["count"], 2)
        self.assertEqual(response.payload, {"ok": True})
        self.assertEqual(response.usage["total_tokens"], 3)

    def test_deepseek_usage_preserves_cache_and_reasoning_tokens(self) -> None:
        usage = deepseek_usage_from_payload(
            {
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                    "prompt_cache_hit_tokens": 4,
                    "prompt_cache_miss_tokens": 6,
                    "completion_tokens_details": {"reasoning_tokens": 7},
                }
            }
        )

        self.assertEqual(usage["prompt_tokens"], 10)
        self.assertEqual(usage["completion_tokens"], 20)
        self.assertEqual(usage["total_tokens"], 30)
        self.assertEqual(usage["prompt_cache_hit_tokens"], 4)
        self.assertEqual(usage["prompt_cache_miss_tokens"], 6)
        self.assertEqual(usage["reasoning_tokens"], 7)

    def test_schema_aware_baseline_receives_schema_but_still_has_no_verifier(self) -> None:
        fake_client = FakeDeepSeekClient()
        schema_fields = SchemaRegistry.from_file(SCHEMA_PATH, AVAILABLE_COLUMNS).configured_fields
        payload = SchemaAwareLLMOnlyBaseline(schema_fields, client=fake_client).propose("广东物理，排位32000，不要中外合作。")
        self.assertEqual(payload["deepseek_usage"]["total_tokens"], 33)
        self.assertIn("cooperation_type", fake_client.last_user_prompt)
        self.assertIn("没有符号验证器", fake_client.last_system_prompt)

    def test_deepseek_normalization_preserves_multi_city_and_ownership_slots(self) -> None:
        text = "我是广东物理类，排位40000，想看深圳、广州、佛山的学校，学费两万以内，优先公办。"
        slots = normalize_slots(
            {
                "user_context": {
                    "source_province": "广东",
                    "subject_type": "物理类",
                    "user_rank": "40000",
                },
                "preferences": {
                    "major_keyword": None,
                    "major_exact_terms": [],
                    "preferred_cities": ["深圳、广州、佛山"],
                    "risk_preference_raw": None,
                    "tuition_preference_raw": "两万以内",
                    "major_expansion_raw": None,
                    "cooperation_preference_raw": "优先公办",
                    "school_ownership_preference_raw": None,
                },
            },
            text,
        )

        self.assertEqual(slots["user_context"]["subject_type"], "物理")
        self.assertEqual(slots["user_context"]["user_rank"], 40000)
        self.assertEqual(slots["preferences"]["preferred_cities"], ["广州", "深圳", "佛山"])
        self.assertEqual(slots["preferences"]["tuition_cap_yuan"], 20000)
        self.assertIsNone(slots["preferences"]["tuition_preference_raw"])
        self.assertIsNone(slots["preferences"]["cooperation_preference_raw"])
        self.assertEqual(slots["preferences"]["school_ownership_preference_raw"], "优先公办")

    def test_deepseek_normalization_keeps_explicit_non_alias_major_terms(self) -> None:
        slots = normalize_slots(
            {
                "user_context": {},
                "preferences": {
                    "major_keyword": "环境工程",
                    "major_exact_terms": ["环境工程"],
                },
                "proposed_rules": [],
            },
            "广东物理类，排位12345，想学环境工程，广州。",
        )

        self.assertEqual(slots["preferences"]["major_exact_terms"], ["环境工程"])
        self.assertEqual(slots["preferences"]["major_keyword"], "环境工程")

    def test_deepseek_normalization_drops_non_alias_major_not_in_user_text(self) -> None:
        slots = normalize_slots(
            {
                "user_context": {},
                "preferences": {
                    "major_keyword": "环境工程",
                    "major_exact_terms": ["环境工程"],
                },
                "proposed_rules": [],
            },
            "广东物理类，排位12345，广州。",
        )

        self.assertEqual(slots["preferences"]["major_exact_terms"], [])
        self.assertIsNone(slots["preferences"]["major_keyword"])


if __name__ == "__main__":
    unittest.main()
