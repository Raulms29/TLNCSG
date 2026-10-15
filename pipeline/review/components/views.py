"""Reusable Streamlit UI components for the Review Module."""

from __future__ import annotations

import streamlit as st

from pipeline.evaluation.ground_truth import GroundTruth
from pipeline.grouping.normalizers import decode_breakdown, split_breakdown_key


# ------------------------------------------------------------------
# Header & metadata
# ------------------------------------------------------------------

def render_query(
    row: dict,
    query_num: int,
    total_queries: int,
    group_num: int,
    total_groups: int,
) -> None:
    """Display QID and query text."""
    st.markdown(f"#### **QID:** {row['QID']} &emsp;•&emsp; **QUERY:** {query_num} OF {total_queries} &emsp;•&emsp; **GROUP:** {group_num} OF {total_groups}")
    st.subheader(row['Query'])

def render_metadata(row: dict) -> None:
    """Display the group size and which model / thinking mode produced its runs."""
    breakdown = decode_breakdown(row.get("Run Breakdown", ""))
    col1, col2 = st.columns(2)
    col1.metric("Group Size", row.get('Group Size', '—'))
    col2.metric("Models", len({split_breakdown_key(k)[0] for k in breakdown}))
    st.table([
        {
            "Model": model_dir,
            "Thinking": thinking,
            "Runs": len(runs),
            "Run IDs": ", ".join(str(r) for r in runs),
        }
        for model_dir, thinking, runs in (
            (*split_breakdown_key(k), v) for k, v in breakdown.items()
        )
    ])


# ------------------------------------------------------------------
# Ground truth
# ------------------------------------------------------------------

def render_ground_truth(gt: GroundTruth | None) -> None:
    """Show the ground truth in a collapsible expander."""
    if gt is None:
        st.warning("Ground truth not available for this query.")
        return

    with st.expander("Ground Truth", expanded=False):
        if gt.dataset == "ambrosia":
            st.markdown("**Interpretations & SQL:**")
            st.code(gt.gold_queries or "", language="sql")
            if gt.db_dump:
                with st.expander("Database Schema", expanded=False):
                    st.code(gt.db_dump, language="sql")
        else:
            st.markdown("**LISP s-expression (friendly names):**")
            st.code(gt.s_expression_friendly or "", language="lisp")


# ------------------------------------------------------------------
# LLM verdict & Rationale
# ------------------------------------------------------------------

def render_llm_verdict(row: dict) -> None:
    """Display the LLM judge's verdict as a colored banner."""
    is_correct = str(row.get("Correct", "")).lower() == "true"
    hypotheses = row.get("Hypotheses Covered", 1)

    if is_correct:
        st.success(f"[PASS] LLM says: **Correct** — Hypotheses covered: **{hypotheses}**", icon=None)
    else:
        st.error(f"[FAIL] LLM says: **Incorrect** — Hypotheses covered: **{hypotheses}**", icon=None)


def render_llm_rationale(row: dict) -> None:
    """Display the LLM's rationale at the very end."""
    rationale = row.get("Rationale", "")
    with st.expander("Evaluator Rationale", expanded=True):
        st.markdown(rationale if rationale else "*No rationale provided.*")


# ------------------------------------------------------------------
# Candidate output
# ------------------------------------------------------------------

def render_candidate_output(row: dict, grammar: str) -> None:
    """Render the representative output and optional reasoning trace."""
    output = str(row.get("Representative Output", "")).strip()
    reasoning = row.get("Reasoning", "")

    # Strip markdown code blocks if the LLM accidentally left them in the output
    if output.startswith("```"):
        lines = output.split("\n")
        if len(lines) > 1:
            lines = lines[1:]  # Remove the opening ```lang
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]  # Remove the closing ```
            output = "\n".join(lines).strip()
        else:
            output = output.strip("`")

    lang = "json" if "sem_gir" in grammar.lower() or "semgir" in grammar.lower() else "text"

    st.markdown("**Candidate Output:**")
    st.code(output, language=lang)

    if reasoning and str(reasoning).strip():
        with st.expander("Thinking / Reasoning Trace", expanded=False):
            st.text(reasoning)


# ------------------------------------------------------------------
# Progress
# ------------------------------------------------------------------

def render_progress(title: str, reviewed: int, total: int) -> None:
    """Show a progress bar and fraction."""
    if total == 0:
        st.info(f"{title}: No groups to review.")
        return
    pct = reviewed / total
    pct = min(1.0, max(0.0, pct))
    st.progress(pct, text=f"{title} Progress: {reviewed} / {total}")
