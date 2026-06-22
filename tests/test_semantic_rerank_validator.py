from __future__ import annotations

import unittest

from src.semantic.rerank_validator import RerankValidator


class RerankValidatorTest(unittest.TestCase):
    def test_accepts_candidate_row_ids_reason_codes_and_field_refs(self) -> None:
        result = RerankValidator().validate(
            {
                "items": [
                    {
                        "row_id": "candidate_002",
                        "bucket": "reach",
                        "reason_codes": ["rank_distance"],
                        "field_refs": ["最低录取排名"],
                    },
                    {
                        "row_id": "candidate_001",
                        "bucket": "reach",
                        "reason_codes": ["school_tier"],
                        "field_refs": ["是否985"],
                    },
                ]
            },
            candidates=_candidates(),
            quotas={"reach": 2, "match": 1, "safety": 1},
        )

        self.assertTrue(result.ok)
        self.assertFalse(result.fallback_used)
        self.assertEqual(
            [row["row_id"] for row in result.result_sections["reach"]],
            ["candidate_002", "candidate_001"],
        )
        self.assertEqual(
            result.result_sections["reach"][0]["rerank_reason_codes"],
            ["rank_distance"],
        )

    def test_unknown_row_id_falls_back_to_deterministic_candidate_order(self) -> None:
        result = RerankValidator().validate(
            {
                "items": [
                    {
                        "row_id": "outside_001",
                        "bucket": "reach",
                        "reason_codes": ["rank_distance"],
                    }
                ]
            },
            candidates=_candidates(),
            quotas={"reach": 2, "match": 1, "safety": 1},
        )

        self.assertFalse(result.ok)
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.issues[0]["code"], "unknown_row_id")
        self.assertEqual(
            [row["row_id"] for row in result.result_sections["reach"]],
            ["candidate_001", "candidate_002"],
        )

    def test_bucket_mismatch_reason_code_and_missing_field_are_rejected(self) -> None:
        result = RerankValidator().validate(
            {
                "items": [
                    {
                        "row_id": "candidate_001",
                        "bucket": "match",
                        "reason_codes": ["rank_distance"],
                    },
                    {
                        "row_id": "candidate_002",
                        "bucket": "reach",
                        "reason_codes": ["external_prestige"],
                    },
                    {
                        "row_id": "candidate_003",
                        "bucket": "match",
                        "reason_codes": ["rank_distance"],
                        "field_refs": ["就业质量"],
                    },
                ]
            },
            candidates=_candidates(),
            quotas={"reach": 2, "match": 1, "safety": 1},
        )

        self.assertFalse(result.ok)
        self.assertTrue(result.fallback_used)
        self.assertEqual(
            [issue["code"] for issue in result.issues],
            ["bucket_mismatch", "unsupported_reason_code", "missing_field_ref"],
        )


def _candidates() -> list[dict[str, object]]:
    return [
        {
            "row_id": "candidate_001",
            "bucket": "reach",
            "院校名称": "A 大学",
            "最低录取排名": 14600,
            "是否985": "是",
        },
        {
            "row_id": "candidate_002",
            "bucket": "reach",
            "院校名称": "B 大学",
            "最低录取排名": 14900,
            "是否985": "否",
        },
        {
            "row_id": "candidate_003",
            "bucket": "match",
            "院校名称": "C 大学",
            "最低录取排名": 21000,
            "是否985": "否",
        },
    ]


if __name__ == "__main__":
    unittest.main()
