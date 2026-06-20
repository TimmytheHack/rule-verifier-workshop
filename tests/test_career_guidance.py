from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.domains import DomainConfig
from src.extractors.deepseek_extractor import normalize_slots
from src.extractors.regex_extractor import RegexExtractor
from src.reporting.career_guidance import career_guidance_for_query
from src.schema.attribute_grounder import AttributeGrounder
from src.schema.schema_registry import SchemaRegistry


ADMISSIONS_DOMAIN = DomainConfig.load("admissions")


class CareerGuidanceExtractionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = SchemaRegistry.from_domain(
            ADMISSIONS_DOMAIN,
            [
                "生源地",
                "科类",
                "专业名称",
                "城市",
                "学费",
                "专业组最低位次1",
                "选科要求",
            ],
        )

    def test_regex_extracts_family_resource_and_employment_slots(self) -> None:
        slots = RegexExtractor().extract("家里没有资源，想选一个好就业的专业。")

        self.assertEqual(slots["preferences"]["family_resource_raw"], "家里没有资源")
        self.assertEqual(slots["preferences"]["employment_preference_raw"], "好就业")
        self.assertIsNone(slots["preferences"]["career_goal_raw"])
        self.assertEqual(
            slots["raw_sources"]["preferences.family_resource_raw"],
            "家里没有资源",
        )
        self.assertEqual(
            slots["raw_sources"]["preferences.employment_preference_raw"],
            "好就业",
        )

    def test_regex_extracts_career_goal_slot_and_source(self) -> None:
        slots = RegexExtractor().extract("家里没有资源，想稳定就业。")

        self.assertEqual(slots["preferences"]["career_goal_raw"], "稳定就业")
        self.assertEqual(
            slots["raw_sources"]["preferences.career_goal_raw"],
            "稳定就业",
        )

    def test_family_resource_phrase_does_not_become_career_goal(self) -> None:
        slots = RegexExtractor().extract("家里在体制内有资源，想学法学。")

        self.assertEqual(
            slots["preferences"]["family_resource_raw"],
            "家里在体制内有资源",
        )
        self.assertIsNone(slots["preferences"]["career_goal_raw"])
        self.assertNotIn("preferences.career_goal_raw", slots["raw_sources"])

    def test_explicit_career_goal_after_family_resource_is_extracted(self) -> None:
        slots = RegexExtractor().extract("家里在体制内有资源，想考公。")

        self.assertEqual(
            slots["preferences"]["family_resource_raw"],
            "家里在体制内有资源",
        )
        self.assertEqual(slots["preferences"]["career_goal_raw"], "考公")
        self.assertEqual(
            slots["raw_sources"]["preferences.career_goal_raw"],
            "考公",
        )

    def test_regex_does_not_extract_negated_career_or_employment(self) -> None:
        for text, term in [("不想考公", "考公"), ("不考虑体制内", "体制内")]:
            slots = RegexExtractor().extract(text)

            self.assertIsNone(slots["preferences"]["career_goal_raw"])
            self.assertNotIn("preferences.career_goal_raw", slots["raw_sources"])
            self.assertNotIn(term, slots["preferences"]["other_vague_preferences"])
            self.assertNotIn("preferences.other_vague_preferences", slots["raw_sources"])

        slots = RegexExtractor().extract("不要求好就业")

        self.assertIsNone(slots["preferences"]["employment_preference_raw"])
        self.assertNotIn(
            "preferences.employment_preference_raw",
            slots["raw_sources"],
        )
        self.assertNotIn("好就业", slots["preferences"]["other_vague_preferences"])
        self.assertNotIn("preferences.other_vague_preferences", slots["raw_sources"])

    def test_regex_does_not_extract_post_term_negated_employment(self) -> None:
        cases = [
            "家里没资源，好就业不重要，只想离家近。",
            "家里没资源，好就业不看重，只想离家近。",
            "家里没资源，好就业不是重点，只想离家近。",
            "家里没资源，好就业无所谓，只想离家近。",
            "家里没资源，好就业不优先，只想离家近。",
        ]
        for text in cases:
            with self.subTest(text=text):
                slots = RegexExtractor().extract(text)

                self.assertIsNone(slots["preferences"]["employment_preference_raw"])
                self.assertNotIn(
                    "preferences.employment_preference_raw",
                    slots["raw_sources"],
                )
                self.assertNotIn(
                    "好就业",
                    slots["preferences"]["other_vague_preferences"],
                )

    def test_regex_does_not_extract_post_term_negated_career_goal(self) -> None:
        cases = [
            ("家里没资源，想稳定就业不重要，只想离家近。", "稳定就业"),
            ("家里没资源，想考公不是重点，只想离家近。", "考公"),
        ]
        for text, term in cases:
            with self.subTest(text=text):
                slots = RegexExtractor().extract(text)

                self.assertIsNone(slots["preferences"]["career_goal_raw"])
                self.assertNotIn(
                    "preferences.career_goal_raw",
                    slots["raw_sources"],
                )
                self.assertNotIn(
                    term,
                    slots["preferences"]["other_vague_preferences"],
                )

    def test_regex_ignores_unused_salary_goal_and_keeps_later_goal(self) -> None:
        slots = RegexExtractor().extract("不用考虑高薪，想稳定就业。")

        self.assertEqual(slots["preferences"]["career_goal_raw"], "稳定就业")
        self.assertNotIn("高薪", slots["preferences"]["other_vague_preferences"])
        self.assertEqual(
            slots["raw_sources"]["preferences.career_goal_raw"],
            "稳定就业",
        )

    def test_salary_preference_stays_missing_schema_vague_term(self) -> None:
        slots = RegexExtractor().extract("想高薪。")

        self.assertIsNone(slots["preferences"]["career_goal_raw"])
        self.assertEqual(slots["preferences"]["other_vague_preferences"], ["高薪"])

        grounding = AttributeGrounder(self.registry).ground(slots)
        salary_records = [
            item
            for item in grounding["attributes"]
            if item["slot_path"] == "preferences.other_vague_preferences[]"
            and item["value"] == "高薪"
        ]

        self.assertEqual(salary_records[0]["status"], "missing_schema")
        self.assertFalse(salary_records[0]["can_become_executable_rule"])

    def test_deepseek_normalize_falls_back_to_long_family_resource_alias(self) -> None:
        slots = normalize_slots(
            {
                "user_context": {},
                "preferences": {},
                "proposed_rules": [],
            },
            "家里在体制内有资源，想学法学。",
        )

        self.assertEqual(
            slots["preferences"]["family_resource_raw"],
            "家里在体制内有资源",
        )
        self.assertIsNone(slots["preferences"]["career_goal_raw"])

    def test_deepseek_normalize_revalidates_llm_career_goal_overlap(self) -> None:
        slots = normalize_slots(
            {
                "user_context": {},
                "preferences": {"career_goal_raw": "体制内"},
                "proposed_rules": [],
            },
            "家里在体制内有资源，想学法学。",
        )

        self.assertEqual(
            slots["preferences"]["family_resource_raw"],
            "家里在体制内有资源",
        )
        self.assertIsNone(slots["preferences"]["career_goal_raw"])

    def test_deepseek_employment_fallback_ignores_negated_preference(self) -> None:
        slots = normalize_slots(
            {
                "user_context": {},
                "preferences": {"employment_preference_raw": "好就业"},
                "proposed_rules": [],
            },
            "不要求好就业，只想离家近。",
        )

        self.assertIsNone(slots["preferences"]["employment_preference_raw"])

    def test_deepseek_normalize_filters_post_term_negated_employment(self) -> None:
        slots = normalize_slots(
            {
                "user_context": {},
                "preferences": {
                    "employment_preference_raw": "好就业",
                    "other_vague_preferences": ["好就业"],
                },
                "proposed_rules": [],
            },
            "家里没资源，好就业不重要，只想离家近。",
        )

        self.assertIsNone(slots["preferences"]["employment_preference_raw"])
        self.assertNotIn("好就业", slots["preferences"]["other_vague_preferences"])

    def test_deepseek_normalize_filters_post_term_negated_career_goal(self) -> None:
        slots = normalize_slots(
            {
                "user_context": {},
                "preferences": {
                    "career_goal_raw": "稳定就业",
                    "other_vague_preferences": ["稳定就业"],
                },
                "proposed_rules": [],
            },
            "家里没资源，想稳定就业不重要，只想离家近。",
        )

        self.assertIsNone(slots["preferences"]["career_goal_raw"])
        self.assertNotIn("稳定就业", slots["preferences"]["other_vague_preferences"])

    def test_deepseek_filters_negated_other_vague_preferences(self) -> None:
        slots = normalize_slots(
            {
                "user_context": {},
                "preferences": {"other_vague_preferences": ["考公"]},
                "proposed_rules": [],
            },
            "不想考公，想学环境工程。",
        )

        self.assertNotIn("考公", slots["preferences"]["other_vague_preferences"])

    def test_deepseek_ignores_unused_salary_goal_and_keeps_later_goal(self) -> None:
        slots = normalize_slots(
            {
                "user_context": {},
                "preferences": {"other_vague_preferences": ["高薪", "稳定就业"]},
                "proposed_rules": [],
            },
            "不用考虑高薪，想稳定就业。",
        )

        self.assertEqual(slots["preferences"]["career_goal_raw"], "稳定就业")
        self.assertNotIn("高薪", slots["preferences"]["other_vague_preferences"])

    def test_deepseek_family_resource_raw_matches_source_text(self) -> None:
        slots = normalize_slots(
            {
                "user_context": {},
                "preferences": {"family_resource_raw": "家里有资源"},
                "proposed_rules": [],
            },
            "家里没有资源，想学法学。",
        )

        self.assertEqual(
            slots["preferences"]["family_resource_raw"],
            "家里没有资源",
        )

    def test_family_resource_is_context_and_employment_is_no_schema(self) -> None:
        slots = RegexExtractor().extract(
            "家里在医疗系统有资源，想选好就业专业，也想稳定就业。"
        )

        grounding = AttributeGrounder(self.registry).ground(slots)
        by_path = {
            item["slot_path"]: item
            for item in grounding["attributes"]
        }

        self.assertEqual(
            by_path["preferences.family_resource_raw"]["status"],
            "context_only",
        )
        self.assertFalse(
            by_path["preferences.family_resource_raw"]["can_become_executable_rule"]
        )
        self.assertEqual(
            by_path["preferences.employment_preference_raw"]["status"],
            "missing_schema",
        )
        self.assertFalse(
            by_path["preferences.employment_preference_raw"]["can_become_executable_rule"]
        )
        self.assertEqual(
            by_path["preferences.career_goal_raw"]["status"],
            "context_only",
        )
        self.assertFalse(
            by_path["preferences.career_goal_raw"]["can_become_executable_rule"]
        )


class CareerGuidancePolicyTest(unittest.TestCase):
    def test_no_resource_good_employment_returns_information_request_only(self) -> None:
        query = "家里没资源，不知道怎么选专业，想选好就业的。"
        slots = RegexExtractor().extract(query)

        guidance = career_guidance_for_query(query, slots, ADMISSIONS_DOMAIN)

        self.assertEqual(guidance["status"], "reference_only")
        self.assertEqual(guidance["execution_effect"], "does_not_change_sql_or_results")
        self.assertIn(
            "career_no_family_resource_goal",
            [item["rule_id"] for item in guidance["matched_rules"]],
        )
        self.assertIn(
            "employment_outlook",
            [item["field_id"] for item in guidance["no_schema_field_preferences"]],
        )
        self.assertTrue(
            any(
                item["question_id"] == "q_employment_goal"
                for item in guidance["information_requests"]
            )
        )

    def test_family_resource_query_asks_for_resource_details(self) -> None:
        query = "家里在医疗系统有资源，想看以后更好就业的专业。"
        slots = RegexExtractor().extract(query)

        guidance = career_guidance_for_query(query, slots, ADMISSIONS_DOMAIN)

        question_ids = {
            item["question_id"]
            for item in guidance["information_requests"]
        }
        self.assertIn("q_family_resource_industry", question_ids)
        self.assertIn("q_family_resource_city", question_ids)
        self.assertFalse(guidance["executable"])

    def test_no_resource_negated_employment_does_not_match_guidance(self) -> None:
        query = "家里没资源，但不要求好就业，只想离家近。"
        slots = RegexExtractor().extract(query)

        guidance = career_guidance_for_query(query, slots, ADMISSIONS_DOMAIN)

        self.assertIsNone(slots["preferences"]["employment_preference_raw"])
        self.assertEqual(guidance["matched_rules"], [])
        self.assertEqual(guidance["information_requests"], [])
        self.assertEqual(guidance["no_schema_field_preferences"], [])

    def test_post_term_negated_employment_does_not_match_guidance(self) -> None:
        query = "家里没资源，好就业不重要，只想离家近。"
        slots = RegexExtractor().extract(query)

        guidance = career_guidance_for_query(query, slots, ADMISSIONS_DOMAIN)

        self.assertIsNone(slots["preferences"]["employment_preference_raw"])
        self.assertEqual(guidance["matched_rules"], [])
        self.assertEqual(guidance["information_requests"], [])
        self.assertEqual(guidance["no_schema_field_preferences"], [])

    def test_family_resource_negated_employment_does_not_match_guidance(self) -> None:
        query = (
            "家里在医疗系统有资源，但不要求好就业，只想离家近。"
        )
        slots = RegexExtractor().extract(query)

        guidance = career_guidance_for_query(query, slots, ADMISSIONS_DOMAIN)

        self.assertIsNone(slots["preferences"]["employment_preference_raw"])
        self.assertEqual(guidance["matched_rules"], [])
        self.assertEqual(guidance["information_requests"], [])
        self.assertEqual(guidance["no_schema_field_preferences"], [])

    def test_unapproved_policy_status_returns_empty_guidance(self) -> None:
        query = "家里没资源，想选好就业的。"
        slots = RegexExtractor().extract(query)

        for index, status in enumerate([None, "draft", "needs_review", "blocked"]):
            with self.subTest(status=status):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    policy_path = root / f"career_policy_{index}.json"
                    policy = {
                        "execution_effect": "does_not_change_sql_or_results",
                        "rules": [
                            {
                                "rule_id": "unapproved_rule",
                                "label": "未审核规则",
                                "trigger_slots": {
                                    "preferences.family_resource_raw": [
                                        "家里没资源"
                                    ]
                                },
                                "trigger_terms": ["好就业"],
                                "information_requests": [
                                    {
                                        "question_id": "q_unapproved",
                                        "label": "未审核问题",
                                        "question": "未审核问题",
                                        "fixed_options": [],
                                        "reason": "未审核 policy 不应生效。",
                                    }
                                ],
                                "no_schema_field_preferences": [],
                            }
                        ],
                    }
                    if status is not None:
                        policy["status"] = status
                    policy_path.write_text(
                        json.dumps(policy, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    domain = DomainConfig(
                        domain_id="admissions",
                        root=root,
                        payload={
                            "paths": {
                                "career_decision_policy": policy_path.name,
                            }
                        },
                    )

                    guidance = career_guidance_for_query(query, slots, domain)

                    self.assertEqual(guidance["matched_rules"], [])
                    self.assertEqual(guidance["information_requests"], [])
                    self.assertEqual(guidance["no_schema_field_preferences"], [])

    def test_empty_guidance_returns_fresh_lists(self) -> None:
        domain = DomainConfig(
            domain_id="admissions",
            root=Path("."),
            payload={"paths": {}},
        )
        first = career_guidance_for_query("", None, domain)

        first["matched_rules"].append({"rule_id": "mutated"})
        first["information_requests"].append({"question_id": "mutated"})
        first["no_schema_field_preferences"].append({"field_id": "mutated"})
        second = career_guidance_for_query("", None, domain)

        self.assertEqual(second["matched_rules"], [])
        self.assertEqual(second["information_requests"], [])
        self.assertEqual(second["no_schema_field_preferences"], [])


if __name__ == "__main__":
    unittest.main()
