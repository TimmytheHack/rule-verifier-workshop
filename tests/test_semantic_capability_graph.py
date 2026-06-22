import unittest

from src.semantic.capability_graph import DatasetCapabilityGraph
from tests.semantic_test_utils import new_admissions_dataset


class SemanticCapabilityGraphTest(unittest.TestCase):
    def test_graph_profiles_new_admissions_columns(self) -> None:
        with new_admissions_dataset() as dataset:
            graph = DatasetCapabilityGraph.from_dataset(dataset)

        self.assertEqual(4, graph.row_count)
        self.assertIn("专业", graph.fields)
        self.assertEqual("number", graph.fields["最低位次"].inferred_type)
        self.assertIn("between", graph.fields["最低位次"].candidate_ops)
        self.assertIn("contains", graph.fields["专业"].candidate_ops)
        self.assertIn("sort", graph.fields["最低分数"].candidate_ops)

    def test_graph_records_only_explicit_expected_columns_as_missing(self) -> None:
        with new_admissions_dataset() as dataset:
            graph = DatasetCapabilityGraph.from_dataset(
                dataset,
                expected_source_columns=["专业", "学费", "城市"],
            )

        self.assertIn("学费", graph.missing_source_columns)
        self.assertIn("城市", graph.missing_source_columns)
        self.assertNotIn("专业", graph.missing_source_columns)


if __name__ == "__main__":
    unittest.main()
