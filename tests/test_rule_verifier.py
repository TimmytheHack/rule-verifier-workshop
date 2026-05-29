from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.extractors.regex_extractor import RegexExtractor
from src.rules.rule_classifier import RuleClassifier
from src.rules.rule_promoter import RulePromoter
from src.rules.rule_verifier import RuleVerifier
from src.schema.schema_registry import SchemaRegistry


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/schema_registry.json"
TAXONOMY_PATH = ROOT / "rules/rule_taxonomy.json"
VAGUE_TERMS_PATH = ROOT / "rules/vague_terms.json"
DEMO_INPUT = "我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。"
AVAILABLE_COLUMNS = ["生源地", "科类", "专业名称", "城市", "专业组最低位次1", "学费"]


class RuleVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = SchemaRegistry.from_file(SCHEMA_PATH, AVAILABLE_COLUMNS)
        self.verifier = RuleVerifier(self.registry)
        slots = RegexExtractor().extract(DEMO_INPUT)
        self.classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(slots)

    def test_deterministic_rules_are_executable_when_schema_grounded(self) -> None:
        rules = {rule["rule_id"]: rule for rule in self.classified["deterministic_rules"]}
        self.assertTrue(rules["d_source_province"]["verification"]["executable"])
        self.assertTrue(rules["d_subject_type"]["verification"]["executable"])
        self.assertTrue(rules["d_major_keyword"]["verification"]["executable"])
        self.assertTrue(rules["d_city"]["verification"]["executable"])

    def test_candidate_rules_do_not_execute_before_confirmation(self) -> None:
        for rule in self.classified["candidate_rules"]:
            self.assertTrue(rule["requires_human_confirmation"])
            self.assertTrue(rule["verification"]["ambiguity_detected"])
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
        terms = {item["term"]: item for item in vague_terms}
        self.assertTrue(terms["稳一点"]["requires_human_confirmation"])
        self.assertTrue(terms["太贵"]["requires_human_confirmation"])
        self.assertTrue(terms["相关"]["requires_human_confirmation"])


if __name__ == "__main__":
    unittest.main()
