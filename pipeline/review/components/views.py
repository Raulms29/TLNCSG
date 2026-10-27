"""Reusable Streamlit UI components for the Review Module."""

from __future__ import annotations

import json

import streamlit as st

from pipeline.evaluation.ground_truth import GroundTruth
from pipeline.grammars import is_semgir


# ------------------------------------------------------------------
# Query
# ------------------------------------------------------------------

def render_query(qid: str, text: str, n_answers: int) -> None:
    st.caption(f"QID {qid} · {n_answers} distinct answer{'s' if n_answers != 1 else ''}")
    st.markdown(f"### {text}")


# ------------------------------------------------------------------
# Candidate output
# ------------------------------------------------------------------

def _readable_output(output: str, grammar: str) -> str:
    """The answer as grouping extracted it; SemGIR JSON is pretty-printed (key order kept)."""
    if is_semgir(grammar):
        try:
            return json.dumps(json.loads(output), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    return output


def render_output(row: dict, grammar: str) -> None:
    """The answer, readable: SemGIR JSON pretty-printed."""
    output = _readable_output(str(row.get("Representative Output", "")), grammar)
    st.code(output, language="json" if is_semgir(grammar) else "text", wrap_lines=True)


# ------------------------------------------------------------------
# Ground truth
# ------------------------------------------------------------------

def _render_ambrosia_interpretations(readings: list[tuple[str, str]]) -> None:
    """Each reading: its meaning, then its SQL."""
    for i, (meaning, sql) in enumerate(readings, start=1):
        st.markdown(f"**Interpretation {i}** — {meaning}")
        st.code(sql, language="sql", wrap_lines=True)


def render_ground_truth(gt: GroundTruth | None) -> None:
    """Show the ground truth once, above the answers."""
    if gt is None:
        st.warning("Ground truth not available for this query.")
        return

    if gt.dataset == "ambrosia":
        _render_ambrosia_interpretations(gt.readings)
        if gt.db_dump:
            with st.expander("Database Schema", expanded=False):
                st.code(gt.db_dump, language="sql")
    else:
        st.caption("LISP s-expression (friendly names)")
        st.code(gt.s_expression_friendly or "", language="lisp", wrap_lines=True)
