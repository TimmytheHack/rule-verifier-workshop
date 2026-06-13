from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from src.domains import DomainConfig
from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import run_workbench_with_test_warehouse
from tests.workbench_contract_utils import (
FRONTEND_TOP_RESULT_KEYS,
    assert_workbench_contract,
)


ADMISSIONS_DOMAIN = DomainConfig.load("admissions")
GOLDEN_CASES = json.loads(
    ADMISSIONS_DOMAIN.golden_cases_path.read_text(encoding="utf-8")
)["cases"]
ADMISSIONS_TOP_TO_RAW = {
    "university_name": "院校名称",
    "group_code": "院校专业组代码",
    "major_code": "专业代码",
    "major_name": "专业名称",
    "full_major_name": "专业全称",
    "city": "城市",
    "tuition": "学费",
    "rank_2024": "专业组最低位次1",
    "major_min_rank": "最低位次1",
}


def _run_case(prompt: str, extractor: str = "regex") -> dict[str, object]:
    return run_workbench_with_test_warehouse(
        WorkbenchConfig(
            user_input=prompt,
            extractor=extractor,
            soft_preferences={"prompt": prompt},
        )
    )


def _value_at(payload: dict[str, object], dotted_path: str) -> object:
    value: object = payload
    for key in dotted_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


class WorkbenchGoldenE2ETest(unittest.TestCase):
    def test_golden_admission_consulting_cases(self) -> None:
        self.assertGreaterEqual(len(GOLDEN_CASES), 20)
        for case in GOLDEN_CASES:
            with self.subTest(case=case["case_id"]):
                result = _run_case(case["input"])

                assert_workbench_contract(self, result)
                self.assertEqual(result["status"], case.get("status", "ok"))
                self.assertEqual(result["result_count"], case["result_count"])
                self.assertEqual(
                    result["execution"]["hard_rule_ids"],
                    case["hard_rule_ids"],
                )
                self.assertEqual(
                    [rule["rule_id"] for rule in result["evidence_pack"]["executed_rules"]],
                    case["hard_rule_ids"],
                )
                self.assertEqual(
                    result["evidence_pack"]["trace_summary"]["executed_rule_ids"],
                    case["hard_rule_ids"],
                )
                self.assertEqual(
                    result["evidence_pack"]["trace_summary"]["traced_result_count"],
                    case["result_count"],
                )

                for path, expected in case["slots"].items():
                    self.assertEqual(
                        _value_at(result["extracted_slots"], path),
                        expected,
                        path,
                    )

                if case["top"] is None:
                    self.assertEqual(result["items"], [])
                    self.assertEqual(result["top_results"], [])
                    self.assertEqual(result["evidence_pack"]["top_k_results"], [])
                else:
                    item = result["items"][0]
                    self.assertTrue(item["matched_filters"])
                    for key, expected in case["top"].items():
                        raw_key = ADMISSIONS_TOP_TO_RAW.get(key)
                        if raw_key:
                            self.assertEqual(item["raw"].get(raw_key), expected, key)
                    evidence_top = result["evidence_pack"]["top_k_results"][0]
                    self.assertEqual(
                        evidence_top["院校名称"],
                        case["top"]["university_name"],
                    )
                    self.assertTrue(evidence_top["trace"])

                answer_text = result["natural_language_report"]["full_text"]
                self.assertIn("字段值审计解释：", answer_text)
                self.assertIn("已执行规则：", answer_text)
                for expected_text in case["answer_contains"]:
                    self.assertIn(expected_text, answer_text)
                for absent in case.get("params_absent", []):
                    self.assertNotIn(absent, result["execution"]["params"])

    def test_top_results_keep_frontend_english_keys(self) -> None:
        result = _run_case("广东物理，排位32000，想学计算机，广深优先。")
        top_result = result["top_results"][0]

        self.assertTrue(FRONTEND_TOP_RESULT_KEYS <= set(top_result))
        self.assertIn("university_name", top_result)
        self.assertIn("group_code", top_result)
        self.assertIn("major_name", top_result)
        self.assertNotIn("院校名称", top_result)

    def test_pearl_river_delta_does_not_enter_hard_filter(self) -> None:
        result = _run_case("广东物理，排名3.2万，计算机相关，珠三角优先，不要校企合作。")

        self.assertEqual(
            result["execution"]["hard_rule_ids"],
            ["e_source_province", "e_subject_type", "e_major_keyword"],
        )
        self.assertNotIn("e_city", result["execution"]["hard_rule_ids"])
        self.assertNotIn("珠三角", result["execution"]["params"])
        self.assertIn(
            "[需确认] 珠三角 -> 城市：partial_match",
            result["natural_language_report"]["full_text"],
        )

    def test_hybrid_without_deepseek_key_uses_deterministic_only(self) -> None:
        with patch("src.api.workbench.has_deepseek_api_key", return_value=False):
            with patch("src.api.workbench.DeepSeekExtractor") as extractor_class:
                result = _run_case(
                    "广东物理，物化生，排位32000，想学计科，广深优先。",
                    extractor="hybrid",
                )

        extractor_class.assert_not_called()
        self.assertEqual(result["token_usage"]["extractor"], None)
        self.assertFalse(result["extracted_slots"]["fallback_extraction"]["used"])
        self.assertEqual(
            result["execution"]["hard_rule_ids"],
            [
                "e_source_province",
                "e_subject_type",
                "e_subject_requirement",
                "e_city",
            ],
        )
        self.assertEqual(result["result_count"], 3962)


if __name__ == "__main__":
    unittest.main()
