"""Grammar names: families, SemGIR detection and prompt lookup, including variants such as ``semgir_apo``."""

from __future__ import annotations

FAMILIES = ("SemGIR", "SQUALL", "GraphQ_IR")


def _compact(name: str) -> str:
    return name.lower().replace("_", "")


def grammar_family(grammar: str) -> str:
    """The family *grammar* is a variant of, matched ignoring case and underscores
    (``SemGIR_APO`` -> ``SemGIR``, ``graphqir_ablation`` -> ``GraphQ_IR``); any other grammar is its own family."""
    compact = _compact(grammar)
    return next((family for family in FAMILIES if _compact(family) in compact), grammar)


def is_semgir(grammar: str) -> bool:
    return grammar_family(grammar) == "SemGIR"


def prompt_for_grammar(prompts: dict[str, str], grammar: str) -> str | None:
    """The prompt of *grammar* in *prompts* (keyed by grammar name, matched ignoring case and underscores), or the
    prompt of the grammar it is a variant of (e.g. ``semgir_apo`` -> ``semgir``). None if there is neither."""
    by_name = {_compact(name): prompt for name, prompt in prompts.items()}
    grammar = _compact(grammar)
    return by_name.get(grammar) or next((prompt for name, prompt in by_name.items() if name in grammar), None)
