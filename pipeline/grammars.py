"""Grammar names: SemGIR detection and prompt lookup, including variants such as ``semgir_apo``."""

from __future__ import annotations


def is_semgir(grammar: str) -> bool:
    grammar = grammar.lower()
    return "sem_gir" in grammar or "semgir" in grammar


def prompt_for_grammar(prompts: dict[str, str], grammar: str) -> str | None:
    """The prompt of *grammar* in *prompts* (keyed by lower-case grammar name), or the prompt of the
    grammar it is a variant of (e.g. ``semgir_apo`` -> ``semgir``). None if there is neither."""
    grammar = grammar.lower()
    return prompts.get(grammar) or next((prompt for name, prompt in prompts.items() if name in grammar), None)
