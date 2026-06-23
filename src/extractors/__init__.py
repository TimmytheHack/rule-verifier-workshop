"""Preference extractors."""

from importlib import import_module
from typing import Any

from src.extractors.regex_extractor import RegexExtractor

_LAZY_EXPORTS = {
    "ExtractorFallbackPipeline": (
        "src.extractors.extractor_pipeline",
        "ExtractorFallbackPipeline",
    ),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


__all__ = ["ExtractorFallbackPipeline", "RegexExtractor"]
