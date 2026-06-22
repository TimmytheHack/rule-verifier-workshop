from __future__ import annotations

import unittest
from dataclasses import dataclass

from src.semantic.evidence_bounded_reranker import EvidenceBoundedReranker
from src.semantic.intent_models import SemanticIntent, SemanticUserContext


@dataclass(frozen=True)
class _FakeResponse:
    payload: dict
    usage: dict | None = None


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.system_prompt = ""
        self.user_prompt = ""

    def chat_json(self, system_prompt: str, user_prompt: str) -> _FakeResponse:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return _FakeResponse(payload=self.payload)


class EvidenceBoundedRerankerTest(unittest.TestCase):
    def test_prompt_contains_only_bounded_candidate_fields(self) -> None:
        client = _FakeClient(
            {
                "items": [
                    {
                        "row_id": "candidate_001",
                        "bucket": "reach",
                        "reason_codes": ["rank_distance"],
                    }
                ]
            }
        )
        payload = EvidenceBoundedReranker(client).rerank(
            intent=SemanticIntent(
                query_type="semantic_recommendation",
                user_context=SemanticUserContext(user_rank=15000),
            ),
            candidates=[
                {
                    "row_id": "candidate_001",
                    "bucket": "reach",
                    "院校名称": "深圳大学",
                    "专业": "计算机科学与技术",
                    "最低录取排名": 14900,
                    "raw_excel_row": {"不应进入提示词": True},
                }
            ],
            quotas={"reach": 1, "match": 1, "safety": 1},
        )

        self.assertEqual(payload["items"][0]["row_id"], "candidate_001")
        self.assertIn("allowed_reason_codes", client.user_prompt)
        self.assertIn("candidate_001", client.user_prompt)
        self.assertIn("rank_distance", client.user_prompt)
        self.assertNotIn("raw_excel_row", client.user_prompt)
        self.assertNotIn("不应进入提示词", client.user_prompt)
        self.assertIn("不能生成 SQL", client.system_prompt)


if __name__ == "__main__":
    unittest.main()
