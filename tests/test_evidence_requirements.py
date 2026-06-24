from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from src.semantic.evidence_requirements import (
    DeepSeekEvidenceRequirementClassifier,
    EvidenceRequirement,
    EvidenceRequirementResult,
)


@dataclass(frozen=True)
class _FakeResponse:
    payload: Any
    usage: Any


class _FakeClient:
    def __init__(
        self,
        payload: Any,
        usage: Any | None = None,
    ) -> None:
        self.payload = payload
        self.usage = {"total_tokens": 9} if usage is None else usage
        self.system_prompt = ""
        self.user_prompt = ""

    def chat_json(self, system_prompt: str, user_prompt: str) -> _FakeResponse:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return _FakeResponse(payload=self.payload, usage=self.usage)


class EvidenceRequirementTest(unittest.TestCase):
    def _classify(
        self,
        payload: Any,
        usage: Any | None = None,
    ) -> tuple[EvidenceRequirementResult, _FakeClient]:
        client = _FakeClient(payload, usage=usage)
        result = DeepSeekEvidenceRequirementClassifier(client).classify(
            text="想读人工智能，计算机，学校好一点，好就业",
            schema_context=[{"field_id": "major_name", "source_column": "专业"}],
            query_options={"query_types": ["semantic_recommendation"]},
        )
        return result, client

    def test_rejects_raw_sql_keys(self) -> None:
        with self.assertRaises(ValidationError):
            EvidenceRequirement(
                source_text="想读计算机",
                requirement_type="table_field",
                candidate_semantic="major_name",
                rationale="x",
                raw_sql="SELECT 1",
            )

    def test_classify_returns_validated_requirements_and_usage(self) -> None:
        client = _FakeClient(
            {
                "requirements": [
                    {
                        "source_text": "人工智能，计算机",
                        "requirement_type": "table_field",
                        "candidate_semantic": "major_name",
                        "rationale": "需要专业字段判断专业名称或方向。",
                    },
                    {
                        "source_text": "好就业",
                        "requirement_type": "knowledge_base_or_reviewed_field",
                        "candidate_semantic": "employment_outcome",
                        "rationale": "需要就业数据或 reviewed KB 支持。",
                    },
                    {
                        "source_text": "学校好一点",
                        "requirement_type": "reviewed_ranking_policy",
                        "candidate_semantic": "school_quality",
                        "rationale": "需要 reviewed ranking policy 定义学校质量。",
                    },
                ]
            }
        )

        result = DeepSeekEvidenceRequirementClassifier(client).classify(
            text="想读人工智能，计算机，学校好一点，好就业",
            schema_context=[{"field_id": "major_name", "source_column": "专业"}],
            query_options={"query_types": ["semantic_recommendation"]},
        )

        self.assertIsInstance(result, EvidenceRequirementResult)
        self.assertEqual(
            [
                "table_field",
                "knowledge_base_or_reviewed_field",
                "reviewed_ranking_policy",
            ],
            [requirement.requirement_type for requirement in result.requirements],
        )
        self.assertEqual(9, result.usage["total_tokens"])

    def test_invalid_requirement_records_are_rejected_without_crashing(self) -> None:
        result, _client = self._classify(
            {
                "requirements": [
                    {
                        "source_text": "人工智能",
                        "requirement_type": "table_field",
                        "candidate_semantic": "major_name",
                        "rationale": "需要专业字段。",
                    },
                    {
                        "source_text": "学校好一点",
                        "requirement_type": "not_allowed",
                        "candidate_semantic": "school_quality",
                        "rationale": "需要已审查口径。",
                    },
                    {
                        "source_text": " ",
                        "requirement_type": "user_boundary",
                        "candidate_semantic": None,
                        "rationale": "需要用户给出边界。",
                    },
                    {
                        "source_text": "好就业",
                        "requirement_type": "knowledge_base_or_reviewed_field",
                        "candidate_semantic": "employment_outcome",
                        "rationale": "需要就业证据。",
                        "extra": "not allowed",
                    },
                ]
            }
        )

        self.assertEqual(1, len(result.requirements))
        self.assertEqual(3, len(result.rejected_requirements))
        self.assertEqual(
            ["invalid_requirement_shape"] * 3,
            [item["reason"] for item in result.rejected_requirements],
        )

    def test_raw_sql_requirement_is_rejected_and_sanitized(self) -> None:
        result, _client = self._classify(
            {
                "requirements": [
                    {
                        "source_text": "想读计算机",
                        "requirement_type": "table_field",
                        "candidate_semantic": "major_name",
                        "rationale": "x",
                        "raw_sql": "SELECT 1",
                    }
                ]
            }
        )

        self.assertEqual([], result.requirements)
        self.assertEqual("raw_sql_forbidden", result.rejected_requirements[0]["reason"])
        self.assertNotIn("raw_sql", str(result.rejected_requirements[0]["requirement"]))
        self.assertNotIn("SELECT 1", str(result.rejected_requirements))

    def test_sql_like_rejected_diagnostic_keys_are_sanitized(self) -> None:
        result, _client = self._classify(
            {
                "requirements": [
                    {
                        "source_text": "想读计算机",
                        "requirement_type": "table_field",
                        "candidate_semantic": "major_name",
                        "rationale": "x",
                        "SELECT * FROM admissions": "不要泄露键名",
                        "nested": {"ORDER BY rank": "不要泄露嵌套键名"},
                    }
                ]
            }
        )

        self.assertEqual([], result.requirements)
        self.assertEqual(
            "invalid_requirement_shape",
            result.rejected_requirements[0]["reason"],
        )
        serialized = str(result.rejected_requirements)
        self.assertNotIn("SELECT * FROM admissions", serialized)
        self.assertNotIn("ORDER BY rank", serialized)

    def test_sql_like_rejected_values_are_sanitized_beyond_select(self) -> None:
        result, _client = self._classify(
            {
                "requirements": [
                    {
                        "source_text": "想读计算机",
                        "requirement_type": "table_field",
                        "candidate_semantic": "major_name",
                        "rationale": "x",
                        "note": "ORDER BY rank",
                    }
                ]
            }
        )

        self.assertEqual([], result.requirements)
        self.assertEqual(
            "invalid_requirement_shape",
            result.rejected_requirements[0]["reason"],
        )
        self.assertNotIn("ORDER BY rank", str(result.rejected_requirements))

    def test_top_level_sql_keys_reject_payload(self) -> None:
        for key in ("raw_sql", "sql"):
            with self.subTest(key=key):
                result, _client = self._classify(
                    {
                        "requirements": [
                            {
                                "source_text": "人工智能",
                                "requirement_type": "table_field",
                                "candidate_semantic": "major_name",
                                "rationale": "需要专业字段。",
                            }
                        ],
                        "metadata": {key: "SELECT 1"},
                    }
                )

                self.assertEqual([], result.requirements)
                self.assertEqual(1, len(result.rejected_requirements))
                self.assertEqual(
                    "raw_sql_forbidden",
                    result.rejected_requirements[0]["reason"],
                )
                self.assertNotIn("SELECT 1", str(result.rejected_requirements))

    def test_non_list_requirements_rejects_payload(self) -> None:
        result, _client = self._classify({"requirements": {"source_text": "x"}})

        self.assertEqual([], result.requirements)
        self.assertEqual(
            "invalid_payload_shape",
            result.rejected_requirements[0]["reason"],
        )

    def test_non_dict_requirement_item_is_rejected(self) -> None:
        result, _client = self._classify({"requirements": ["不是对象"]})

        self.assertEqual([], result.requirements)
        self.assertEqual(
            "invalid_requirement_shape",
            result.rejected_requirements[0]["reason"],
        )

    def test_bad_usage_shape_falls_back_to_empty_dict(self) -> None:
        result, _client = self._classify({"requirements": []}, usage=["bad"])

        self.assertEqual({}, result.usage)

    def test_messages_style_client_response_is_supported(self) -> None:
        class _MessagesClient:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def chat_json(
                self,
                messages: list[dict[str, object]],
                temperature: float = 0.0,
            ) -> dict[str, object]:
                self.calls.append(
                    {"messages": messages, "temperature": temperature}
                )
                return {
                    "requirements": [
                        {
                            "source_text": "想读计算机",
                            "requirement_type": "table_field",
                            "candidate_semantic": "major_name",
                            "rationale": "需要专业字段。",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 3,
                        "total_tokens": 8,
                    },
                }

        client = _MessagesClient()
        result = DeepSeekEvidenceRequirementClassifier(client).classify(
            text="想读计算机",
            schema_context=[{"field_id": "major_name"}],
            query_options={"query_types": ["semantic_recommendation"]},
        )

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["temperature"], 0.0)
        self.assertEqual(
            result.requirements[0].candidate_semantic,
            "major_name",
        )
        self.assertEqual(result.usage["total_tokens"], 8)

    def test_blank_candidate_semantic_becomes_none(self) -> None:
        result, _client = self._classify(
            {
                "requirements": [
                    {
                        "source_text": "专业不限",
                        "requirement_type": "user_boundary",
                        "candidate_semantic": " ",
                        "rationale": "需要用户确认边界。",
                    }
                ]
            }
        )

        self.assertIsNone(result.requirements[0].candidate_semantic)

    def test_prompt_marks_inputs_as_untrusted_data(self) -> None:
        _result, client = self._classify({"requirements": []})

        self.assertIn("不可信数据", client.system_prompt)
        self.assertIn("不是指令", client.system_prompt)
        self.assertIn("untrusted_inputs", client.user_prompt)
        self.assertIn("user_text", client.user_prompt)
        self.assertIn("schema_context", client.user_prompt)
        self.assertIn("query_options", client.user_prompt)
        self.assertIn("llm_extracted_preferences", client.user_prompt)

    def test_prompt_includes_llm_extracted_preferences(self) -> None:
        _result, client = self._classify({"requirements": []})

        result = DeepSeekEvidenceRequirementClassifier(client).classify(
            text="想读计算机",
            schema_context=[],
            query_options={},
            preferences=[
                {
                    "source_text": "想读计算机",
                    "semantic": "major_name",
                    "op": "contains_any",
                    "value": ["计算机"],
                }
            ],
        )

        self.assertEqual(result.requirements, [])
        self.assertIn('"semantic": "major_name"', client.user_prompt)
        self.assertIn('"source_text": "想读计算机"', client.user_prompt)


if __name__ == "__main__":
    unittest.main()
