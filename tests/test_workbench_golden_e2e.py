from __future__ import annotations

import unittest
from unittest.mock import patch

from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import run_workbench_with_test_warehouse
from tests.workbench_contract_utils import (
    FRONTEND_TOP_RESULT_KEYS,
    assert_workbench_contract,
)


GOLDEN_CASES = [
    {
        "case_id": "g01_computer_guangshen",
        "input": "广东物理，排位32000，想学计算机，广深优先。",
        "slots": {
            "user_context.source_province": "广东",
            "user_context.subject_type": "物理",
            "user_context.user_rank": 32000,
            "preferences.major_exact_terms": ["计算机"],
            "preferences.preferred_cities": ["广州", "深圳"],
        },
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 149,
        "top": {
            "university_name": "中山大学",
            "group_code": "10558219",
            "major_name": "计算机类",
            "city": "广州",
            "group_min_rank": 4019,
        },
        "answer_contains": ["[已执行] 广深 -> 城市：exact_match"],
    },
    {
        "case_id": "g02_jike_subject_bundle",
        "input": "广东物理，物化生，排位32000，想学计科，广深优先。",
        "status": "needs_confirmation",
        "slots": {
            "user_context.reselected_subjects": ["化学", "生物"],
            "preferences.major_exact_terms": [],
            "preferences.major_expansion_raw": "计科",
            "preferences.preferred_cities": ["广州", "深圳"],
        },
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_subject_requirement",
            "e_city",
        ],
        "result_count": 3962,
        "top": {
            "university_name": "香港中文大学(深圳)",
            "group_code": "16407101",
            "major_name": "理科试验班",
            "city": "深圳",
            "group_min_rank": 968,
        },
        "answer_contains": [
            "[已执行] 物化生 -> 选科要求：exact_match",
            "[需确认] 计科 -> 专业名称：partial_match",
        ],
    },
    {
        "case_id": "g03_history_law_guangzhou",
        "input": "广东历史，排位25000，想学法学，广州优先。",
        "slots": {
            "user_context.subject_type": "历史",
            "preferences.major_exact_terms": ["法学"],
            "preferences.preferred_cities": ["广州"],
        },
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 29,
        "top": {
            "university_name": "中山大学",
            "group_code": "10558216",
            "major_name": "法学",
            "city": "广州",
            "group_min_rank": 1439,
        },
        "answer_contains": ["[已执行] 法学 -> 专业名称：exact_match"],
    },
    {
        "case_id": "g04_software_shenzhen_tuition",
        "input": "广东物理，排位40000，想学软件工程，深圳，学费2w以内。",
        "slots": {
            "preferences.major_exact_terms": ["软件工程"],
            "preferences.preferred_cities": ["深圳"],
            "preferences.tuition_cap_yuan": 20000,
        },
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
            "e_tuition_cap_explicit",
        ],
        "result_count": 1,
        "top": {
            "university_name": "深圳职业技术大学",
            "group_code": "11113202",
            "major_name": "软件工程技术",
            "city": "深圳",
            "group_min_rank": 54061,
        },
        "answer_contains": ["[已执行] 20000 -> 学费：exact_match"],
    },
    {
        "case_id": "g05_ai_guangzhou",
        "input": "广东物理，排位50000，想学人工智能，广州。",
        "slots": {"preferences.major_exact_terms": ["人工智能"]},
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 53,
        "top": {
            "university_name": "香港科技大学(广州)",
            "group_code": "16412101",
            "major_name": "人工智能",
            "city": "广州",
            "group_min_rank": 1424,
        },
        "answer_contains": ["[已执行] 人工智能 -> 专业名称：exact_match"],
    },
    {
        "case_id": "g06_electronic_info_foshan",
        "input": "广东物理，排位60000，想学电子信息，佛山。",
        "slots": {"preferences.major_exact_terms": ["电子信息"]},
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 3,
        "top": {
            "university_name": "佛山大学",
            "group_code": "11847201",
            "major_name": "电子信息工程",
            "city": "佛山",
            "group_min_rank": 68019,
        },
        "answer_contains": ["[已执行] 电子 -> 专业名称：exact_match"],
    },
    {
        "case_id": "g07_automation_dongguan",
        "input": "广东物理，排位80000，想学自动化，东莞。",
        "slots": {
            "user_context.reselected_subjects": [],
            "preferences.major_exact_terms": ["自动化"],
        },
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 17,
        "top": {
            "university_name": "东莞理工学院",
            "group_code": "11819202",
            "major_name": "电气工程及其自动化",
            "city": "东莞",
            "group_min_rank": 92989,
        },
        "answer_contains": ["[已执行] 自动化 -> 专业名称：exact_match"],
    },
    {
        "case_id": "g08_chinese_literature",
        "input": "广东历史，排位30000，想学汉语言文学，广州。",
        "slots": {"preferences.major_exact_terms": ["汉语言文学"]},
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 30,
        "top": {
            "university_name": "中山大学",
            "group_code": "10558201",
            "major_name": "汉语言文学",
            "city": "广州",
            "group_min_rank": 1203,
        },
        "answer_contains": ["[已执行] 汉语言文学 -> 专业名称：exact_match"],
    },
    {
        "case_id": "g09_network_security_empty",
        "input": "广东物理，排位90000，想学网络安全，深圳。",
        "status": "no_results",
        "slots": {"preferences.major_exact_terms": ["网络安全"]},
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 0,
        "top": None,
        "answer_contains": ["共筛选到 0 条符合已执行规则的结果。"],
    },
    {
        "case_id": "g10_data_science_guangzhou_shenzhen",
        "input": "广东物理，排位45000，想学数据科学，广州深圳。",
        "slots": {"preferences.major_exact_terms": ["数据科学"]},
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 32,
        "top": {
            "university_name": "广东工业大学",
            "group_code": "11845207",
            "major_name": "数据科学与大数据技术",
            "city": "广州",
            "group_min_rank": 34297,
        },
        "answer_contains": ["[已执行] 数据科学 -> 专业名称：exact_match"],
    },
    {
        "case_id": "g11_accounting_history",
        "input": "广东历史，排位35000，想学会计，广州。",
        "slots": {"preferences.major_exact_terms": ["会计"]},
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 102,
        "top": {
            "university_name": "暨南大学",
            "group_code": "10559201",
            "major_name": "会计学",
            "city": "广州",
            "group_min_rank": 5912,
        },
        "answer_contains": ["[已执行] 会计 -> 专业名称：exact_match"],
    },
    {
        "case_id": "g12_clinical_guangzhou",
        "input": "广东物理，排位70000，想学临床医学，广州。",
        "slots": {"preferences.major_exact_terms": ["临床医学"]},
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 26,
        "top": {
            "university_name": "南方医科大学",
            "group_code": "12121206",
            "major_name": "临床医学",
            "city": "广州",
            "group_min_rank": 2977,
        },
        "answer_contains": ["[已执行] 临床医学 -> 专业名称：exact_match"],
    },
    {
        "case_id": "g13_related_major_prd_cooperation",
        "input": "广东物理，排名3.2万，计算机相关，珠三角优先，不要校企合作。",
        "status": "needs_confirmation",
        "slots": {
            "user_context.user_rank": 32000,
            "preferences.major_exact_terms": ["计算机"],
            "preferences.major_expansion_raw": "计算机相关",
            "preferences.other_vague_preferences": ["珠三角"],
            "preferences.cooperation_preference_raw": "不要校企合作",
        },
        "hard_rule_ids": ["e_source_province", "e_subject_type", "e_major_keyword"],
        "result_count": 749,
        "top": {
            "university_name": "北京大学",
            "group_code": "10001203",
            "major_name": "计算机类",
            "city": "海淀区",
            "group_min_rank": 85,
        },
        "answer_contains": [
            "[需确认] 计算机相关 -> 专业名称：partial_match",
            "[需确认] 珠三角 -> 城市：partial_match",
            "[未执行] 不要校企合作 -> 合作办学类型字段：no_schema_field",
        ],
        "params_absent": ["计算机相关", "珠三角", "不要校企合作"],
    },
    {
        "case_id": "g14_zhongwai_cooperation",
        "input": "广东物理，排位32000，想学计算机，不要中外合作。",
        "slots": {"preferences.cooperation_preference_raw": "不要中外合作"},
        "hard_rule_ids": ["e_source_province", "e_subject_type", "e_major_keyword"],
        "result_count": 749,
        "top": {
            "university_name": "北京大学",
            "group_code": "10001203",
            "major_name": "计算机类",
            "city": "海淀区",
            "group_min_rank": 85,
        },
        "answer_contains": [
            "[未执行] 不要中外合作 -> 合作办学类型字段：no_schema_field"
        ],
        "params_absent": ["不要中外合作", "中外合作"],
    },
    {
        "case_id": "g15_stay_guangdong_recommend",
        "input": "排位10000名，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐。",
        "status": "needs_confirmation",
        "slots": {
            "user_context.source_province": None,
            "preferences.major_exact_terms": ["人工智能", "计算机"],
            "preferences.preferred_school_provinces": ["广东"],
            "preferences.overseas_preference_raw": "不想去国外",
            "preferences.recommendation_request_raw": "给出推荐",
        },
        "hard_rule_ids": ["e_major_keyword", "e_school_province"],
        "result_count": 436,
        "top": {
            "university_name": "香港科技大学(广州)",
            "group_code": "16412101",
            "major_name": "人工智能",
            "city": "广州",
            "group_min_rank": 1424,
        },
        "answer_contains": [
            "[未执行] 不想去国外 -> 国家或境外办学字段：no_schema_field",
            "[需确认] 给出推荐 -> 专业组最低位次1：partial_match",
        ],
    },
    {
        "case_id": "g16_finance_shenzhen",
        "input": "广东历史，排位50000，想学金融，深圳。",
        "slots": {"preferences.major_exact_terms": ["金融"]},
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 9,
        "top": {
            "university_name": "深圳大学",
            "group_code": "10590202",
            "major_name": "金融学类",
            "city": "深圳",
            "group_min_rank": 7247,
        },
        "answer_contains": ["[已执行] 金融 -> 专业名称：exact_match"],
    },
    {
        "case_id": "g17_cyberspace_guangshen",
        "input": "广东物理，排位55000，想学网络空间安全，广州深圳。",
        "slots": {"preferences.major_exact_terms": ["网络空间安全"]},
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 8,
        "top": {
            "university_name": "中山大学",
            "group_code": "10558219",
            "major_name": "网络空间安全",
            "city": "广州",
            "group_min_rank": 4019,
        },
        "answer_contains": ["[已执行] 网络空间安全 -> 专业名称：exact_match"],
    },
    {
        "case_id": "g18_electronic_info_zhuhai",
        "input": "广东物理，排位75000，想学电子信息，珠海。",
        "slots": {"preferences.preferred_cities": ["珠海"]},
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 3,
        "top": {
            "university_name": "珠海科技学院",
            "group_code": "13684209",
            "major_name": "电子信息科学与技术",
            "city": "珠海",
            "group_min_rank": 161791,
        },
        "answer_contains": ["[已执行] 珠海 -> 城市：exact_match"],
    },
    {
        "case_id": "g19_journalism_history",
        "input": "广东历史，排位42000，想学新闻传播，广州。",
        "slots": {"preferences.major_exact_terms": ["新闻传播"]},
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 3,
        "top": {
            "university_name": "中山大学",
            "group_code": "10558216",
            "major_name": "新闻传播学类",
            "city": "广州",
            "group_min_rank": 1439,
        },
        "answer_contains": ["[已执行] 新闻传播 -> 专业名称：exact_match"],
    },
    {
        "case_id": "g20_wuhuadi_automation",
        "input": "广东物理，物化地，排位65000，想学自动化，广深。",
        "slots": {
            "user_context.reselected_subjects": ["化学", "地理"],
            "preferences.major_exact_terms": ["自动化"],
            "preferences.preferred_cities": ["广州", "深圳"],
        },
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_subject_requirement",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 93,
        "top": {
            "university_name": "华南理工大学",
            "group_code": "10561203",
            "major_name": "自动化",
            "city": "广州",
            "group_min_rank": 12608,
        },
        "answer_contains": [
            "[已执行] 物化地 -> 选科要求：exact_match",
            "[已执行] 广深 -> 城市：exact_match",
        ],
    },
    {
        "case_id": "g21_low_tuition_needs_confirmation",
        "input": "广东物理，排位32000，想学临床医学，深圳，学费1000以内。",
        "status": "needs_confirmation",
        "slots": {
            "preferences.major_exact_terms": ["临床医学"],
            "preferences.tuition_cap_yuan": 1000,
        },
        "hard_rule_ids": [
            "e_source_province",
            "e_subject_type",
            "e_major_keyword",
            "e_city",
        ],
        "result_count": 3,
        "top": {
            "university_name": "深圳大学",
            "group_code": "10590242",
            "major_name": "临床医学",
            "city": "深圳",
            "group_min_rank": 28089,
        },
        "answer_contains": ["[需确认] 1000 -> 学费：partial_match"],
        "params_absent": [1000.0, 1000],
    },
]


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
                    self.assertEqual(result["top_results"], [])
                    self.assertEqual(result["evidence_pack"]["top_k_results"], [])
                else:
                    top_result = result["top_results"][0]
                    self.assertTrue(FRONTEND_TOP_RESULT_KEYS <= set(top_result))
                    self.assertNotIn("院校名称", top_result)
                    for key, expected in case["top"].items():
                        self.assertEqual(top_result[key], expected, key)
                    self.assertTrue(top_result["trace"])
                    self.assertTrue(
                        any(item["status"] == "pass" for item in top_result["trace"])
                    )
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
