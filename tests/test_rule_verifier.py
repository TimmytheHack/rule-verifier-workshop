from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.extractors.regex_extractor import RegexExtractor
from src.rules.rule_classifier import RuleClassifier
from src.rules.rule_promoter import RulePromoter
from src.rules.rule_verifier import RuleVerifier
from src.schema.attribute_grounder import AttributeGrounder
from src.schema.schema_registry import SchemaRegistry


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/schema_registry.json"
TAXONOMY_PATH = ROOT / "rules/rule_taxonomy.json"
VAGUE_TERMS_PATH = ROOT / "rules/vague_terms.json"
INFORMATION_REQUIREMENTS_PATH = ROOT / "rules/information_requirements.json"
DEMO_INPUT = "我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。"
AVAILABLE_COLUMNS = ["生源地", "科类", "专业名称", "城市", "专业组最低位次1", "学费"]


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
            {"source_province", "subject_type", "user_rank", "batch"},
        )
        self.assertEqual(
            required_user_inputs["user_rank"]["missing_prompt"],
            "请提供你的省排名/位次。仅凭分数无法稳定判断风险。",
        )
        self.assertIn("专业组最低位次1", requirements["mvp_required_data_fields"])
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


if __name__ == "__main__":
    unittest.main()
