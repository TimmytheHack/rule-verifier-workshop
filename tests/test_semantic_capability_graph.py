import unittest

from src.domains import DomainConfig
from src.semantic.capability_graph import DatasetCapabilityGraph
from src.semantic.reviewed_mapping import ReviewedMappingRegistry
from src.semantic.semantic_candidates import RuleBasedSemanticCandidateGenerator
from tests.semantic_test_utils import new_admissions_dataset


class SemanticCapabilityGraphTest(unittest.TestCase):
    def test_next_fixture_keeps_workbook_path_available(self) -> None:
        dataset = next(new_admissions_dataset())

        self.assertTrue(dataset.workbook_path.exists())

    def test_graph_profiles_new_admissions_columns(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(dataset)

        self.assertEqual(4, graph.row_count)
        self.assertEqual(17, graph.column_count)
        self.assertIn("专业", graph.fields)
        self.assertEqual("number", graph.fields["最低位次"].inferred_type)
        self.assertEqual(0.0, graph.fields["最低位次"].missing_rate)
        self.assertEqual(
            0.0,
            graph.fields["最低位次"].to_dict()["missing_rate"],
        )
        self.assertEqual("enum_or_category", graph.fields["专业"].inferred_type)
        self.assertIn("between", graph.fields["最低位次"].candidate_ops)
        self.assertIn("in", graph.fields["专业"].candidate_ops)
        self.assertIn("not_in", graph.fields["专业"].candidate_ops)
        self.assertIn("contains_any", graph.fields["专业"].candidate_ops)
        self.assertIn("sort", graph.fields["专业"].candidate_ops)
        self.assertIn("sort", graph.fields["最低分数"].candidate_ops)

    def test_graph_records_only_explicit_expected_columns_as_missing(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(
            dataset,
            expected_source_columns=["专业", "学费", "城市", "专业组最低位次1"],
        )

        self.assertIn("学费", graph.missing_source_columns)
        self.assertIn("城市", graph.missing_source_columns)
        self.assertIn("专业组最低位次1", graph.missing_source_columns)
        self.assertNotIn("专业", graph.missing_source_columns)


class SemanticMappingTest(unittest.TestCase):
    def test_rule_based_candidates_for_new_admissions_headers(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        domain = DomainConfig.load("admissions")

        candidates = RuleBasedSemanticCandidateGenerator.from_domain(domain).generate(
            graph
        )

        by_field = {
            candidate["canonical_field_id"]: candidate
            for candidate in candidates
        }
        self.assertEqual("专业", by_field["major_name"]["source_column"])
        self.assertEqual("最低位次", by_field["major_min_rank"]["source_column"])
        self.assertEqual("最低分数", by_field["major_min_score"]["source_column"])
        self.assertEqual("学校所在", by_field["school_province"]["source_column"])

    def test_candidate_generator_has_no_builtin_admissions_header_map(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(dataset)

        candidates = RuleBasedSemanticCandidateGenerator({}).generate(graph)

        self.assertEqual([], candidates)

    def test_reviewed_mapping_registry_activates_only_existing_columns(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        domain = DomainConfig.load("admissions")

        registry = ReviewedMappingRegistry.from_domain(domain, graph)

        self.assertEqual("专业", registry.source_column("major_name"))
        self.assertEqual("最低位次", registry.source_column("major_min_rank"))
        self.assertTrue(registry.has_op("major_name", "contains_any"))
        self.assertTrue(registry.has_op("major_min_rank", "between"))
        self.assertFalse(registry.has_field("tuition_yuan_per_year"))
        self.assertIn("tuition_yuan_per_year", registry.unsupported_field_ids())


if __name__ == "__main__":
    unittest.main()
