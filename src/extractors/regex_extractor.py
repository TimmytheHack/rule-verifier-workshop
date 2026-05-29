"""Conservative regex extractor for MVP/eval inputs.

This is intentionally not an LLM extractor. It extracts obvious facts and keeps
vague text as raw preferences; it does not decide final executability.
"""

from __future__ import annotations

import re
from typing import Any


class RegexExtractor:
    """Extracts the known MVP slots with conservative regex/string rules."""

    def extract(self, text: str) -> dict[str, Any]:
        rank_match = re.search(r"排位\s*(\d+)", text)
        user_rank = int(rank_match.group(1)) if rank_match else None
        subject_type = "物理" if "物理" in text else None
        if "历史" in text:
            subject_type = "历史"

        preferred_cities = [city for city in ["广州", "深圳"] if city in text]
        major_keyword = self._major_keyword(text)

        return {
            "input": text,
            "user_context": {
                "source_province": "广东" if "广东" in text else None,
                "subject_type": subject_type,
                "user_rank": user_rank,
            },
            "preferences": {
                "major_keyword": major_keyword,
                "preferred_cities": preferred_cities,
                "risk_preference_raw": self._first_present(text, ["稳一点", "冲一冲", "学校好一点", "学校别太差"]),
                "tuition_preference_raw": self._first_present(text, ["太贵", "费用别太高"]),
                "major_expansion_raw": "计算机相关扩展" if "相关" in text else None,
                "cooperation_preference_raw": self._first_present(text, ["不想去太贵的中外合作", "不要中外合作", "中外合作"]),
                "other_vague_preferences": [
                    term for term in ["就业前景好", "离家近一点", "学校别太差", "一线城市"] if term in text
                ],
            },
            "raw_phrases": self._raw_phrases(text),
        }

    def _major_keyword(self, text: str) -> str | None:
        for keyword in ["计算机", "软件工程", "法学"]:
            if keyword in text:
                return keyword
        return None

    def _first_present(self, text: str, candidates: list[str]) -> str | None:
        for candidate in candidates:
            if candidate in text:
                return candidate
        return None

    def _raw_phrases(self, text: str) -> list[str]:
        phrases = []
        for candidate in [
            "广东物理类",
            "广东历史类",
            "广东物理",
            "广东历史",
            "物理类",
            "历史类",
            "排位32000",
            "排位50000",
            "排位20000",
            "排位45000",
            "排位60000",
            "排位35000",
            "排位40000",
            "排位30000",
            "想学计算机",
            "想读法学",
            "软件工程",
            "最好在广州深圳",
            "只看广州",
            "深圳",
            "学校稳一点",
            "学校好一点",
            "冲一冲",
            "不想太贵",
            "费用别太高",
            "不要中外合作",
            "不想去太贵的中外合作",
            "就业前景好",
            "离家近一点",
            "学校别太差",
            "一线城市",
        ]:
            if candidate in text:
                phrases.append(candidate)
        return phrases
