"""Top bar of the Review Module: grammar, query navigation, progress and settings."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from pipeline.review.components.data import (
    Query,
    find_evaluated_csvs,
    grammars_in,
    load_queries,
)
from pipeline.review.config import ReviewConfig
from pipeline.review.exporter import generate_outputs
from pipeline.review.state import ReviewState


def is_query_done(query: Query, review_state: ReviewState) -> bool:
    return all(review_state.is_reviewed(a.key) for a in query.answers)


def go_to_query(qid: str) -> None:
    """Open a query; per-answer edit toggles are cleared."""
    st.session_state.qid = qid
    st.session_state.editing = set()


def next_pending_qid(
    queries: list[Query], current_qid: str, review_state: ReviewState
) -> str | None:
    """The next query (after the current one, wrapping) that still has unreviewed answers."""
    qids = [q.qid for q in queries]
    start = qids.index(current_qid) + 1 if current_qid in qids else 0
    for query in queries[start:] + queries[:start]:
        if not is_query_done(query, review_state):
            return query.qid
    return None


def _step(queries: list[Query], increment: int) -> None:
    qids = [q.qid for q in queries]
    current = qids.index(st.session_state.qid)
    go_to_query(qids[(current + increment) % len(qids)])


def _on_grammar_change() -> None:
    st.session_state.pop("qid", None)


def _render_settings(
    cfg: ReviewConfig, review_state: ReviewState, csv_files: list[Path]
) -> None:
    with st.popover("⚙", help="Settings and export"):
        eval_dir = st.text_input("Evaluation directory", value=cfg.evaluation_dir)
        if eval_dir != cfg.evaluation_dir:
            cfg.evaluation_dir = eval_dir
            st.session_state.pop("qid", None)
            st.rerun()
        st.checkbox(
            "Express Mode", key="express_mode", help="Hide error categorization"
        )
        if st.button("Generate Output Files", type="primary", width="stretch"):
            generate_outputs(
                cfg.output_dir, review_state.all_reviews, csv_files
            )


def render_topbar(cfg: ReviewConfig) -> dict:
    """Render the top bar and return the selected grammar, its queries and the current query."""
    if "review_state" not in st.session_state:
        # Shared by all runs, so verdicts carry over
        st.session_state.review_state = ReviewState(Path(cfg.review_state_path))
    review_state: ReviewState = st.session_state.review_state

    csv_files = find_evaluated_csvs(cfg.evaluation_dir)
    if not csv_files:
        st.error(f"No `*_evaluated.csv` files found in `{cfg.evaluation_dir}`.")
        _render_settings(cfg, review_state, csv_files)
        st.stop()

    grammars = grammars_in(csv_files)
    # Row 1: grammar (+ settings); row 2: query navigation
    _, col_grammar, col_settings = st.columns([1, 10, 1], vertical_alignment="center")

    with col_grammar.container(horizontal=True, horizontal_alignment="center"):
        grammar = st.segmented_control(
            "Grammar",
            grammars,
            default=grammars[0],
            required=True,
            key="grammar",
            on_change=_on_grammar_change,
            label_visibility="collapsed",
            width="content",
        )

    queries = load_queries(csv_files, grammar)
    qids = [q.qid for q in queries]
    if st.session_state.get("qid") not in qids:
        # Resume at the first query with unreviewed answers
        go_to_query(next_pending_qid(queries, "", review_state) or qids[0])
    position = qids.index(st.session_state.qid)

    with col_settings:
        _render_settings(cfg, review_state, csv_files)

    col_nav, col_jump = st.columns([1, 2], vertical_alignment="center")
    # One flex row, items centred vertically
    with col_nav.container(horizontal=True, vertical_alignment="center", horizontal_alignment="center"):
        if st.button(
            "",
            shortcut="Left",
            width=56,
            help="Previous query (←)",
        ):
            _step(queries, -1)
            st.rerun()
        # A borderless button, not text: same box as its neighbours, so it lines up with them
        st.button(
            f"Query **{position + 1}** / {len(queries)}",
            type="tertiary",
            key="query_counter",
            help="Change query with ← / → or the list",
        )
        if st.button(
            "",
            shortcut="Right",
            width=56,
            help="Next query (→)",
        ):
            _step(queries, 1)
            st.rerun()

    with col_jump:
        labels = {
            q.qid: f"{'✔' if is_query_done(q, review_state) else '●'}  {q.qid} — {q.text[:60]}"
            for q in queries
        }
        st.session_state.jump = st.session_state.qid
        st.selectbox(
            "Jump to query",
            qids,
            key="jump",
            format_func=lambda qid: labels[qid],
            on_change=lambda: go_to_query(st.session_state.jump),
            label_visibility="collapsed",
        )

    keys = {a.key for q in queries for a in q.answers}
    reviewed, total = review_state.get_progress(list(keys))
    st.progress(
        reviewed / total if total else 0.0,
        text=f"{grammar}: {reviewed} / {total} answers reviewed",
    )

    return {
        "grammar": grammar,
        "queries": queries,
        "query": queries[position],
    }
