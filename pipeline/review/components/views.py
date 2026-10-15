"""Reusable Streamlit UI components for the Review Module."""

from __future__ import annotations

import json
import re

import streamlit as st

from pipeline.evaluation.ground_truth import GroundTruth


def _is_semgir(grammar: str) -> bool:
    return "sem_gir" in grammar.lower() or "semgir" in grammar.lower()


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
    """Strip code fences and, for SemGIR, pretty-print the JSON (key order kept)."""
    output = output.strip()
    matches = list(re.finditer(r"```(?:\w+)?\s*([\s\S]*?)\s*```", output))
    if matches:
        output = matches[-1].group(1).strip()
    if _is_semgir(grammar):
        try:
            return json.dumps(json.loads(output), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    return output


def render_output(row: dict, grammar: str) -> None:
    """The answer, readable: fences stripped, SemGIR JSON pretty-printed."""
    output = _readable_output(str(row.get("Representative Output", "")), grammar)
    st.code(output, language="json" if _is_semgir(grammar) else "text", wrap_lines=True)


# ------------------------------------------------------------------
# Ground truth
# ------------------------------------------------------------------

def _render_ambrosia_interpretations(gold_queries: str) -> None:
    """Show each 'Interpretation i: / Meaning: / SQL:' block separately."""
    blocks = [b.strip() for b in gold_queries.split("\n\n") if b.strip()]
    for block in blocks:
        lines = block.split("\n")
        meaning = next((l[len("Meaning:"):].strip() for l in lines if l.startswith("Meaning:")), None)
        sql_start = next((i for i, l in enumerate(lines) if l.startswith("SQL:")), None)
        if meaning is None or sql_start is None:
            st.code(block, language="sql", wrap_lines=True)
            continue
        sql = "\n".join([lines[sql_start][len("SQL:"):]] + lines[sql_start + 1:]).strip()
        st.markdown(f"**{lines[0].rstrip(':')}** — {meaning}")
        st.code(sql, language="sql", wrap_lines=True)


def render_ground_truth(gt: GroundTruth | None) -> None:
    """Show the ground truth once, above the answers."""
    if gt is None:
        st.warning("Ground truth not available for this query.")
        return

    if gt.dataset == "ambrosia":
        _render_ambrosia_interpretations(gt.gold_queries or "")
        if gt.db_dump:
            with st.expander("Database Schema", expanded=False):
                st.code(gt.db_dump, language="sql")
    else:
        st.caption("LISP s-expression (friendly names)")
        st.code(gt.s_expression_friendly or "", language="lisp", wrap_lines=True)
