"""Conservative deterministic extractor for MVP/eval inputs.

This is still a baseline extractor: it proposes slots and source phrases only.
It never decides final executability.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import cn2an

from src.domains import DomainConfig

DEFAULT_ALIAS_PATH = DomainConfig.load("admissions").value_aliases_path
NUMBER_TEXT_PATTERN = (
    r"\d+(?:\.\d+)?\s*(?:万|w|W)?|[零〇一二两三四五六七八九十百千万点]+"
)


@lru_cache(maxsize=4)
def _load_aliases(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class RegexExtractor:
    """Benchmark-compatible deterministic extractor using aliases and regex."""

    def __init__(self, alias_path: str | Path = DEFAULT_ALIAS_PATH) -> None:
        self.aliases = _load_aliases(str(alias_path))

    def extract(self, text: str) -> dict[str, Any]:
        user_rank = self._user_rank(text)
        subject_type = self._subject_type(text)
        reselected_subjects = self._reselected_subjects(text)
        preferred_cities = self._preferred_cities(text)
        major_exact_terms = self._major_exact_terms(text)
        major_abbreviation_candidate = self._major_abbreviation_candidate(text)
        if major_abbreviation_candidate:
            major_exact_terms = [
                term
                for term in major_exact_terms
                if term != "计算机"
            ]
        major_keyword = major_exact_terms[0] if major_exact_terms else None
        tuition_cap_yuan = self._tuition_cap_yuan(text)
        major_expansion_raw = major_abbreviation_candidate or self._major_expansion(text)
        cooperation_preference_raw = self._first_present(
            text,
            self.aliases["cooperation_terms"],
        )
        other_vague_preferences = [
            term
            for term in self.aliases["other_vague_terms"]
            if term in text
        ]

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
                "risk_preference_raw": self._first_present(
                    text,
                    self.aliases["risk_terms"],
                ),
                "tuition_preference_raw": (
                    None
                    if tuition_cap_yuan is not None
                    else self._first_present(text, self.aliases["tuition_terms"])
                ),
                "tuition_cap_yuan": tuition_cap_yuan,
                "major_expansion_raw": major_expansion_raw,
                "cooperation_preference_raw": cooperation_preference_raw,
                "overseas_preference_raw": self._first_present(
                    text,
                    self.aliases["overseas_avoidance_terms"],
                ),
                "school_ownership_preference_raw": self._first_present(
                    text,
                    self.aliases["ownership_terms"],
                ),
                "recommendation_request_raw": self._first_present(
                    text,
                    self.aliases["recommendation_terms"],
                ),
                "other_vague_preferences": other_vague_preferences,
            },
            "raw_sources": self._raw_sources(
                text=text,
                major_expansion_raw=major_expansion_raw,
                cooperation_preference_raw=cooperation_preference_raw,
                other_vague_preferences=other_vague_preferences,
            ),
            "raw_phrases": self._raw_phrases(text),
        }

    def _user_rank(self, text: str) -> int | None:
        pattern = re.compile(
            rf"(?:排位|位次|排名|省排|省排名|全省)\s*"
            rf"(?:约|大概|大约|差不多)?\s*({NUMBER_TEXT_PATTERN})\s*"
            rf"(?:名|左右)?"
        )
        match = pattern.search(text)
        if not match:
            return None
        return _parse_quantity(match.group(1))

    def _subject_type(self, text: str) -> str | None:
        for subject_type, aliases in self.aliases["subject_type_aliases"].items():
            if any(alias in text for alias in aliases):
                return subject_type
        return None

    def _major_exact_terms(self, text: str) -> list[str]:
        positions: dict[str, int] = {}
        for canonical, aliases in self.aliases["major_aliases"].items():
            indexes = [text.find(alias) for alias in aliases if text.find(alias) >= 0]
            if indexes:
                positions[canonical] = min(indexes)
        return sorted(positions, key=positions.get)

    def _preferred_cities(self, text: str) -> list[str]:
        cities: list[str] = []
        for alias, canonical_cities in self.aliases["city_group_aliases"].items():
            if alias in text:
                cities.extend(canonical_cities)
        for canonical, aliases in self.aliases["city_aliases"].items():
            if any(alias in text for alias in aliases):
                cities.append(canonical)
        return _unique(cities)

    def _major_expansion(self, text: str) -> str | None:
        for term in self._major_source_terms(text):
            if f"{term}相关" in text:
                return f"{term}相关"
        if any(token in text for token in ["相关", "都可以", "或者", "、", "/", "互联网"]):
            return "相关专业"
        return None

    def _major_abbreviation_candidate(self, text: str) -> str | None:
        if "计科" in text and "计算机" not in text:
            return "计科"
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
        if any(term in text for term in ["广东考生", "广东省考生", "广东户籍"]):
            return "广东"
        return None

    def _preferred_school_provinces(self, text: str) -> list[str]:
        if self._first_present(text, self.aliases["school_province_terms"]):
            return ["广东"]
        return []

    def _reselected_subjects(self, text: str) -> list[str]:
        normalized = text.replace("思想政治", "政治").replace("生物学", "生物")
        subjects = []
        for subject, aliases in self.aliases["reselected_subject_aliases"].items():
            if any(
                alias in normalized
                for alias in aliases
                if len(alias) > 1
            ):
                subjects.append(subject)
        return _unique(subjects)[:2]

    def _raw_sources(
        self,
        text: str,
        major_expansion_raw: str | None,
        cooperation_preference_raw: str | None,
        other_vague_preferences: list[str],
    ) -> dict[str, Any]:
        sources: dict[str, Any] = {}
        major_sources = self._major_source_terms(text)
        if major_sources:
            sources["preferences.major_exact_terms"] = major_sources
            sources["preferences.major_keyword"] = major_sources[0]
        city_sources = self._city_source_terms(text)
        if city_sources:
            sources["preferences.preferred_cities"] = city_sources
        reselected_sources = self._reselected_subject_source_terms(text)
        if reselected_sources:
            sources["user_context.reselected_subjects"] = reselected_sources
        if major_expansion_raw:
            sources["preferences.major_expansion_raw"] = major_expansion_raw
        if cooperation_preference_raw:
            sources["preferences.cooperation_preference_raw"] = cooperation_preference_raw
        if other_vague_preferences:
            sources["preferences.other_vague_preferences"] = other_vague_preferences
        return sources

    def _major_source_terms(self, text: str) -> list[str]:
        positions: dict[str, tuple[int, str]] = {}
        for canonical, aliases in self.aliases["major_aliases"].items():
            matches = [
                (text.find(alias), alias)
                for alias in aliases
                if text.find(alias) >= 0
            ]
            if matches:
                positions[canonical] = min(matches)
        return [
            alias
            for _, alias in sorted(positions.values(), key=lambda item: item[0])
        ]

    def _city_source_terms(self, text: str) -> list[str]:
        sources = [
            alias
            for alias in self.aliases["city_group_aliases"]
            if alias in text
        ]
        for aliases in self.aliases["city_aliases"].values():
            matches = [alias for alias in aliases if alias in text]
            if matches:
                sources.append(matches[0])
        return _unique(sources)

    def _reselected_subject_source_terms(self, text: str) -> list[str]:
        bundles = ["物化生", "物化地", "物政地", "物生地", "史政地", "史化生"]
        matches = [bundle for bundle in bundles if bundle in text]
        if matches:
            return matches[:1]
        normalized = text.replace("思想政治", "政治").replace("生物学", "生物")
        sources = []
        for aliases in self.aliases["reselected_subject_aliases"].values():
            for alias in aliases:
                if len(alias) > 1 and alias in normalized:
                    sources.append(alias)
                    break
        return _unique(sources)

    def _tuition_cap_yuan(self, text: str) -> int | None:
        patterns = [
            rf"(?:不考虑|不要|不想要)?(?:学费|费用|预算)[^，。,.；;]{{0,12}}?"
            rf"(?:超过|高于|大于)\s*({NUMBER_TEXT_PATTERN})",
            rf"(?:学费|费用|预算)[^，。,.；;]{{0,12}}?"
            rf"({NUMBER_TEXT_PATTERN})\s*(?:元|块)?\s*(?:以内|以下|内)",
            rf"({NUMBER_TEXT_PATTERN})\s*(?:元|块)?\s*(?:以内|以下|内)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            parsed = _parse_quantity(match.group(1))
            if parsed is not None:
                return parsed
        return None

    def _raw_phrases(self, text: str) -> list[str]:
        phrases = []
        rank_match = re.search(
            rf"(?:排位|位次|排名|省排|省排名|全省)\s*(?:约|大概|大约|差不多)?"
            rf"\s*{NUMBER_TEXT_PATTERN}\s*(?:名|左右)?",
            text,
        )
        if rank_match:
            phrases.append(rank_match.group(0))
        for section in [
            "risk_terms",
            "tuition_terms",
            "cooperation_terms",
            "overseas_avoidance_terms",
            "ownership_terms",
            "recommendation_terms",
            "other_vague_terms",
        ]:
            phrases.extend(term for term in self.aliases[section] if term in text)
        for aliases_by_value in [
            self.aliases["city_aliases"],
            self.aliases["major_aliases"],
            self.aliases["subject_type_aliases"],
        ]:
            for aliases in aliases_by_value.values():
                phrases.extend(alias for alias in aliases if alias in text)
        phrases.extend(
            alias
            for alias in self.aliases["city_group_aliases"]
            if alias in text
        )
        return _unique(phrases)


def _parse_quantity(value: str) -> int | None:
    text = (
        value.strip()
        .replace(",", "")
        .replace("，", "")
        .replace("W", "万")
        .replace("w", "万")
    )
    text = re.sub(r"(?:名|元|块|左右|以内|以下|内|的)$", "", text)
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return int(float(text))
    try:
        parsed = cn2an.cn2an(text, "smart")
    except (ValueError, KeyError):
        return None
    return int(parsed)


def _unique(values: list[str]) -> list[str]:
    output = []
    for value in values:
        if value not in output:
            output.append(value)
    return output
