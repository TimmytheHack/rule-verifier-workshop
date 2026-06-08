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
    SCHOOL_PROVINCE_TERMS = ["留在广东", "广东省内", "省内", "不出省", "不想出省", "留省内"]
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
        "数学",
    ]
    RISK_TERMS = [
        "稳一点",
        "稳妥一点",
        "稳妥",
        "保守一点",
        "不想太冒险",
        "冲一冲",
        "想冲",
        "保底",
    ]
    TUITION_TERMS = ["太贵", "不要太贵", "不想太贵", "费用别太高", "费用低一点", "学费低", "学费低一点", "便宜点", "预算有限"]
    COOPERATION_TERMS = ["不想去太贵的中外合作", "不要中外合作", "不考虑中外合作", "中外合作"]
    OVERSEAS_AVOIDANCE_TERMS = ["不想去国外", "不要国外", "不去国外", "不出国", "不想出国", "想留在国内"]
    OWNERSHIP_TERMS = ["公办本科", "优先公办", "公办", "民办"]
    RECOMMENDATION_TERMS = ["给出推荐", "请推荐", "推荐一下", "推荐"]
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
        reselected_subjects = self._reselected_subjects(text)

        preferred_cities = [city for city in self.CITY_TERMS if city in text]
        major_exact_terms = self._major_exact_terms(text)
        major_keyword = major_exact_terms[0] if major_exact_terms else None

        return {
            "input": text,
            "user_context": {
                "source_province": self._source_province(text),
                "subject_type": subject_type,
                "reselected_subjects": reselected_subjects,
                "user_rank": user_rank,
            },
            "preferences": {
                "major_keyword": major_keyword,
                "major_exact_terms": major_exact_terms,
                "preferred_cities": preferred_cities,
                "preferred_school_provinces": self._preferred_school_provinces(text),
                "risk_preference_raw": self._first_present(text, self.RISK_TERMS),
                "tuition_preference_raw": self._first_present(text, self.TUITION_TERMS),
                "tuition_cap_yuan": self._tuition_cap_yuan(text),
                "major_expansion_raw": self._major_expansion(text),
                "cooperation_preference_raw": self._first_present(text, self.COOPERATION_TERMS),
                "overseas_preference_raw": self._first_present(text, self.OVERSEAS_AVOIDANCE_TERMS),
                "school_ownership_preference_raw": self._first_present(text, self.OWNERSHIP_TERMS),
                "recommendation_request_raw": self._first_present(text, self.RECOMMENDATION_TERMS),
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

    def _source_province(self, text: str) -> str | None:
        if re.search(r"广东\s*(?:物理|历史)", text):
            return "广东"
        if re.search(r"(?:我是|本人|考生|生源地|户籍|来自)\s*广东", text):
            return "广东"
        if "广东考生" in text or "广东省考生" in text:
            return "广东"
        return None

    def _preferred_school_provinces(self, text: str) -> list[str]:
        if self._first_present(text, self.SCHOOL_PROVINCE_TERMS):
            return ["广东"]
        return []

    def _reselected_subjects(self, text: str) -> list[str]:
        normalized = text.replace("思想政治", "政治").replace("生物学", "生物")
        subjects = [subject for subject in ["化学", "生物", "政治", "地理"] if subject in normalized]
        return subjects[:2]

    def _tuition_cap_yuan(self, text: str) -> int | None:
        ten_thousand_match = re.search(r"(?:学费|费用|预算)?\s*([一二两三四五六七八九十\d.]+)\s*万\s*以内", text)
        if ten_thousand_match:
            value = self._parse_small_number(ten_thousand_match.group(1))
            return int(value * 10000) if value is not None else None

        yuan_match = re.search(r"(?:学费|费用|预算)\D{0,4}(\d{4,6})\s*(?:元)?\s*以内", text)
        if yuan_match:
            return int(yuan_match.group(1))
        return None

    def _parse_small_number(self, value: str) -> float | None:
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            return float(value)
        mapping = {
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }
        return float(mapping[value]) if value in mapping else None

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
            "广东省内",
            "留在广东省",
            "不出省",
            "想学计算机",
            "想读法学",
            "软件工程",
            "人工智能",
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
            "不想去国外",
            "不去国外",
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
            "数学",
            "数学系",
            "给出推荐",
            "请推荐",
        ]:
            if candidate in text:
                phrases.append(candidate)
        return phrases
