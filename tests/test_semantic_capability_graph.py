import unittest

from src.semantic.capability_graph import DatasetCapabilityGraph
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


if __name__ == "__main__":
    unittest.main()
