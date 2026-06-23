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

    def test_graph_profiles_boolean_like_sparse_columns_and_top_values(self) -> None:
        from pathlib import Path

        import pandas as pd
        from src.adapters.excel_adapter import ExcelDataSet

        dataframe = pd.DataFrame(
            [
                {"专业": "计算机科学与技术", "是否中外合作": "否", "最低位次": "10242"},
                {"专业": "人工智能", "是否中外合作": "否", "最低位次": "15000"},
                {"专业": "软件工程", "是否中外合作": "是", "最低位次": "18000"},
                {"专业": "人工智能", "是否中外合作": "", "最低位次": "无"},
            ]
        )
        dataset = ExcelDataSet(
            workbook_path=Path("fixture.xlsx"),
            sheet_name="Sheet1",
            header_row=0,
            headers=list(dataframe.columns),
            header_index={name: index for index, name in enumerate(dataframe.columns)},
            dataframe=dataframe,
        )

        graph = DatasetCapabilityGraph.from_dataset(dataset)
        cooperation = graph.fields["是否中外合作"].to_dict()
        rank = graph.fields["最低位次"].to_dict()
        major = graph.fields["专业"].to_dict()

        self.assertEqual(cooperation["boolean_profile"]["true_count"], 1)
        self.assertEqual(cooperation["boolean_profile"]["false_count"], 2)
        self.assertEqual(cooperation["boolean_profile"]["null_count"], 1)
        self.assertEqual(cooperation["boolean_profile"]["other_count"], 0)
        self.assertAlmostEqual(cooperation["boolean_profile"]["true_rate"], 0.25)
        self.assertIn("boolean_preferred_value", cooperation["candidate_ops"])
        self.assertEqual(rank["parse_success_rate"], 0.75)
        self.assertEqual(major["top_values"][0], {"value": "人工智能", "count": 2})
        self.assertTrue(major["distinct_values_complete"])
        self.assertIn("计算机科学与技术", major["distinct_values"])

    def test_graph_treats_pandas_missing_values_as_sparse_boolean_nulls(self) -> None:
        from pathlib import Path

        import pandas as pd
        from src.adapters.excel_adapter import ExcelDataSet

        dataframe = pd.DataFrame(
            [
                {"是否中外合作": "是"},
                {"是否中外合作": "否"},
                {"是否中外合作": float("nan")},
                {"是否中外合作": pd.NA},
            ]
        )
        dataset = ExcelDataSet(
            workbook_path=Path("fixture.xlsx"),
            sheet_name="Sheet1",
            header_row=0,
            headers=list(dataframe.columns),
            header_index={name: index for index, name in enumerate(dataframe.columns)},
            dataframe=dataframe,
        )

        graph = DatasetCapabilityGraph.from_dataset(dataset)
        cooperation = graph.fields["是否中外合作"].to_dict()

        self.assertEqual(cooperation["boolean_profile"]["true_count"], 1)
        self.assertEqual(cooperation["boolean_profile"]["false_count"], 1)
        self.assertEqual(cooperation["boolean_profile"]["null_count"], 2)
        self.assertEqual(cooperation["boolean_profile"]["other_count"], 0)
        self.assertTrue(cooperation["boolean_profile"]["is_boolean_like"])
        self.assertIn("boolean_preferred_value", cooperation["candidate_ops"])


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
