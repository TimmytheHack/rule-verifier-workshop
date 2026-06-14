"""招生政策参考资料的只读 lexical matcher。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.domains import DomainConfig


@dataclass(frozen=True)
class PolicyReferenceHit:
    """EvidencePack 中的 reference-only 命中。"""

    reference_id: str
    title: str
    source: str
    matched_terms: list[str]
    excerpt: str
    status: str = "reference_only"
    effect: str = "does_not_change_sql_or_results"

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "title": self.title,
            "source": self.source,
            "matched_terms": self.matched_terms,
            "excerpt": self.excerpt,
            "status": self.status,
            "effect": self.effect,
        }


class PolicyReferenceIndex:
    """从已审核 Markdown 资料中提取解释性片段，不产生 hard rule。"""

    def __init__(
        self,
        domain_config: DomainConfig,
        docs_path: Path,
        keywords: list[str],
        max_hits: int,
    ) -> None:
        self.domain_config = domain_config
        self.docs_path = docs_path
        self.keywords = _unique_terms(keywords)
        self.max_hits = max(0, int(max_hits))

    @classmethod
    def from_domain_config(cls, domain_config: DomainConfig) -> "PolicyReferenceIndex":
        config = domain_config.payload.get("policy_references") or {}
        path_value = config.get("path") or (
            (domain_config.payload.get("paths") or {}).get("policy_references")
        )
        docs_path = (
            domain_config.resolve_path(path_value)
            if path_value
            else domain_config.root / "_missing_policy_references"
        )
        if not config.get("enabled") or config.get("status") != "approved":
            return cls(domain_config, docs_path, [], 0)
        return cls(
            domain_config=domain_config,
            docs_path=docs_path,
            keywords=_configured_keywords(config),
            max_hits=int(config.get("max_hits") or 3),
        )

    def match(self, query: str) -> list[dict[str, Any]]:
        if self.max_hits <= 0 or not self.docs_path.exists():
            return []
        query_text = _normalize_text(query)
        if not query_text:
            return []
        hits: list[tuple[int, str, PolicyReferenceHit]] = []
        for path in sorted(self.docs_path.glob("*.md")):
            text = _normalize_text(path.read_text(encoding="utf-8"))
            matched_terms = [
                term for term in self.keywords if term in query_text and term in text
            ]
            if not matched_terms:
                continue
            title = _title_from_markdown(text, fallback=path.stem)
            excerpt = _excerpt_for_terms(text, matched_terms)
            source = _relative_source(path, self.domain_config.root)
            score = sum(len(term) for term in matched_terms)
            hits.append(
                (
                    score,
                    source,
                    PolicyReferenceHit(
                        reference_id=path.stem,
                        title=title,
                        source=source,
                        matched_terms=matched_terms,
                        excerpt=excerpt,
                    ),
                )
            )
        hits.sort(key=lambda item: (-item[0], item[1]))
        return [hit.to_dict() for _, _, hit in hits[: self.max_hits]]


def policy_references_for_query(
    domain_config: DomainConfig,
    query: str,
) -> list[dict[str, Any]]:
    """读取 domain pack 配置，返回 reference-only 资料命中。"""

    try:
        return PolicyReferenceIndex.from_domain_config(domain_config).match(query)
    except OSError:
        return []


def _configured_keywords(config: dict[str, Any]) -> list[str]:
    raw = config.get("keywords") or {}
    if isinstance(raw, list):
        return [str(item) for item in raw]
    terms: list[str] = []
    for value in raw.values():
        if isinstance(value, list):
            terms.extend(str(item) for item in value)
        elif value:
            terms.append(str(value))
    return terms


def _unique_terms(terms: list[str]) -> list[str]:
    result: list[str] = []
    for term in sorted((item.strip() for item in terms), key=len, reverse=True):
        if term and term not in result:
            result.append(term)
    return result


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _title_from_markdown(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return fallback


def _excerpt_for_terms(text: str, terms: list[str], max_length: int = 180) -> str:
    first_term = min(
        terms,
        key=lambda term: text.find(term) if term in text else len(text),
    )
    index = text.find(first_term)
    if index < 0:
        return text[:max_length]
    start = max(0, index - 40)
    end = min(len(text), index + max_length - 40)
    excerpt = text[start:end].strip()
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(text):
        excerpt = excerpt + "..."
    return excerpt


def _relative_source(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return path.name
