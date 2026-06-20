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
                "description": "生源地 等于 广东",
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
                "description": "学费 不高于 20000",
            },
        ],
        candidate_confirmations=[
            {
                "confirmation_id": "tuition_threshold",
                "source_text": "太贵",
                "selected_label": "不高于 20000 元/年",
                "status": "promoted_to_executed_rule",
                "description": "学费 不高于 20000",
            },
            {
                "confirmation_id": "cooperation_type",
                "source_text": "不想去太贵的中外合作",
                "status": "not_executable",
                "reason": "缺少合作办学类型字段。",
            },
        ],
        not_executed_preferences=[
            {
                "source_text": "不想去太贵的中外合作",
                "status": "not_executed",
                "reason": "缺少合作办学类型字段。",
                "safety_warning": (
                    "不想去太贵的中外合作 未执行："
                    "缺少合作办学类型字段。"
                ),
            }
        ],
        result_count=1,
        top_k_results=[
            {
                "rank": 1,
                "院校名称": "深圳大学",
                "院校专业组代码": "10590251",
                "专业代码": "353",
                "专业名称": "计算机类",
                "专业全称": "计算机类(含：计算机科学与技术、软件工程)",
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
                    "缺少合作办学类型字段。"
                ),
            ],
        },
        execution_summary={
            "executor": "duckdb",
            "sql": "SELECT * FROM admissions WHERE 城市 = ?",
            "params": ["深圳"],
            "input_row_count": 10,
            "filtered_row_count": 1,
            "sort_key": ["专业组最低位次1 ASC NULLS LAST"],
            "top_k": 5,
        },
    )


def sample_decision_guidance() -> dict[str, object]:
    return {
        "status": "reference_only",
        "execution_effect": "does_not_change_sql_or_results",
        "executable": False,
        "matched_rules": [
            {
                "rule_id": "career_no_family_resource_goal",
                "label": "家里缺少就业资源时先明确就业目标",
                "effect": "does_not_change_sql_or_results",
            }
        ],
        "information_requests": [
            {
                "question_id": "q_employment_goal",
                "label": "就业目标",
                "question": "请先选择更看重的就业目标。",
                "fixed_options": ["稳定就业", "体制内/考公考编"],
                "reason": "不能把好就业直接翻译成筛选条件。",
            }
        ],
        "no_schema_field_preferences": [
            {
                "source_text": "好就业",
                "field_id": "employment_outlook",
                "field": "就业结果字段",
                "reason": "当前数据中没有已审查就业结果字段。",
            }
        ],
    }


class AnswerReportingTest(unittest.TestCase):
    def test_template_answer_is_fully_evidence_aligned(self) -> None:
        evidence = sample_evidence().to_dict()
        answer = TemplateReportBuilder().build(evidence)
        score = score_answer_against_evidence(answer, evidence)

        self.assertIn("共筛选到 1 条", answer)
        self.assertIn("未执行，未参与筛选", answer)
        self.assertEqual(score["task_success_score"], score["max_score"])

    def test_template_answer_displays_career_guidance_as_reference_only(self) -> None:
        evidence = sample_evidence().to_dict()
        evidence["decision_guidance"] = sample_decision_guidance()
        answer = TemplateReportBuilder().build(evidence)

        self.assertIn("就业与家庭资源说明（不参与筛选）", answer)
        self.assertIn("家里缺少就业资源时先明确就业目标", answer)
        self.assertIn("不改变 SQL、不改变结果数量", answer)
        self.assertIn("固定选项：稳定就业、体制内/考公考编", answer)

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
        self.assertIn("只能使用传入的证据包", fake_client.last_system_prompt)
        self.assertIn("院校专业组代码", fake_client.last_system_prompt)
        self.assertIn("not_executed_preferences", fake_client.last_user_prompt)
        self.assertIn("院校专业组代码", fake_client.last_user_prompt)
        self.assertIn("不想去太贵的中外合作", fake_client.last_user_prompt)
        self.assertIn("decision_guidance 只能解释和追问", fake_client.last_user_prompt)
        self.assertNotIn("ExcelAdapter", fake_client.last_user_prompt)
        self.assertIn("证据覆盖清单", result["answer"])
        self.assertIn("院校专业组代码：10590251", result["answer"])
        self.assertIn("专业代码：353", result["answer"])
        self.assertIn("专业全称：计算机类", result["answer"])
        self.assertEqual(score["task_success_score"], score["max_score"])

    def test_deepseek_coverage_appendix_lists_decision_guidance(self) -> None:
        fake_client = FakeDeepSeekClient()
        evidence = sample_evidence().to_dict()
        evidence["decision_guidance"] = sample_decision_guidance()
        result = DeepSeekAnswerGenerator(client=fake_client).generate(evidence)

        self.assertIn("decision_guidance", fake_client.last_user_prompt)
        self.assertIn("不得改变 SQL、结果数或 executed_rules", fake_client.last_user_prompt)
        self.assertIn("就业与家庭资源说明（不参与筛选）", result["answer"])
        self.assertIn("不改变 SQL、不改变结果数量", result["answer"])
        self.assertIn("需要补充：就业目标", result["answer"])

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

    def test_evidence_pack_records_executor_audit(self) -> None:
        evidence = sample_evidence().to_dict()
        execution = evidence["execution_summary"]

        self.assertEqual(execution["executor"], "duckdb")
        self.assertEqual(execution["sql"], "SELECT * FROM admissions WHERE 城市 = ?")
        self.assertEqual(execution["params"], ["深圳"])
        self.assertEqual(execution["input_row_count"], 10)
        self.assertEqual(execution["filtered_row_count"], 1)
        self.assertEqual(execution["sort_key"], ["专业组最低位次1 ASC NULLS LAST"])
        self.assertEqual(execution["top_k"], 5)

    def test_skipped_soft_confirmation_is_not_reported_as_executed(self) -> None:
        evidence = EvidencePack.from_verified_pipeline(
            user_request="广东物理，预算有限。",
            executed_rules=[],
            classified_rules={
                "candidate_rules": [
                    {
                        "rule_id": "c_tuition_cap",
                        "source_text": "预算有限",
                    }
                ],
                "confirmation_questions": [],
                "simulated_confirmations": {
                    "tuition_threshold": {
                        "label": "不高于 20000 元/年",
                        "selected_option": "20000",
                        "field": "学费",
                        "operator": "<=",
                        "value": 20000,
                    }
                },
                "non_executable_preferences": [],
                "llm_needed_parts": [],
            },
            traced_results=[],
            execution_summary={
                "executor": "duckdb",
                "sql": "SELECT * FROM admissions",
                "params": [],
                "input_row_count": 1,
                "filtered_row_count": 1,
                "sort_key": [],
                "top_k": 5,
                "skipped_soft_rule_ids": ["e_tuition_cap"],
            },
        )

        payload = evidence.to_dict()
        self.assertEqual(
            payload["candidate_confirmations"][0]["status"],
            "confirmed_not_hard_filter",
        )
        self.assertIn("未进入 hard filter", TemplateReportBuilder().build(payload))


if __name__ == "__main__":
    unittest.main()
