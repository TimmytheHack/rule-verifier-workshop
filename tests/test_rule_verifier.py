from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from src.extractors.regex_extractor import RegexExtractor
from src.api.workbench import (
    WorkbenchConfig,
    _apply_soft_confirmations,
    _append_grounding_non_executable_preferences,
    _extract_slots,
    _merge_verified_proposed_rules,
    _slots_from_inputs,
)
from src.executors.pandas_executor import PandasExecutor
from src.rules.rule_classifier import RuleClassifier
from src.rules.rule_promoter import RulePromoter
from src.rules.rule_verifier import RuleVerifier
from src.schema.attribute_grounder import AttributeGrounder
from src.schema.schema_registry import SchemaRegistry
from src.tracing.trace_generator import TraceGenerator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/schema_registry.json"
TAXONOMY_PATH = ROOT / "rules/rule_taxonomy.json"
VAGUE_TERMS_PATH = ROOT / "rules/vague_terms.json"
INFORMATION_REQUIREMENTS_PATH = ROOT / "rules/information_requirements.json"
DEMO_INPUT = "我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。"
AVAILABLE_COLUMNS = ["生源地", "科类", "选科要求", "专业名称", "城市", "专业组最低位次1", "学费"]


class RuleVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = SchemaRegistry.from_file(SCHEMA_PATH, AVAILABLE_COLUMNS)
        self.verifier = RuleVerifier(self.registry)
        self.slots = RegexExtractor().extract(DEMO_INPUT)
        self.classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(self.slots)

    def test_deterministic_rules_are_executable_when_schema_grounded(self) -> None:
        rules = {rule["rule_id"]: rule for rule in self.classified["deterministic_rules"]}
        self.assertTrue(rules["d_source_province"]["verification"]["executable"])
        self.assertTrue(rules["d_subject_type"]["verification"]["executable"])
        self.assertTrue(rules["d_major_keyword"]["verification"]["executable"])
        self.assertTrue(rules["d_city"]["verification"]["executable"])
        self.assertEqual(rules["d_city"]["verification"]["execution_level"], "executable")
        self.assertEqual(rules["d_city"]["verification"]["ambiguity_level"], "none")
        self.assertTrue(rules["d_city"]["verification"]["schema_grounded"])

    def test_candidate_rules_do_not_execute_before_confirmation(self) -> None:
        for rule in self.classified["candidate_rules"]:
            self.assertTrue(rule["requires_human_confirmation"])
            self.assertTrue(rule["verification"]["ambiguity_detected"])
            self.assertEqual(rule["verification"]["ambiguity_level"], "medium")
            self.assertFalse(rule["verification"]["executable"])

    def test_missing_cooperation_type_is_not_schema_grounded(self) -> None:
        self.assertFalse(self.registry.has_field("cooperation_type"))
        llm_part = self.classified["llm_needed_parts"][0]
        self.assertEqual(llm_part["field_id"], "cooperation_type")
        self.assertFalse(llm_part["verification"]["field_exists"])
        self.assertFalse(llm_part["verification"]["executable"])

    def test_candidate_rules_are_not_promoted_without_simulated_confirmation(self) -> None:
        final_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=False,
        ).final_executable_rules(self.classified)
        rule_ids = {rule["rule_id"] for rule in final_rules}
        self.assertEqual(rule_ids, {"e_source_province", "e_subject_type", "e_major_keyword", "e_city"})
        self.assertNotIn("e_safety_margin", rule_ids)
        self.assertNotIn("e_tuition_cap", rule_ids)

    def test_simulated_confirmation_explicitly_promotes_expected_candidate_rules(self) -> None:
        final_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=True,
        ).final_executable_rules(self.classified)
        rule_ids = {rule["rule_id"] for rule in final_rules}
        self.assertIn("e_safety_margin", rule_ids)
        self.assertIn("e_tuition_cap", rule_ids)
        self.assertNotIn("cooperation_type", {rule["field"] for rule in final_rules})

    def test_unmentioned_preferences_are_not_carried_into_pipeline(self) -> None:
        slots = RegexExtractor().extract("广东历史，排位25000，法学，预算有限。")
        classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(slots)
        final_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=True,
        ).final_executable_rules(classified)

        self.assertEqual(
            {rule["rule_id"] for rule in classified["candidate_rules"]},
            {"c_tuition_cap"},
        )
        self.assertEqual(classified["llm_needed_parts"], [])
        self.assertEqual(classified["non_executable_preferences"], [])
        self.assertEqual(
            {question["question_id"] for question in classified["confirmation_questions"]},
            {"q_tuition_cap"},
        )
        self.assertNotIn("e_safety_margin", {rule["rule_id"] for rule in final_rules})
        self.assertIn("e_tuition_cap", {rule["rule_id"] for rule in final_rules})

    def test_safety_margin_confirmation_uses_current_user_rank(self) -> None:
        slots = RegexExtractor().extract("广东物理，排位25000，想学计算机，稳一点。")
        classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(slots)
        final_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=True,
        ).final_executable_rules(classified)

        safety_rule = next(rule for rule in final_rules if rule["rule_id"] == "e_safety_margin")
        self.assertEqual(safety_rule["operator"], "between")
        self.assertEqual(safety_rule["value"], [22500, 27500])

    def test_math_major_prompt_extracts_major_without_crashing(self) -> None:
        slots = RegexExtractor().extract("我今年高考排位22944，我想报广东数学系")
        classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(slots)
        final_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=True,
        ).final_executable_rules(classified)

        self.assertEqual(slots["preferences"]["major_keyword"], "数学")
        self.assertIn("e_major_keyword", {rule["rule_id"] for rule in final_rules})
        self.assertNotIn("e_subject_type", {rule["rule_id"] for rule in final_rules})

    def test_recommendation_query_uses_school_province_major_or_and_rank_floor(self) -> None:
        query = "排位10000名，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐"
        registry = SchemaRegistry.from_file(
            SCHEMA_PATH,
            AVAILABLE_COLUMNS + ["所在省"],
        )
        verifier = RuleVerifier(registry)
        slots = RegexExtractor().extract(query)

        self.assertIsNone(slots["user_context"]["source_province"])
        self.assertEqual(slots["user_context"]["user_rank"], 10000)
        self.assertEqual(slots["preferences"]["major_exact_terms"], ["人工智能", "计算机"])
        self.assertEqual(slots["preferences"]["preferred_school_provinces"], ["广东"])
        self.assertEqual(slots["preferences"]["overseas_preference_raw"], "不想去国外")
        self.assertEqual(slots["preferences"]["recommendation_request_raw"], "给出推荐")

        classified = RuleClassifier(TAXONOMY_PATH, verifier).classify(slots)
        grounding = AttributeGrounder(registry).ground(slots)
        classified = _append_grounding_non_executable_preferences(classified, grounding)
        final_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=True,
        ).final_executable_rules(classified)
        final_by_id = {rule["rule_id"]: rule for rule in final_rules}

        self.assertEqual(final_by_id["e_major_keyword"]["operator"], "contains_any")
        self.assertEqual(final_by_id["e_major_keyword"]["value"], ["人工智能", "计算机"])
        self.assertEqual(final_by_id["e_school_province"]["field"], "所在省")
        self.assertEqual(final_by_id["e_school_province"]["value"], ["广东"])
        self.assertEqual(final_by_id["e_recommendation_rank_floor"]["value"], 10000)
        self.assertIn(
            "不想去国外",
            {item["source_text"] for item in classified["non_executable_preferences"]},
        )

        dataframe = pd.DataFrame(
            [
                {
                    "ID": 1,
                    "所在省": "广东",
                    "专业名称": "人工智能",
                    "专业组最低位次1": 12064,
                    "学费": 6853,
                },
                {
                    "ID": 2,
                    "所在省": "广东",
                    "专业名称": "计算机类",
                    "专业组最低位次1": 12232,
                    "学费": 6853,
                },
                {
                    "ID": 3,
                    "所在省": "广东",
                    "专业名称": "人工智能",
                    "专业组最低位次1": 9000,
                    "学费": 6853,
                },
                {
                    "ID": 4,
                    "所在省": "湖南",
                    "专业名称": "计算机科学与技术",
                    "专业组最低位次1": 20000,
                    "学费": 6500,
                },
            ]
        )

        results = PandasExecutor().execute(dataframe, final_rules, user_rank=10000)

        self.assertEqual([row["ID"] for row in results], [1, 2])

    def test_recommendation_query_does_not_apply_unselected_boundaries(self) -> None:
        query = "排位10000名，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐"
        registry = SchemaRegistry.from_file(
            SCHEMA_PATH,
            AVAILABLE_COLUMNS + ["所在省"],
        )
        verifier = RuleVerifier(registry)
        config = WorkbenchConfig(user_input=query, soft_preferences={"prompt": query})
        slots = _slots_from_inputs(RegexExtractor().extract(query), config)
        classified = RuleClassifier(TAXONOMY_PATH, verifier).classify(slots)
        classified = _apply_soft_confirmations(classified, config, slots)
        final_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=True,
        ).final_executable_rules(classified)
        final_by_id = {rule["rule_id"]: rule for rule in final_rules}

        self.assertIn("e_recommendation_rank_floor", final_by_id)
        self.assertNotIn("e_safety_margin", final_by_id)
        self.assertNotIn("e_tuition_cap", final_by_id)

    def test_vague_terms_are_configured_to_block_over_promotion(self) -> None:
        vague_terms = json.loads(VAGUE_TERMS_PATH.read_text(encoding="utf-8"))
        terms = {item["term"]: item for item in vague_terms["terms"]}
        self.assertEqual(vague_terms["default_policy"]["deterministic_promotion"], "forbidden")
        self.assertTrue(terms["稳一点"]["requires_human_confirmation"])
        self.assertTrue(terms["太贵"]["requires_human_confirmation"])
        self.assertTrue(terms["相关"]["requires_human_confirmation"])
        self.assertEqual(terms["中外合作"]["default_rule_class"], "llm_needed")
        self.assertEqual(
            terms["学费两万以内"]["default_rule_class"],
            "deterministic_if_schema_grounded",
        )

    def test_information_requirements_define_minimum_executability_gate(self) -> None:
        requirements = json.loads(INFORMATION_REQUIREMENTS_PATH.read_text(encoding="utf-8"))
        required_user_inputs = {item["field_id"]: item for item in requirements["required_user_inputs"]}
        self.assertEqual(
            set(required_user_inputs),
            {"source_province", "subject_type", "reselected_subjects", "user_rank", "batch"},
        )
        self.assertEqual(
            required_user_inputs["user_rank"]["missing_prompt"],
            "请提供你的省排名/位次。仅凭分数无法稳定判断风险。",
        )
        self.assertIn("专业组最低位次1", requirements["mvp_required_data_fields"])
        self.assertIn("选科要求", requirements["mvp_required_data_fields"])
        self.assertIn("就业前景", requirements["llm_needed_or_external_info"])
        self.assertTrue(requirements["mvp_risk_policy"]["thresholds_require_confirmation"])

    def test_explicit_tuition_cap_can_be_deterministic_when_schema_grounded(self) -> None:
        slots = RegexExtractor().extract("我是广东物理类，排位40000，想看深圳、广州、佛山的学校，学费两万以内。")
        self.assertIsNone(slots["preferences"]["tuition_preference_raw"])
        self.assertEqual(slots["preferences"]["tuition_cap_yuan"], 20000)

        classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(slots)
        deterministic = {rule["rule_id"]: rule for rule in classified["deterministic_rules"]}
        self.assertTrue(deterministic["d_tuition_cap_explicit"]["verification"]["executable"])
        self.assertEqual(deterministic["d_tuition_cap_explicit"]["value"], 20000)
        self.assertNotIn("c_tuition_cap", {rule["rule_id"] for rule in classified["candidate_rules"]})

    def test_deterministic_extractor_handles_common_aliases_and_units(self) -> None:
        slots = RegexExtractor().extract(
            "广东物理类，全省三万二，想学计科，广深优先，预算2w以内。"
        )

        self.assertEqual(slots["user_context"]["source_province"], "广东")
        self.assertEqual(slots["user_context"]["subject_type"], "物理")
        self.assertEqual(slots["user_context"]["user_rank"], 32000)
        self.assertEqual(slots["preferences"]["major_exact_terms"], [])
        self.assertEqual(slots["preferences"]["major_expansion_raw"], "计科")
        self.assertEqual(slots["preferences"]["preferred_cities"], ["广州", "深圳"])
        self.assertEqual(slots["preferences"]["tuition_cap_yuan"], 20000)

    def test_deterministic_extractor_handles_decimal_rank_and_subject_bundle(self) -> None:
        slots = RegexExtractor().extract(
            "我是广东考生，物化生，排名3.2万，计算机类/软件方向，不考虑学费超过2万的。"
        )

        self.assertEqual(slots["user_context"]["subject_type"], "物理")
        self.assertEqual(slots["user_context"]["reselected_subjects"], ["化学", "生物"])
        self.assertEqual(slots["user_context"]["user_rank"], 32000)
        self.assertEqual(
            slots["preferences"]["major_exact_terms"],
            ["计算机", "软件工程"],
        )
        self.assertEqual(slots["preferences"]["tuition_cap_yuan"], 20000)

    def test_cooperation_alias_preserves_user_source_text_without_execution(self) -> None:
        slots = RegexExtractor().extract(
            "广东物理类，排位32000，只给我深圳大学附近的计算机，不要校企合作。"
        )
        classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(slots)

        self.assertEqual(slots["preferences"]["cooperation_preference_raw"], "不要校企合作")
        self.assertEqual(classified["llm_needed_parts"][0]["source_text"], "不要校企合作")
        self.assertEqual(
            classified["non_executable_preferences"][0]["source_text"],
            "不要校企合作",
        )
        self.assertFalse(classified["llm_needed_parts"][0]["verification"]["executable"])

    def test_rule_lifecycle_schema_records_non_llm_execution_boundary(self) -> None:
        lifecycle = json.loads((ROOT / "rules/rule_lifecycle_schema.json").read_text(encoding="utf-8"))
        states = {state["state"]: state for state in lifecycle["states"]}
        self.assertFalse(states["verified_rule"]["may_use_llm"])
        self.assertTrue(states["verified_rule"]["may_execute"])
        self.assertFalse(states["traced_result"]["may_execute"])
        self.assertIn("Neural proposes; symbolic verifies and executes.", lifecycle["principles"])

    def test_extracted_attributes_are_audited_against_excel_schema(self) -> None:
        grounding = AttributeGrounder(self.registry).ground(self.slots)
        by_path = {record["slot_path"]: record for record in grounding["attributes"]}
        self.assertEqual(by_path["user_context.source_province"]["status"], "schema_grounded")
        self.assertEqual(by_path["preferences.risk_preference_raw"]["status"], "confirmable")
        self.assertEqual(by_path["preferences.tuition_preference_raw"]["status"], "confirmable")
        self.assertEqual(by_path["preferences.cooperation_preference_raw"]["status"], "missing_schema")
        self.assertEqual(grounding["summary"]["unsafe_ungrounded_executable_attributes"], 0)

    def test_unknown_llm_attributes_are_ignored_not_executed(self) -> None:
        slots = {
            "input": "demo",
            "user_context": {"source_province": "广东", "subject_type": "物理", "user_rank": 32000},
            "preferences": {
                "major_keyword": "计算机",
                "preferred_cities": ["广州"],
                "school_ownership": "公办",
            },
        }
        grounding = AttributeGrounder(self.registry).ground(slots)
        unknown = [record for record in grounding["attributes"] if record["slot_path"] == "preferences.school_ownership"]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["status"], "ignored_not_schema_mapped")
        self.assertFalse(unknown[0]["can_become_executable_rule"])

    def test_school_quality_preference_is_not_treated_as_safety_margin(self) -> None:
        slots = RegexExtractor().extract("广东物理，排位32000，学校好一点。")
        grounding = AttributeGrounder(self.registry).ground(slots)
        records = {
            str(record["value"]): record
            for record in grounding["attributes"]
        }

        self.assertIsNone(slots["preferences"]["risk_preference_raw"])
        self.assertIn("学校好一点", slots["preferences"]["other_vague_preferences"])
        self.assertEqual(records["学校好一点"]["status"], "missing_schema")
        self.assertFalse(records["学校好一点"]["can_become_executable_rule"])

    def test_llm_proposed_rules_require_symbolic_verification(self) -> None:
        proposed_rules = [
            {
                "rule_id": "p_major_math",
                "source_text": "想报数学系",
                "category": "deterministic",
                "field_id": "major_name",
                "field": "专业名称",
                "operator": "contains",
                "value": "数学",
                "semantic_type": "explicit_user_fact",
            },
            {
                "rule_id": "p_avoid_cooperation",
                "source_text": "不要中外合作",
                "category": "deterministic",
                "field_id": "cooperation_type",
                "operator": "neq",
                "value": "中外合作",
                "semantic_type": "unsupported_structured_preference",
            },
            {
                "rule_id": "p_stable",
                "source_text": "稳一点",
                "category": "candidate",
                "field_id": "group_min_rank_2024",
                "field": "专业组最低位次1",
                "operator": ">=",
                "value": "稳一点",
                "semantic_type": "vague_preference",
                "requires_human_confirmation": True,
            },
        ]

        audited = {
            rule["rule_id"]: rule
            for rule in self.verifier.audit_proposed_rules(proposed_rules)
        }

        self.assertTrue(audited["p_major_math"]["verification"]["executable"])
        self.assertEqual(
            audited["p_major_math"]["verification"]["terminal_status"],
            "executable",
        )
        self.assertFalse(audited["p_avoid_cooperation"]["verification"]["executable"])
        self.assertEqual(
            audited["p_avoid_cooperation"]["verification"]["terminal_status"],
            "rejected_missing_schema",
        )
        self.assertFalse(audited["p_stable"]["verification"]["executable"])
        self.assertEqual(
            audited["p_stable"]["verification"]["terminal_status"],
            "confirmable",
        )

    def test_llm_rank_boundary_proposal_does_not_enter_execution_layer(self) -> None:
        final_rules = [
            {
                "rule_id": "e_source_province",
                "field": "生源地",
                "operator": "eq",
                "value": "广东",
            },
            {
                "rule_id": "e_safety_margin",
                "field": "专业组最低位次1",
                "operator": ">=",
                "value": 36800,
            },
            {
                "rule_id": "e_tuition_cap",
                "field": "学费",
                "operator": "<=",
                "value": 40000,
            },
        ]
        proposed_rules = [
            {
                "rule_id": "p_llm_rank_cap",
                "category": "deterministic",
                "field": "专业组最低位次1",
                "operator": "<=",
                "value": 36800,
                "semantic_type": "explicit_user_fact",
                "verification": {
                    "executable": True,
                    "normalized_value": 36800,
                },
            },
            {
                "rule_id": "p_llm_tuition_duplicate",
                "category": "deterministic",
                "field": "学费",
                "operator": "<=",
                "value": 40000,
                "semantic_type": "explicit_user_fact",
                "verification": {
                    "executable": True,
                    "normalized_value": 40000,
                },
            },
            {
                "rule_id": "p_llm_major",
                "category": "deterministic",
                "field": "专业名称",
                "operator": "contains",
                "value": "计算机",
                "semantic_type": "explicit_user_fact",
                "verification": {
                    "executable": True,
                    "normalized_value": "计算机",
                },
            },
        ]

        merged = _merge_verified_proposed_rules(final_rules, proposed_rules)
        merged_ids = {rule["rule_id"] for rule in merged}

        self.assertNotIn("e_p_llm_rank_cap", merged_ids)
        self.assertNotIn("e_p_llm_tuition_duplicate", merged_ids)
        self.assertIn("e_p_llm_major", merged_ids)
        self.assertEqual(
            proposed_rules[0]["execution_merge_status"],
            "not_merged",
        )
        self.assertIn("排位安全边界", proposed_rules[0]["execution_merge_reason"])
        self.assertEqual(
            proposed_rules[1]["execution_merge_status"],
            "not_merged",
        )
        self.assertEqual(
            proposed_rules[2]["execution_merge_status"],
            "merged",
        )

    def test_schema_summary_for_llm_exposes_fields_not_rows(self) -> None:
        summary = self.registry.field_summary_for_llm()
        by_id = {field["field_id"]: field for field in summary}

        self.assertIn("major_name", by_id)
        self.assertEqual(by_id["major_name"]["source_column"], "专业名称")
        self.assertIn("contains", by_id["major_name"]["allowed_ops"])
        self.assertIn("cooperation_type", by_id)
        self.assertFalse(by_id["cooperation_type"]["active"])
        self.assertNotIn("rows", by_id["major_name"])

    def test_structured_hard_filters_override_soft_prompt_for_api_workbench(self) -> None:
        config = WorkbenchConfig(
            user_input="广东历史，排位25000，法学，预算有限。",
            hard_filters={
                "source_province": "广东",
                "subject_type": "历史",
                "user_rank": 25000,
                "major_keyword": "法学",
                "preferred_cities": [],
                "tuition_cap_yuan": None,
            },
            soft_preferences={
                "prompt": "预算有限",
                "safety_margin_percent": None,
                "tuition_cap_yuan": 20000,
            },
        )
        extracted = RegexExtractor().extract(config.soft_preferences["prompt"])
        slots = _slots_from_inputs(extracted, config)
        classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(slots)
        classified = _apply_soft_confirmations(classified, config, slots)
        final_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=True,
        ).final_executable_rules(classified)

        self.assertEqual(slots["preferences"]["major_keyword"], "法学")
        self.assertEqual(
            {rule["rule_id"] for rule in classified["candidate_rules"]},
            {"c_tuition_cap"},
        )
        self.assertNotIn("c_major_expansion", {rule["rule_id"] for rule in classified["candidate_rules"]})
        self.assertIn("e_tuition_cap", {rule["rule_id"] for rule in final_rules})
        self.assertNotIn("e_safety_margin", {rule["rule_id"] for rule in final_rules})

    def test_api_soft_safety_rule_executes_only_when_confirmed(self) -> None:
        base_config = WorkbenchConfig(
            user_input="广东物理，排位32000，计算机，稳一点。",
            hard_filters={
                "source_province": "广东",
                "subject_type": "物理",
                "user_rank": 32000,
                "major_keyword": "计算机",
                "preferred_cities": [],
                "tuition_cap_yuan": None,
            },
            soft_preferences={
                "prompt": "稳一点",
                "safety_margin_percent": None,
                "tuition_cap_yuan": None,
            },
        )
        slots = _slots_from_inputs(
            RegexExtractor().extract(base_config.soft_preferences["prompt"]),
            base_config,
        )
        classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(slots)
        classified = _apply_soft_confirmations(classified, base_config, slots)
        unconfirmed_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=True,
        ).final_executable_rules(classified)
        self.assertNotIn("e_safety_margin", {rule["rule_id"] for rule in unconfirmed_rules})

        confirmed_config = WorkbenchConfig(
            user_input=base_config.user_input,
            hard_filters=base_config.hard_filters,
            soft_preferences={
                **base_config.soft_preferences,
                "safety_margin_percent": 5,
            },
        )
        confirmed_slots = _slots_from_inputs(
            RegexExtractor().extract(confirmed_config.soft_preferences["prompt"]),
            confirmed_config,
        )
        confirmed_classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(confirmed_slots)
        confirmed_classified = _apply_soft_confirmations(
            confirmed_classified,
            confirmed_config,
            confirmed_slots,
        )
        confirmed_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=True,
        ).final_executable_rules(confirmed_classified)
        safety_rule = next(rule for rule in confirmed_rules if rule["rule_id"] == "e_safety_margin")
        self.assertEqual(safety_rule["operator"], "between")
        self.assertEqual(safety_rule["value"], [30400, 33600])

    def test_api_boundary_options_create_structured_confirmed_rules(self) -> None:
        config = WorkbenchConfig(
            user_input="广东物理，排位32000。",
            hard_filters={
                "source_province": "广东",
                "subject_type": "物理",
                "user_rank": 32000,
                "major_keyword": None,
                "preferred_cities": [],
                "tuition_cap_yuan": None,
            },
            soft_preferences={
                "prompt": "",
                "safety_margin_percent": 10,
                "tuition_cap_yuan": 20000,
            },
        )
        slots = _slots_from_inputs(RegexExtractor().extract(""), config)
        classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(slots)
        classified = _apply_soft_confirmations(classified, config, slots)
        final_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=True,
        ).final_executable_rules(classified)

        self.assertEqual(
            {rule["rule_id"] for rule in classified["candidate_rules"]},
            {"c_safety_margin", "c_tuition_cap"},
        )
        final_by_id = {rule["rule_id"]: rule for rule in final_rules}
        self.assertEqual(final_by_id["e_safety_margin"]["operator"], "between")
        self.assertEqual(final_by_id["e_safety_margin"]["value"], [28800, 35200])
        self.assertEqual(final_by_id["e_tuition_cap"]["value"], 20000)

    def test_empty_soft_prompt_does_not_fall_back_to_default_demo_input(self) -> None:
        config = WorkbenchConfig(
            hard_filters={
                "source_province": "广东",
                "subject_type": "物理",
                "reselected_subjects": ["化学", "生物"],
                "user_rank": 32000,
                "major_keyword": None,
                "preferred_cities": [],
                "tuition_cap_yuan": None,
            },
            soft_preferences={
                "prompt": "",
                "safety_margin_percent": 10,
                "tuition_cap_yuan": 20000,
            },
        )

        slots, _ = _extract_slots(config)

        self.assertIsNone(slots["preferences"].get("major_keyword"))
        self.assertEqual(slots["preferences"].get("preferred_cities"), [])
        self.assertIsNone(slots["preferences"].get("cooperation_preference_raw"))
        self.assertEqual(slots["preferences"]["risk_preference_raw"], "已选择10%位次窗口")
        self.assertEqual(slots["preferences"]["tuition_preference_raw"], "已选择20000元费用上限")

    def test_reselected_subjects_become_verified_subject_requirement_rule(self) -> None:
        config = WorkbenchConfig(
            user_input="广东物理，化学生物，排位32000，想学计算机。",
            hard_filters={
                "source_province": "广东",
                "subject_type": "物理",
                "reselected_subjects": ["化学", "生物"],
                "user_rank": 32000,
                "major_keyword": None,
                "preferred_cities": [],
                "tuition_cap_yuan": None,
            },
            soft_preferences={"prompt": "想学计算机。"},
        )
        slots = _slots_from_inputs(RegexExtractor().extract("想学计算机。"), config)
        classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(slots)
        deterministic = {rule["rule_id"]: rule for rule in classified["deterministic_rules"]}

        self.assertEqual(slots["user_context"]["reselected_subjects"], ["化学", "生物"])
        self.assertTrue(deterministic["d_subject_requirement"]["verification"]["executable"])

    def test_executor_filters_by_subject_requirement(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "ID": 1,
                    "生源地": "广东",
                    "科类": "物理",
                    "选科要求": "化学和生物",
                    "专业名称": "计算机科学与技术",
                    "专业组最低位次1": 40000,
                    "学费": 6000,
                },
                {
                    "ID": 2,
                    "生源地": "广东",
                    "科类": "物理",
                    "选科要求": "政治",
                    "专业名称": "计算机科学与技术",
                    "专业组最低位次1": 41000,
                    "学费": 6000,
                },
            ]
        )
        rules = [
            {
                "rule_id": "e_subject_requirement",
                "field": "选科要求",
                "operator": "satisfies_subject_requirement",
                "value": ["化学", "生物"],
            }
        ]

        results = PandasExecutor().execute(dataframe, rules, user_rank=32000)

        self.assertEqual([row["ID"] for row in results], [1])
        self.assertEqual(results[0]["选科要求"], "化学和生物")

    def test_executor_filters_rank_window_and_sorts_by_lower_rank_number(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "ID": 1,
                    "生源地": "广东",
                    "科类": "物理",
                    "专业名称": "计算机科学与技术",
                    "专业组最低位次1": 168764,
                    "学费": 6000,
                },
                {
                    "ID": 2,
                    "生源地": "广东",
                    "科类": "物理",
                    "专业名称": "计算机科学与技术",
                    "专业组最低位次1": 33000,
                    "学费": 6000,
                },
                {
                    "ID": 3,
                    "生源地": "广东",
                    "科类": "物理",
                    "专业名称": "计算机科学与技术",
                    "专业组最低位次1": 29000,
                    "学费": 6000,
                },
                {
                    "ID": 4,
                    "生源地": "广东",
                    "科类": "物理",
                    "专业名称": "计算机科学与技术",
                    "专业组最低位次1": 36000,
                    "学费": 6000,
                },
            ]
        )
        rules = [
            {
                "rule_id": "e_safety_margin",
                "field": "专业组最低位次1",
                "operator": "between",
                "value": [28800, 35200],
            }
        ]

        results = PandasExecutor().execute(dataframe, rules, user_rank=32000)

        self.assertEqual([row["ID"] for row in results], [3, 2])
        self.assertEqual([row["专业组最低位次1"] for row in results], [29000, 33000])

    def test_trace_generator_uses_current_executable_rules(self) -> None:
        row = {
            "生源地": "广东",
            "科类": "历史",
            "专业名称": "法学",
            "学费": 5000,
            "专业组最低位次1": 25667,
            "城市": "长沙",
        }
        rules = [
            {"rule_id": "e_source_province", "field": "生源地", "operator": "eq", "value": "广东"},
            {"rule_id": "e_subject_type", "field": "科类", "operator": "eq", "value": "历史"},
            {"rule_id": "e_major_keyword", "field": "专业名称", "operator": "contains", "value": "法学"},
            {
                "rule_id": "e_safety_margin",
                "field": "专业组最低位次1",
                "operator": "between",
                "value": [25000, 30000],
            },
            {"rule_id": "e_tuition_cap", "field": "学费", "operator": "<=", "value": 20000},
        ]

        traced = TraceGenerator().add_traces([row], executable_rules=rules)[0]["trace"]
        reason_text = "\n".join(item["reason"] for item in traced)

        self.assertIn("科类 等于 历史", reason_text)
        self.assertIn("专业名称 包含 法学", reason_text)
        self.assertIn("专业组最低位次1 25667 位于 25000-30000 名的窗口内", reason_text)
        self.assertIn("学费 5000 不高于 20000", reason_text)
        self.assertNotIn("科类 等于 物理", reason_text)
        self.assertNotIn("专业名称 包含 计算机", reason_text)
        self.assertNotIn("35200", reason_text)


if __name__ == "__main__":
    unittest.main()
