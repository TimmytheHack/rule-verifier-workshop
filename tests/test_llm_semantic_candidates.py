import json
import unittest
from dataclasses import dataclass
from typing import Any

from src.domains import DomainConfig
from src.semantic.capability_graph import DatasetCapabilityGraph
from src.semantic.llm_semantic_candidates import DeepSeekSemanticCandidateGenerator
from tests.semantic_test_utils import new_admissions_dataset


@dataclass(frozen=True)
class _FakeResponse:
    payload: Any
    usage: dict[str, int]


class _FakeClient:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.system_prompt = ""
        self.user_prompt = ""

    def chat_json(self, system_prompt: str, user_prompt: str) -> _FakeResponse:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return _FakeResponse(
            payload=self.payload,
            usage={"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
        )


class _DomainStub:
    def __init__(self, semantic_capabilities: dict[str, Any]) -> None:
        self.semantic_capabilities = semantic_capabilities


class DeepSeekSemanticCandidateGeneratorTest(unittest.TestCase):
    def _graph_and_domain(self) -> tuple[DatasetCapabilityGraph, DomainConfig]:
        dataset = next(new_admissions_dataset())
        return DatasetCapabilityGraph.from_dataset(dataset), DomainConfig.load(
            "admissions"
        )

    def test_generate_accepts_schema_grounded_candidates_only(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "最低位次",
                        "canonical_field_id": "major_min_rank",
                        "confidence": 0.87,
                        "evidence": ["列名与专业最低位次语义一致"],
                        "risks": ["可能与专业组最低位次混淆"],
                        "proposed_ops": ["between", "sort"],
                    },
                    {
                        "source_column": "不存在列",
                        "canonical_field_id": "city",
                        "confidence": 0.4,
                        "evidence": ["列名近似城市"],
                        "risks": ["源列不存在"],
                        "proposed_ops": ["eq"],
                    },
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual(1, len(result.candidates))
        accepted = result.candidates[0]
        self.assertEqual("最低位次", accepted["source_column"])
        self.assertEqual("major_min_rank", accepted["canonical_field_id"])
        self.assertEqual(0.87, accepted["confidence"])
        self.assertEqual(["列名与专业最低位次语义一致"], accepted["evidence"])
        self.assertEqual(["between", "sort"], accepted["proposed_ops"])
        self.assertEqual("candidate_only", accepted["status"])
        self.assertEqual(1, len(result.rejected_candidates))
        self.assertEqual(
            "unknown_source_column",
            result.rejected_candidates[0]["reason"],
        )
        self.assertIn("canonical_fields", client.user_prompt)
        self.assertNotIn("raw_sql", client.user_prompt)
        self.assertEqual(12, result.usage["total_tokens"])

    def test_generate_rejects_unknown_canonical_field(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "最低位次",
                        "canonical_field_id": "unknown_rank",
                        "confidence": 0.8,
                        "evidence": ["列名与位次相关"],
                        "risks": [],
                        "proposed_ops": ["sort"],
                    }
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual([], result.candidates)
        self.assertEqual(1, len(result.rejected_candidates))
        self.assertEqual(
            "unknown_canonical_field",
            result.rejected_candidates[0]["reason"],
        )

    def test_prompt_includes_field_profiles_and_untrusted_data_instruction(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient({"candidates": []})

        DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        prompt = json.loads(client.user_prompt)
        rank_column = next(
            column
            for column in prompt["columns"]
            if column["source_column"] == "最低位次"
        )
        self.assertIn("top_values", rank_column)
        self.assertIn("boolean_profile", rank_column)
        self.assertIn("不可信数据", client.system_prompt)

    def test_generate_filters_ops_by_reviewed_mapping(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "最低分数",
                        "canonical_field_id": "major_min_score",
                        "confidence": 0.76,
                        "evidence": ["列名与最低分数一致"],
                        "risks": [],
                        "proposed_ops": [
                            "between",
                            "sort",
                            "satisfies_subject_requirement",
                        ],
                    }
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual(1, len(result.candidates))
        self.assertEqual(["sort"], result.candidates[0]["proposed_ops"])

    def test_generate_supports_reviewed_mappings_list_shape(self) -> None:
        graph, _domain = self._graph_and_domain()
        domain = _DomainStub(
            {
                "reviewed_mappings": [
                    {
                        "field_id": "major_min_rank",
                        "allowed_ops": ["sort"],
                    }
                ]
            }
        )
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "最低位次",
                        "canonical_field_id": "major_min_rank",
                        "confidence": 0.76,
                        "evidence": ["列名与最低位次一致"],
                        "risks": [],
                        "proposed_ops": ["between", "sort"],
                    }
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        prompt = json.loads(client.user_prompt)
        self.assertEqual(["major_min_rank"], prompt["canonical_fields"])
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(["sort"], result.candidates[0]["proposed_ops"])

    def test_generate_rejects_raw_sql_candidates(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "最低位次",
                        "canonical_field_id": "major_min_rank",
                        "confidence": 0.87,
                        "raw_sql": "最低位次 BETWEEN 1000 AND 2000",
                    }
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual([], result.candidates)
        self.assertEqual(1, len(result.rejected_candidates))
        self.assertEqual("raw_sql_forbidden", result.rejected_candidates[0]["reason"])

    def test_generate_rejects_sql_like_accepted_evidence_and_risks(self) -> None:
        graph, domain = self._graph_and_domain()
        for key in ("evidence", "risks"):
            with self.subTest(key=key):
                candidate = {
                    "source_column": "最低位次",
                    "canonical_field_id": "major_min_rank",
                    "confidence": 0.87,
                    "evidence": ["列名与专业最低位次语义一致"],
                    "risks": [],
                    "proposed_ops": ["sort"],
                }
                candidate[key] = ["SELECT * FROM admissions"]
                client = _FakeClient({"candidates": [candidate]})

                result = DeepSeekSemanticCandidateGenerator(client).generate(
                    graph=graph,
                    domain_config=domain,
                )

                self.assertEqual([], result.candidates)
                self.assertEqual(1, len(result.rejected_candidates))
                self.assertEqual(
                    "raw_sql_forbidden",
                    result.rejected_candidates[0]["reason"],
                )

    def test_generate_rejects_invalid_confidence_values(self) -> None:
        graph, domain = self._graph_and_domain()
        invalid_values = [
            float("nan"),
            float("inf"),
            -0.1,
            1.1,
            "NaN",
            "Infinity",
            "-0.1",
            "1.1",
        ]
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "最低位次",
                        "canonical_field_id": "major_min_rank",
                        "confidence": value,
                        "evidence": ["列名与专业最低位次语义一致"],
                        "risks": [],
                        "proposed_ops": ["sort"],
                    }
                    for value in invalid_values
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual([], result.candidates)
        self.assertEqual(len(invalid_values), len(result.rejected_candidates))
        self.assertEqual(
            ["invalid_candidate_shape"] * len(invalid_values),
            [candidate["reason"] for candidate in result.rejected_candidates],
        )

    def test_generate_rejects_sql_candidates_at_any_depth(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "最低位次",
                        "canonical_field_id": "major_min_rank",
                        "confidence": 0.87,
                        "sql": "最低位次 BETWEEN 1000 AND 2000",
                    },
                    {
                        "source_column": "最低位次",
                        "canonical_field_id": "major_min_rank",
                        "confidence": 0.87,
                        "metadata": {"sql": "ORDER BY 最低位次 ASC"},
                    },
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual([], result.candidates)
        self.assertEqual(2, len(result.rejected_candidates))
        self.assertEqual(
            ["raw_sql_forbidden", "raw_sql_forbidden"],
            [candidate["reason"] for candidate in result.rejected_candidates],
        )

    def test_generate_sanitizes_malformed_rejected_candidates(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            {
                "candidates": [
                    [
                        {"sql": "SELECT * FROM admissions", "note": "保留"},
                        {
                            "raw_sql": "DROP TABLE admissions",
                            "nested": {"sql": "WHERE 1 = 1", "label": "安全"},
                        },
                    ]
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual([], result.candidates)
        self.assertEqual(1, len(result.rejected_candidates))
        self.assertEqual(
            "invalid_candidate_shape",
            result.rejected_candidates[0]["reason"],
        )
        self.assertEqual(
            [{"note": "保留"}, {"nested": {"label": "安全"}}],
            result.rejected_candidates[0]["candidate"],
        )

    def test_generate_rejects_non_dict_payload_shape(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            [
                {"raw_sql": "SELECT * FROM admissions", "note": "保留"},
                {"nested": {"sql": "WHERE 1 = 1", "label": "安全"}},
            ]
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual([], result.candidates)
        self.assertEqual(1, len(result.rejected_candidates))
        self.assertEqual(
            "invalid_candidate_shape",
            result.rejected_candidates[0]["reason"],
        )
        self.assertEqual(
            [{"note": "保留"}, {"nested": {"label": "安全"}}],
            result.rejected_candidates[0]["candidate"],
        )

    def test_generate_rejects_non_list_candidates_shape(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            {
                "candidates": {
                    "raw_sql": "SELECT * FROM admissions",
                    "items": [{"sql": "WHERE 1 = 1", "label": "安全"}],
                }
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual([], result.candidates)
        self.assertEqual(1, len(result.rejected_candidates))
        self.assertEqual(
            "invalid_candidate_shape",
            result.rejected_candidates[0]["reason"],
        )
        self.assertEqual(
            {"items": [{"label": "安全"}]},
            result.rejected_candidates[0]["candidate"],
        )

    def test_generate_rejects_dict_payload_without_candidates(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient({"message": "缺少候选数组"})

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual([], result.candidates)
        self.assertEqual(1, len(result.rejected_candidates))
        self.assertEqual(
            "invalid_candidate_shape",
            result.rejected_candidates[0]["reason"],
        )

    def test_generate_rejects_top_level_sql_keys(self) -> None:
        graph, domain = self._graph_and_domain()
        for key in ("raw_sql", "sql", "SQL"):
            with self.subTest(key=key):
                client = _FakeClient(
                    {
                        key: "SELECT * FROM admissions",
                        "candidates": [],
                        "note": "保留",
                    }
                )

                result = DeepSeekSemanticCandidateGenerator(client).generate(
                    graph=graph,
                    domain_config=domain,
                )

                self.assertEqual([], result.candidates)
                self.assertEqual(1, len(result.rejected_candidates))
                self.assertEqual(
                    "raw_sql_forbidden",
                    result.rejected_candidates[0]["reason"],
                )
                self.assertEqual(
                    {"candidates": [], "note": "保留"},
                    result.rejected_candidates[0]["candidate"],
                )

    def test_generate_rejects_nested_top_level_sql_keys(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            {
                "metadata": {"sql": "SELECT * FROM admissions"},
                "candidates": [
                    {
                        "source_column": "最低位次",
                        "canonical_field_id": "major_min_rank",
                        "confidence": 0.87,
                        "evidence": ["列名与专业最低位次语义一致"],
                        "risks": [],
                        "proposed_ops": ["sort"],
                    }
                ],
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual([], result.candidates)
        self.assertEqual(1, len(result.rejected_candidates))
        self.assertEqual("raw_sql_forbidden", result.rejected_candidates[0]["reason"])
        serialized = json.dumps(result.rejected_candidates, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM admissions", serialized)

    def test_generate_rejects_candidate_missing_required_shape_fields(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "最低位次",
                        "canonical_field_id": "major_min_rank",
                        "confidence": 0.87,
                    }
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual([], result.candidates)
        self.assertEqual(1, len(result.rejected_candidates))
        self.assertEqual(
            "invalid_candidate_shape",
            result.rejected_candidates[0]["reason"],
        )

    def test_generate_rejects_candidate_with_wrong_list_shapes(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "最低位次",
                        "canonical_field_id": "major_min_rank",
                        "confidence": 0.87,
                        "evidence": "列名与专业最低位次语义一致",
                        "risks": "无",
                        "proposed_ops": "sort",
                    }
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual([], result.candidates)
        self.assertEqual(1, len(result.rejected_candidates))
        self.assertEqual(
            "invalid_candidate_shape",
            result.rejected_candidates[0]["reason"],
        )

    def test_generate_rejects_candidate_with_non_string_list_items(self) -> None:
        graph, domain = self._graph_and_domain()
        invalid_candidates = []
        for key, value in (
            ("evidence", [123]),
            ("risks", [{}]),
            ("proposed_ops", [1]),
        ):
            candidate = {
                "source_column": "最低位次",
                "canonical_field_id": "major_min_rank",
                "confidence": 0.87,
                "evidence": ["列名与专业最低位次语义一致"],
                "risks": [],
                "proposed_ops": ["sort"],
            }
            candidate[key] = value
            invalid_candidates.append(candidate)
        client = _FakeClient({"candidates": invalid_candidates})

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual([], result.candidates)
        self.assertEqual(3, len(result.rejected_candidates))
        self.assertEqual(
            ["invalid_candidate_shape"] * 3,
            [candidate["reason"] for candidate in result.rejected_candidates],
        )

    def test_generate_sanitizes_sql_like_text_in_rejected_diagnostics(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "不存在列",
                        "canonical_field_id": "major_min_rank",
                        "confidence": 0.31,
                        "evidence": ["SELECT * FROM admissions"],
                        "risks": ["delete from admissions where 1 = 1"],
                        "debug": ["SELECT", "SELECT 1"],
                        "notes": [
                            "ORDER BY rank",
                            "WHERE x = 1",
                            "BETWEEN 1 AND 2",
                        ],
                    }
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        serialized = json.dumps(result.rejected_candidates, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM admissions", serialized)
        self.assertNotIn('"SELECT"', serialized)
        self.assertNotIn("SELECT 1", serialized)
        self.assertNotIn("delete from admissions", serialized)
        self.assertNotIn("ORDER BY rank", serialized)
        self.assertNotIn("WHERE x = 1", serialized)
        self.assertNotIn("BETWEEN 1 AND 2", serialized)
        self.assertIn("[removed_sql]", serialized)

    def test_generate_sanitizes_sql_like_rejected_diagnostic_keys(self) -> None:
        graph, domain = self._graph_and_domain()
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "不存在列",
                        "canonical_field_id": "major_min_rank",
                        "confidence": 0.31,
                        "evidence": [],
                        "risks": [],
                        "proposed_ops": [],
                        "SELECT * FROM admissions": "保留",
                    }
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        serialized = json.dumps(result.rejected_candidates, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM admissions", serialized)
        self.assertIn("[removed_sql]", result.rejected_candidates[0]["candidate"])


if __name__ == "__main__":
    unittest.main()
