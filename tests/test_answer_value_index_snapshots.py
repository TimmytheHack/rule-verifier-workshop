from __future__ import annotations

import unittest

from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import run_workbench_with_test_warehouse


def _run_regex_workbench(prompt: str) -> dict[str, object]:
    return run_workbench_with_test_warehouse(
        WorkbenchConfig(
            user_input=prompt,
            extractor="regex",
            soft_preferences={"prompt": prompt},
        )
    )


def _attribute_section(result: dict[str, object]) -> str:
    report = result["natural_language_report"]
    assert isinstance(report, dict)
    text = str(report["full_text"])
    return (
        text.split("字段值审计解释：\n", 1)[1]
        .split("\n\n已执行规则：", 1)[0]
        .strip()
    )


class AnswerValueIndexSnapshotTest(unittest.TestCase):
    def test_exact_match_snapshot_for_aliases_and_subject_bundle(self) -> None:
        result = _run_regex_workbench(
            "广东物理，物化生，排位32000，想学计科，广深优先。"
        )

        self.assertEqual(
            _attribute_section(result),
            "\n".join(
                [
                    "- [已执行] 广东 -> 生源地：exact_match；索引命中：广东；已匹配字段“生源地”，并已进入 hard filter。",
                    "- [已执行] 物理 -> 科类：exact_match；索引命中：物理；已匹配字段“科类”，并已进入 hard filter。",
                    "- [已执行] 物化生 -> 选科要求：exact_match；索引命中：化学、生物；已匹配字段“选科要求”，并已进入 hard filter。",
                    "- [已执行] 广深 -> 城市：exact_match；索引命中：广州、深圳；已匹配字段“城市”，并已进入 hard filter。",
                    "- [需确认] 计科 -> 专业名称：partial_match；该属性有对应字段，但语义或边界需要确认。未进入 hard filter。",
                ]
            ),
        )
        self.assertEqual(
            result["execution"]["hard_rule_ids"],
            [
                "e_source_province",
                "e_subject_type",
                "e_subject_requirement",
                "e_city",
            ],
        )

    def test_partial_and_no_schema_snapshot_for_related_major_and_cooperation(self) -> None:
        result = _run_regex_workbench(
            "广东物理，排位32000，计算机相关，珠三角优先，不要校企合作。"
        )

        self.assertEqual(
            _attribute_section(result),
            "\n".join(
                [
                    "- [已执行] 广东 -> 生源地：exact_match；索引命中：广东；已匹配字段“生源地”，并已进入 hard filter。",
                    "- [已执行] 物理 -> 科类：exact_match；索引命中：物理；已匹配字段“科类”，并已进入 hard filter。",
                    "- [已执行] 计算机 -> 专业名称：exact_match；索引命中：计算机类、计算机科学与技术、计算机应用技术、电子与计算机工程、计算机网络技术；已匹配字段“专业名称”，并已进入 hard filter。",
                    "- [需确认] 计算机相关 -> 专业名称：partial_match；该属性有对应字段，但语义或边界需要确认。未进入 hard filter。",
                    "- [未执行] 不要校企合作 -> 合作办学类型字段：no_schema_field；当前数据中没有可执行字段，不能进入筛表。原文已保留，未进入 hard filter。",
                    "- [需确认] 珠三角 -> 城市：partial_match；需要确认珠三角城市集合。未进入 hard filter。",
                ]
            ),
        )
        params = result["execution"]["params"]
        for blocked_value in ["计算机相关", "珠三角", "不要校企合作"]:
            self.assertNotIn(blocked_value, params)
        self.assertEqual(
            result["execution"]["hard_rule_ids"],
            ["e_source_province", "e_subject_type", "e_major_keyword"],
        )

    def test_no_schema_snapshot_preserves_zhongwai_cooperation_text(self) -> None:
        result = _run_regex_workbench(
            "广东物理，排位32000，想学计算机，不要中外合作。"
        )

        self.assertIn(
            "- [未执行] 不要中外合作 -> 合作办学类型字段：no_schema_field；"
            "当前数据中没有可执行字段，不能进入筛表。原文已保留，未进入 hard filter。",
            _attribute_section(result),
        )
        self.assertNotIn("不要中外合作", result["execution"]["params"])
        self.assertNotIn("中外合作", result["execution"]["params"])


if __name__ == "__main__":
    unittest.main()
