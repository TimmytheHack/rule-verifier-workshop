"""Conservative regex extractor for MVP/eval inputs.

This is a benchmark baseline, not the final extraction strategy. It extracts
obvious facts and keeps vague text as raw preferences; it does not decide final
executability.
"""

from __future__ import annotations

import re
from typing import Any


class RegexExtractor:
    """Benchmark-only extractor using conservative regex/string rules."""

    CITY_TERMS = ["广州", "深圳", "佛山", "东莞", "珠海", "惠州", "汕头", "中山"]
    MAJOR_TERMS = [
        "计算机",
        "软件工程",
        "人工智能",
        "网络安全",
        "自动化",
        "新闻传播",
        "数据科学",
        "网络空间安全",
        "电子信息",
        "法学",
        "会计",
        "金融",
        "临床医学",
        "汉语言文学",
    ]
    RISK_TERMS = [
        "稳一点",
        "稳妥一点",
        "稳妥",
        "保守一点",
        "不想太冒险",
        "学校好一点",
        "学校别太差",
        "冲一冲",
        "想冲",
        "保底",
    ]
    TUITION_TERMS = ["太贵", "不要太贵", "不想太贵", "费用别太高", "费用低一点", "学费低", "学费低一点", "两万以内", "便宜点", "预算有限"]
    COOPERATION_TERMS = ["不想去太贵的中外合作", "不要中外合作", "不考虑中外合作", "中外合作"]
    OWNERSHIP_TERMS = ["公办本科", "优先公办", "公办", "民办"]
    OTHER_VAGUE_TERMS = [
        "录取概率高",
        "排名靠前",
        "口碑好",
        "城市不限",
        "珠三角",
        "偏远",
        "太偏远",
        "城市不要太差",
        "公办本科",
        "优先公办",
        "公办",
        "专业不要太冷门",
        "冷门",
        "学校尽量好一点",
        "好学校",
        "学校名气",
        "名气重要",
        "就业前景好",
        "好就业",
        "离家近一点",
        "离家近",
        "学校别太差",
        "一线城市",
        "大城市",
        "发达城市",
        "学校好一点",
    ]

    def extract(self, text: str) -> dict[str, Any]:
        rank_match = re.search(r"排位\s*(\d+)", text)
        user_rank = int(rank_match.group(1)) if rank_match else None
        subject_type = "物理" if "物理" in text else None
        if "历史" in text:
            subject_type = "历史"

        preferred_cities = [city for city in self.CITY_TERMS if city in text]
        major_exact_terms = self._major_exact_terms(text)
        major_keyword = major_exact_terms[0] if major_exact_terms else None

        return {
            "input": text,
            "user_context": {
                "source_province": "广东" if "广东" in text else None,
                "subject_type": subject_type,
                "user_rank": user_rank,
            },
            "preferences": {
                "major_keyword": major_keyword,
                "major_exact_terms": major_exact_terms,
                "preferred_cities": preferred_cities,
                "risk_preference_raw": self._first_present(text, self.RISK_TERMS),
                "tuition_preference_raw": self._first_present(text, self.TUITION_TERMS),
                "major_expansion_raw": self._major_expansion(text),
                "cooperation_preference_raw": self._first_present(text, self.COOPERATION_TERMS),
                "school_ownership_preference_raw": self._first_present(text, self.OWNERSHIP_TERMS),
                "other_vague_preferences": [
                    term for term in self.OTHER_VAGUE_TERMS if term in text
                ],
            },
            "raw_phrases": self._raw_phrases(text),
        }

    def _major_keyword(self, text: str) -> str | None:
        terms = self._major_exact_terms(text)
        return terms[0] if terms else None

    def _major_exact_terms(self, text: str) -> list[str]:
        found = [keyword for keyword in self.MAJOR_TERMS if keyword in text]
        return sorted(found, key=text.find)

    def _major_expansion(self, text: str) -> str | None:
        if "相关" in text or "都可以" in text or "或者" in text or "、" in text:
            return "语义扩展待确认"
        return None

    def _first_present(self, text: str, candidates: list[str]) -> str | None:
        for candidate in candidates:
            if candidate in text:
                return candidate
        return None

    def _raw_phrases(self, text: str) -> list[str]:
        phrases = []
        rank_match = re.search(r"排位\s*\d+", text)
        if rank_match:
            phrases.append(rank_match.group(0))
        for candidate in [
            "广东物理类",
            "广东历史类",
            "广东物理",
            "广东历史",
            "物理类",
            "历史类",
            "想学计算机",
            "想读法学",
            "软件工程",
            "最好在广州深圳",
            "只看广州",
            "深圳",
            "学校稳一点",
            "稳妥一点",
            "稳妥",
            "保守一点",
            "学校好一点",
            "学校尽量好一点",
            "冲一冲",
            "想冲",
            "不想太冒险",
            "都可以",
            "保底",
            "不要太贵",
            "不想太贵",
            "费用别太高",
            "费用低一点",
            "学费低",
            "学费低一点",
            "两万以内",
            "预算有限",
            "不要中外合作",
            "不考虑中外合作",
            "不想去太贵的中外合作",
            "就业前景好",
            "好就业",
            "离家近一点",
            "学校别太差",
            "一线城市",
            "大城市",
            "发达城市",
            "录取概率高",
            "排名靠前",
            "口碑好",
            "城市不限",
            "珠三角",
            "偏远",
            "太偏远",
            "城市不要太差",
            "公办本科",
            "优先公办",
            "公办",
            "专业不要太冷门",
            "冷门",
            "学校尽量好一点",
            "好学校",
            "学校名气",
            "名气重要",
            "新闻传播",
            "网络安全",
            "自动化",
        ]:
            if candidate in text:
                phrases.append(candidate)
        return phrases
