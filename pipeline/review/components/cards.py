"""Answer cards: the reviewer judges every distinct answer of a query, then saves the query."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from pipeline.review.components.data import Answer, Query, is_true
from pipeline.review.components.views import render_output
from pipeline.evaluation.error_categories import ERROR_CATEGORIES
from pipeline.review.state import ReviewState

CORRECT, INCORRECT = "✓ Correct", "✗ Incorrect"


def _groups_label(answer: Answer) -> str:
    """e.g. 'gemma4_26b · 30 runs  |  qwen3_8b · Reasoning · 2 runs'."""
    return " &nbsp;|&nbsp; ".join(
        f"**{g['_model']}**{' · Reasoning' if is_true(g.get('Thinking')) else ''} · {g.get('Group Size', '?')} runs"
        for g in sorted(answer.groups, key=lambda g: int(g.get("Group Size") or 0), reverse=True)
    )


def _judge_badge(answer: Answer) -> str:
    verdicts = answer.judge_verdicts
    if verdicts == {True}:
        return ":green-badge[Judge ✓]"
    if verdicts == {False}:
        return ":red-badge[Judge ✗]"
    return ":orange-badge[Judge: mixed]"


def _judge_category_badge(answer: Answer) -> str:
    """The judge's suggested error categories (one per distinct suggestion across runs), or ''."""
    categories = sorted({g.get("LLM Error Category") for g in answer.groups} - {None, ""})
    return f":gray-badge[{' / '.join(categories)}]" if categories else ""


def _judge_category(answer: Answer) -> str | None:
    """The judge's error category of the largest group that has one, to preselect; None if there is none."""
    for g in sorted(answer.groups, key=lambda g: int(g.get("Group Size") or 0), reverse=True):
        if g.get("LLM Error Category") in ERROR_CATEGORIES:
            return g["LLM Error Category"]
    return None


def _is_open(answer: Answer, review_state: ReviewState) -> bool:
    """Undecided answers and the ones being edited take a decision; the rest are collapsed."""
    return not review_state.is_reviewed(answer.key) or answer.key in st.session_state.get("editing", set())


def _start_edit(answer: Answer, review: dict) -> None:
    """Reopen a reviewed answer with its stored decision prefilled."""
    st.session_state.setdefault("editing", set()).add(answer.key)
    st.session_state[f"v_{answer.key}"] = CORRECT if review["human_correct"] else INCORRECT
    st.session_state[f"r_{answer.key}"] = review.get("discrepancy_reason", "")
    st.session_state[f"c_{answer.key}"] = review.get("error_category") or None
    st.session_state[f"n_{answer.key}"] = review.get("error_notes", "")
    st.session_state[f"h_{answer.key}"] = int(review.get("human_hypotheses_covered", 1))


def _render_reviewed(answer: Answer, review: dict) -> None:
    """One line: who produced it, the stored verdict, where it was given, and Edit."""
    with st.container(border=True):
        col_text, col_edit = st.columns([12, 1], vertical_alignment="center")
        verdict = ":green-badge[✓ Correct]" if review["human_correct"] else ":red-badge[✗ Incorrect]"
        run = review.get("run", "")
        reused = run and run not in {g["_run"] for g in answer.groups}
        date = datetime.fromisoformat(review["timestamp"]).strftime("%d-%m-%Y")
        where = f"↺ reviewed in run {run}, {date}" if reused else f"reviewed {date}"
        col_text.markdown(f"{verdict} &nbsp; {_groups_label(answer)} &nbsp; :gray[{where}]")
        col_edit.button("Edit", key=f"edit_{answer.key}", on_click=_start_edit, args=(answer, review))


def _render_open(answer: Answer, number: int, grammar: str, is_ambrosia: bool, gt_num_interpretations: int) -> None:
    """Full card: who produced it, the output, the judge, and the reviewer's decision."""
    key = answer.key
    rep = answer.rep
    with st.container(border=True):
        col_head, col_verdict = st.columns([3, 1], vertical_alignment="center")
        col_head.markdown(
            f"**#{number}** &nbsp; {_judge_badge(answer)} {_judge_category_badge(answer)} &nbsp; {_groups_label(answer)}"
        )
        verdict = col_verdict.segmented_control(
            "Your verdict", [CORRECT, INCORRECT], key=f"v_{key}", label_visibility="collapsed", width="stretch",
        )

        render_output(rep, grammar)

        rationales: dict[str, list[str]] = {}
        for g in answer.groups:
            rationales.setdefault(g.get("Rationale", "") or "*No rationale provided.*", []).append(g["_model"])
        with st.expander("Judge rationale", expanded=False):
            for text, models in rationales.items():
                if len(rationales) > 1:
                    st.caption(", ".join(sorted(set(models))))
                st.markdown(text)
        if str(rep.get("Reasoning", "")).strip():
            with st.expander("Reasoning trace", expanded=False):
                st.text(rep["Reasoning"])

        if verdict is None:
            return
        human_correct = verdict == CORRECT
        if is_ambrosia:
            st.session_state.setdefault(f"h_{key}", int(rep.get("Hypotheses Covered") or 1))
            st.session_state[f"h_{key}"] = min(st.session_state[f"h_{key}"], gt_num_interpretations)
            st.number_input("Hypotheses covered", min_value=0, max_value=gt_num_interpretations, key=f"h_{key}")
        if answer.judge_verdicts != {human_correct}:
            st.text_area("Why is the judge wrong? (required)", key=f"r_{key}", height=68)
        if not human_correct and not st.session_state.get("express_mode"):
            st.session_state.setdefault(f"c_{key}", _judge_category(answer))
            st.pills("Error category", ERROR_CATEGORIES, key=f"c_{key}")
            st.text_input("Notes (optional)", key=f"n_{key}")


def _accept_judge(open_answers: list[Answer]) -> None:
    """Fill every undecided answer whose judges agree with the judge's verdict."""
    for answer in open_answers:
        if st.session_state.get(f"v_{answer.key}") is None and len(answer.judge_verdicts) == 1:
            st.session_state[f"v_{answer.key}"] = CORRECT if answer.judge_verdicts == {True} else INCORRECT


def _save(query: Query, open_answers: list[Answer], grammar: str, is_ambrosia: bool, review_state: ReviewState) -> list[str]:
    """Validate every open answer, then save them all. Returns the problems, if any."""
    problems = []
    numbers = {a.key: i for i, a in enumerate(query.answers, 1)}
    for answer in open_answers:
        verdict = st.session_state.get(f"v_{answer.key}")
        if verdict is None:
            problems.append(f"#{numbers[answer.key]} has no verdict.")
        elif answer.judge_verdicts != {verdict == CORRECT} and not str(st.session_state.get(f"r_{answer.key}", "")).strip():
            problems.append(f"#{numbers[answer.key]} overrides the judge: explain why.")
    if problems:
        return problems

    for answer in open_answers:
        k = answer.key
        human_correct = st.session_state[f"v_{k}"] == CORRECT
        # Express mode hides the category pills: the judge's category is kept
        category = _judge_category(answer) if st.session_state.get("express_mode") else st.session_state.get(f"c_{k}")
        discrepancy = answer.judge_verdicts != {human_correct}
        review_state.mark_reviewed(
            k,
            run=answer.rep["_run"],
            grammar=grammar,
            qid=query.qid,
            human_correct=human_correct,
            human_hypotheses_covered=int(st.session_state.get(f"h_{k}") or answer.rep.get("Hypotheses Covered") or 1)
            if is_ambrosia else int(answer.rep.get("Hypotheses Covered") or 1),
            discrepancy=discrepancy,
            discrepancy_reason=st.session_state.get(f"r_{k}", "") if discrepancy else "",
            error_category=(category or "") if not human_correct else "",
            error_notes=st.session_state.get(f"n_{k}", "") if not human_correct else "",
        )
    return []


def render_answers(query: Query, grammar: str, review_state: ReviewState, is_ambrosia: bool,
                   gt_num_interpretations: int, on_saved) -> None:
    """All answers of the query, then the save bar. ``on_saved`` moves to the next query."""
    open_answers = [a for a in query.answers if _is_open(a, review_state)]

    for number, answer in enumerate(query.answers, 1):
        if answer in open_answers:
            _render_open(answer, number, grammar, is_ambrosia, gt_num_interpretations)
        else:
            _render_reviewed(answer, review_state.get_review(answer.key))

    if not open_answers:
        st.success("Every answer of this query is reviewed.")
        return

    col_accept, col_save = st.columns([1, 2])
    col_accept.button(
        "Accept judge for the rest", width="stretch", on_click=_accept_judge, args=(open_answers,),
        help="Set every undecided answer to the judge's verdict (answers with mixed judges are left undecided).",
    )
    if col_save.button("Save query & next", type="primary", shortcut="Ctrl+Enter", width="stretch"):
        problems = _save(query, open_answers, grammar, is_ambrosia, review_state)
        if problems:
            for p in problems:
                st.error(p, icon=None)
            return
        st.session_state.editing = set()
        on_saved()
        st.rerun()
