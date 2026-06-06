from __future__ import annotations

import unittest

from scripts.run_answer_demo import compare_answers
from src.evaluation.scoring import score_answer_against_evidence
from src.extractors.deepseek_extractor import DeepSeekJSONResponse
from src.reporting.deepseek_answer_generator import DeepSeekAnswerGenerator
from src.reporting.evidence_pack import EvidencePack
from src.reporting.template_report_builder import TemplateReportBuilder
from src.schema.schema_registry import SchemaRegistry


class FakeDeepSeekClient:
    def __init__(self) -> None:
        self.last_system_prompt = ""
        self.last_user_prompt = ""

    def chat_json(self, system_prompt: str, user_prompt: str) -> DeepSeekJSONResponse:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        return DeepSeekJSONResponse(
            payload={
                "answer": "共筛选到 1 条结果。中外合作：未执行，未参与筛选。"
            },
            usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        )


def sample_evidence() -> EvidencePack:
    return EvidencePack(
        user_request=(
            "我是广东物理类，排位32000，想学计算机，"
            "不想去太贵的中外合作。"
        ),
        executed_rules=[
            {
                "rule_id": "e_source_province",
                "field": "生源地",
                "operator": "eq",
                "value": "广东",
                "description": "生源地 == 广东",
            },
            {
                "rule_id": "e_city",
                "field": "城市",
                "operator": "in_contains",
                "value": ["广州", "深圳"],
                "description": "城市 包含任一：广州、深圳",
            },
            {
                "rule_id": "e_tuition_cap",
                "field": "学费",
                "operator": "<=",
                "value": 20000,
                "description": "学费 <= 20000",
            },
        ],
        candidate_confirmations=[
            {
                "confirmation_id": "tuition_threshold",
                "source_text": "太贵",
                "selected_label": "<= 20000 元/年",
                "status": "promoted_to_executed_rule",
                "description": "学费 <= 20000",
            },
            {
                "confirmation_id": "cooperation_type",
                "source_text": "不想去太贵的中外合作",
                "status": "not_executable",
                "reason": "Missing dedicated cooperation_type field.",
            },
        ],
        not_executed_preferences=[
            {
                "source_text": "不想去太贵的中外合作",
                "status": "not_executed",
                "reason": "Missing dedicated cooperation_type field.",
                "safety_warning": (
                    "不想去太贵的中外合作 未执行："
                    "Missing dedicated cooperation_type field."
                ),
            }
        ],
        result_count=1,
        top_k_results=[
            {
                "rank": 1,
                "院校名称": "深圳大学",
                "院校专业组代码": "10590251",
                "专业名称": "计算机类",
                "城市": "深圳",
                "学费": 6853.0,
                "专业组最低位次": 38998,
                "专业最低位次": 15214,
                "safety_margin": "21.87%",
                "trace": [],
            }
        ],
        trace_summary={
            "executed_rule_ids": ["e_source_province", "e_city", "e_tuition_cap"],
            "safety_warnings": [
                "候选偏好在确认或模拟确认之前不得执行。",
                (
                    "不想去太贵的中外合作 未执行："
                    "Missing dedicated cooperation_type field."
                ),
            ],
        },
    )


class AnswerReportingTest(unittest.TestCase):
    def test_template_answer_is_fully_evidence_aligned(self) -> None:
        evidence = sample_evidence().to_dict()
        answer = TemplateReportBuilder().build(evidence)
        score = score_answer_against_evidence(answer, evidence)

        self.assertIn("共筛选到 1 条", answer)
        self.assertIn("未执行，未参与筛选", answer)
        self.assertEqual(score["task_success_score"], score["max_score"])

    def test_answer_evaluator_flags_unsupported_claims(self) -> None:
        evidence = sample_evidence().to_dict()
        answer = (
            TemplateReportBuilder().build(evidence)
            + "\n系统已过滤中外合作，并判断就业前景好。"
            + "以上均为非中外合作办学，录取希望大，非常稳妥。"
        )
        score = score_answer_against_evidence(answer, evidence)

        self.assertFalse(score["score_parts"]["no_unsupported_claims"])
        self.assertIn("已过滤中外合作", score["details"]["unsupported_claims"])
        self.assertIn("就业前景好", score["details"]["unsupported_claims"])
        self.assertIn("非中外合作", score["details"]["unsupported_claims"])
        self.assertIn("录取希望", score["details"]["unsupported_claims"])
        self.assertIn("非常稳妥", score["details"]["unsupported_claims"])

    def test_deepseek_answer_generator_prompt_accepts_only_evidence_pack(self) -> None:
        fake_client = FakeDeepSeekClient()
        result = DeepSeekAnswerGenerator(client=fake_client).generate(sample_evidence())
        evidence = sample_evidence().to_dict()
        score = score_answer_against_evidence(result["answer"], evidence)

        self.assertEqual(result["deepseek_usage"]["total_tokens"], 3)
        self.assertIn("Use only the supplied evidence_pack", fake_client.last_system_prompt)
        self.assertIn("professional group code", fake_client.last_system_prompt)
        self.assertIn("not_executed_preferences", fake_client.last_user_prompt)
        self.assertIn("院校专业组代码", fake_client.last_user_prompt)
        self.assertIn("不想去太贵的中外合作", fake_client.last_user_prompt)
        self.assertNotIn("ExcelAdapter", fake_client.last_user_prompt)
        self.assertIn("证据覆盖清单", result["answer"])
        self.assertIn("院校专业组代码：10590251", result["answer"])
        self.assertEqual(score["task_success_score"], score["max_score"])

    def test_compare_answers_skips_deepseek_when_not_requested(self) -> None:
        registry = SchemaRegistry(active_fields={}, configured_fields={})
        comparison = compare_answers(
            evidence=sample_evidence(),
            schema_registry=registry,
            include_deepseek=False,
        )

        self.assertEqual(comparison["pipeline_template"]["status"], "ok")
        self.assertEqual(comparison["llm_only_schema_sample"]["status"], "skipped")
        self.assertEqual(comparison["pipeline_deepseek_evidence"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
