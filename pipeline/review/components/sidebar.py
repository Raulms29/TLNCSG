"""Sidebar rendering and navigation state for the Review Module."""

import csv
from pathlib import Path
from typing import Any

import streamlit as st

from pipeline.review.components.views import render_progress
from pipeline.review.config import ReviewConfig
from pipeline.review.exporter import generate_outputs
from pipeline.review.state import ReviewState


@st.cache_data(show_spinner=False)
def get_available_csvs(eval_dir: str) -> list[Path]:
    """Find all evaluated CSVs."""
    p = Path(eval_dir)
    if not p.exists() or not p.is_dir():
        return []
    return list(p.rglob("*_evaluated.csv"))


@st.cache_data(show_spinner=False)
def load_csv_data(csv_path: Path) -> list[dict[str, Any]]:
    """Load rows from a CSV."""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


@st.cache_data(show_spinner=False)
def get_global_total_rows(csv_files: list[Path]) -> int:
    total = 0
    for f in csv_files:
        with open(f, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            total += sum(1 for _ in reader)
    return total

def advance_group(increment: int, total_groups: int):
    """Move the navigation index."""
    if "current_idx" in st.session_state:
        st.session_state.current_idx = (st.session_state.current_idx + increment) % total_groups
    st.session_state.review_action = None


def advance_query(increment: int, all_rows: list[dict]):
    """Move to the first group of the next or previous query."""
    if "current_idx" not in st.session_state or not all_rows:
        return
        
    current_idx = st.session_state.current_idx
    current_qid = all_rows[current_idx].get("QID", "")
    
    # Get unique QIDs and their starting indices
    qid_starts = []
    seen = set()
    for i, r in enumerate(all_rows):
        q = r.get("QID", "")
        if q not in seen:
            seen.add(q)
            qid_starts.append(i)
            
    # Find current QID index
    current_q_idx = 0
    for idx, start_idx in enumerate(qid_starts):
        if all_rows[start_idx].get("QID", "") == current_qid:
            current_q_idx = idx
            break
            
    # Calculate next QID index with wrapping
    next_q_idx = (current_q_idx + increment) % len(qid_starts)
    
    st.session_state.current_idx = qid_starts[next_q_idx]
    st.session_state.review_action = None


def render_sidebar(cfg: ReviewConfig):
    """Render the sidebar and return the current context."""
    with st.sidebar:
        st.title("Settings")
        
        # Eval dir selection
        eval_dir = st.text_input("Evaluation Directory", value=cfg.evaluation_dir)
        cfg.evaluation_dir = eval_dir
        
        csv_files = get_available_csvs(eval_dir)
        if not csv_files:
            st.error("No `*_evaluated.csv` files found.")
            st.stop()
            
        # Extract grammars and models from paths
        grammars = sorted(list({p.parent.parent.name for p in csv_files}))
        selected_grammar = st.selectbox("Grammar", options=grammars)
        
        models = sorted(list({p.parent.name for p in csv_files if p.parent.parent.name == selected_grammar}))
        selected_model = st.selectbox("Model", options=models)
        
        # Get the specific CSVs
        selected_csv_paths = sorted([p for p in csv_files if p.parent.parent.name == selected_grammar and p.parent.name == selected_model])
        if not selected_csv_paths:
            st.warning("No CSV for this combination.")
            st.stop()
            
        # Init state singleton
        if "review_state" not in st.session_state:
            state_file = Path(eval_dir) / "review_state.json"
            st.session_state.review_state = ReviewState(state_file)
            
        review_state: ReviewState = st.session_state.review_state
        
        all_rows = []
        all_keys = []
        for p in selected_csv_paths:
            rel_path = p.relative_to(Path(eval_dir)).as_posix()
            rows_in_file = load_csv_data(p)
            for i, r in enumerate(rows_in_file):
                all_rows.append(r)
                all_keys.append(f"{rel_path}::{i}")
                
        if not all_rows:
            st.warning("No data found for this combination.")
            st.stop()
            
        selection_key = f"{selected_grammar}_{selected_model}"
        if st.session_state.get("active_selection") != selection_key:
            st.session_state.active_selection = selection_key
            
            # Auto-resume: find first unreviewed index
            st.session_state.current_idx = next((i for i, k in enumerate(all_keys) if not review_state.is_reviewed(k)), 0)
            st.session_state.review_action = None
        
        st.markdown("### Progress")
        
        # Grammar Progress
        grammar_csvs = [p for p in csv_files if p.parent.parent.name == selected_grammar]
        grammar_total = get_global_total_rows(grammar_csvs)
        grammar_reviewed = sum(1 for k in review_state.all_reviews if k.startswith(f"{selected_grammar}/"))
        render_progress("Grammar", grammar_reviewed, grammar_total)
        
        # Global Progress
        global_total = get_global_total_rows(csv_files)
        global_reviewed = len(review_state.all_reviews)
        render_progress("Overall", global_reviewed, global_total)
        
        express_mode = st.checkbox("Express Mode", value=False, help="Hide error categorization")
        if st.button("Generate Output Files", type="primary", use_container_width=True):
            generate_outputs(eval_dir, cfg.output_dir, review_state.all_reviews, csv_files)
            
    if "current_idx" not in st.session_state:
        st.session_state.current_idx = next((i for i, k in enumerate(all_keys) if not review_state.is_reviewed(k)), 0)
        
    st.session_state.current_idx = min(max(0, st.session_state.current_idx), len(all_rows) - 1)
    
    idx = st.session_state.current_idx
    
    # Model progress
    model_reviewed, model_total = review_state.get_progress(all_keys)
    
    return {
        "row": all_rows[idx],
        "all_rows": all_rows,
        "state_key": all_keys[idx],
        "express_mode": express_mode,
        "selected_grammar": selected_grammar,
        "selected_model": selected_model,
        "model_reviewed": model_reviewed,
        "model_total": model_total,
        "keys": all_keys,
        "current_idx": idx
    }
