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
ARABIC_QUANTITY_PATTERN = r"(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?"
NUMBER_TEXT_PATTERN = (
    rf"{ARABIC_QUANTITY_PATTERN}\s*(?:万|w|W)?|[零〇一二两三四五六七八九十百千万点]+"
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
        family_resource_raw = self._family_resource_raw(text)
        employment_preference_raw = self._first_positive_present(
            text,
            self.aliases["employment_terms"],
        )
        career_goal_raw = self._career_goal_raw(text, family_resource_raw)
        other_vague_preferences = self._other_vague_preferences(
            text,
            family_resource_raw=family_resource_raw,
            dedicated_preferences=[
                employment_preference_raw,
                career_goal_raw,
            ],
        )

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
                "employment_preference_raw": employment_preference_raw,
                "family_resource_raw": family_resource_raw,
                "career_goal_raw": career_goal_raw,
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
                employment_preference_raw=employment_preference_raw,
                family_resource_raw=family_resource_raw,
                career_goal_raw=career_goal_raw,
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

    def _first_positive_present(self, text: str, candidates: list[str]) -> str | None:
        for candidate in candidates:
            if _positive_term_index(text, candidate) is not None:
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

    def _family_resource_raw(self, text: str) -> str | None:
        no_resource = self._first_present(text, self.aliases["no_family_resource_terms"])
        if no_resource:
            return no_resource
        return self._first_present(text, self.aliases["family_resource_terms"])

    def _career_goal_raw(
        self,
        text: str,
        family_resource_raw: str | None,
    ) -> str | None:
        search_text = text
        if family_resource_raw:
            search_text = search_text.replace(family_resource_raw, "", 1)

        matches = []
        intent_pattern = r"(?:想|希望|打算|考虑|计划|准备|目标(?:是)?|以后|将来)"
        for term in self.aliases["career_goal_terms"]:
            pattern = re.compile(
                rf"{intent_pattern}[^，。,.；;]{{0,8}}{re.escape(term)}"
            )
            match = pattern.search(search_text)
            if match:
                term_index = search_text.find(term, match.start(), match.end())
                if (
                    term_index >= 0
                    and _term_is_negated(search_text, term_index, len(term))
                ):
                    continue
                matches.append((match.start(), term))
        if not matches:
            return None
        return min(matches)[1]

    def _other_vague_preferences(
        self,
        text: str,
        family_resource_raw: str | None,
        dedicated_preferences: list[str | None],
    ) -> list[str]:
        dedicated_terms = {term for term in dedicated_preferences if term}
        return [
            term
            for term in self.aliases["other_vague_terms"]
            if term not in dedicated_terms
            and _positive_term_index(
                text,
                term,
                blocked_phrase=family_resource_raw,
            )
            is not None
        ]

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
        employment_preference_raw: str | None,
        family_resource_raw: str | None,
        career_goal_raw: str | None,
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
        if employment_preference_raw:
            sources["preferences.employment_preference_raw"] = employment_preference_raw
        if family_resource_raw:
            sources["preferences.family_resource_raw"] = family_resource_raw
        if career_goal_raw:
            sources["preferences.career_goal_raw"] = career_goal_raw
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
        re.sub(r"\s+", "", value.strip())
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


def _term_is_negated(
    text: str,
    term_index: int,
    term_length: int = 0,
) -> bool:
    clause_start = (
        max(text.rfind(punctuation, 0, term_index) for punctuation in "，。,.；;")
        + 1
    )
    suffix_start = term_index + term_length
    clause_ends = [
        text.find(punctuation, suffix_start)
        for punctuation in "，。,.；;"
        if text.find(punctuation, suffix_start) >= 0
    ]
    clause_end = min(clause_ends) if clause_ends else len(text)
    prefix = _prefix_after_boundary(text[clause_start:term_index])
    suffix = _suffix_before_boundary(text[suffix_start:clause_end])
    prefix_markers = [
        "不优先考虑",
        "不优先看重",
        "不优先选择",
        "不要求",
        "不需要",
        "不用考虑",
        "不想",
        "不考虑",
        "不要",
        "不看重",
        "无需",
    ]
    suffix_markers = [
        "不重要",
        "不看重",
        "不是重点",
        "无所谓",
        "不优先",
    ]
    return any(marker in prefix for marker in prefix_markers) or any(
        marker in suffix[:10]
        for marker in suffix_markers
    )


def _prefix_after_boundary(prefix: str) -> str:
    boundary_ends = []
    for marker in ["但是", "不过", "只是", "但"]:
        start = 0
        while True:
            index = prefix.find(marker, start)
            if index < 0:
                break
            if _contrast_marker_is_negated(prefix, index, marker):
                start = index + len(marker)
                continue
            boundary_ends.append(index + len(marker))
            start = index + len(marker)
    if not boundary_ends:
        return prefix
    return prefix[max(boundary_ends):]


def _suffix_before_boundary(suffix: str) -> str:
    boundary_indexes = []
    for marker in ["但是", "不过", "只是", "但"]:
        start = 0
        while True:
            index = suffix.find(marker, start)
            if index < 0:
                break
            if _contrast_marker_is_negated(suffix, index, marker):
                start = index + len(marker)
                continue
            boundary_indexes.append(index)
            break
    if not boundary_indexes:
        return suffix
    return suffix[:min(boundary_indexes)]


def _contrast_marker_is_negated(text: str, index: int, marker: str) -> bool:
    return marker in {"但", "但是"} and index > 0 and text[index - 1] == "不"


def _positive_term_index(
    text: str,
    term: str,
    blocked_phrase: str | None = None,
) -> int | None:
    start = 0
    while True:
        index = text.find(term, start)
        if index < 0:
            return None
        if not _term_is_negated(text, index, len(term)) and not _term_is_in_phrase(
            text,
            index,
            blocked_phrase,
        ):
            return index
        start = index + len(term)


def _term_is_in_phrase(
    text: str,
    term_index: int,
    phrase: str | None,
) -> bool:
    if not phrase:
        return False
    phrase_index = text.find(phrase)
    if phrase_index < 0:
        return False
    return phrase_index <= term_index < phrase_index + len(phrase)
