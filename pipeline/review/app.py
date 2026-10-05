"""Main Streamlit app for the Review Module.

Run with: `streamlit run pipeline/review/app.py`
"""

import streamlit as st

from pipeline.evaluation.ground_truth import GroundTruthStore
from pipeline.review.components.views import (
    render_candidate_output,
    render_ground_truth,
    render_llm_rationale,
    render_llm_verdict,
    render_query,
    render_metadata,
    render_progress,
)
from pipeline.review.config import ReviewConfig
from pipeline.review.components.sidebar import render_sidebar, advance_group, advance_query
from pipeline.review.components.form import render_review_form


# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------
st.set_page_config(page_title="TLNCSG Evaluation Review", layout="centered")

if "config" not in st.session_state:
    try:
        st.session_state.config = ReviewConfig.from_json("review_config.json")
    except Exception as e:
        st.error(f"Failed to load review_config.json: {e}")
        st.stop()

if "gt_store" not in st.session_state:
    cfg: ReviewConfig = st.session_state.config
    st.session_state.gt_store = GroundTruthStore(
        ambrosia_path=cfg.dataset_paths.ambrosia,
        grailqa_path=cfg.dataset_paths.grailqa,
        ambrosia_qid_prefix=cfg.ambrosia_qid_prefix,
    )

gt_store: GroundTruthStore = st.session_state.gt_store


# ------------------------------------------------------------------
# Main Orchestration
# ------------------------------------------------------------------
ctx = render_sidebar(st.session_state.config)
row = ctx["row"]
all_rows = ctx["all_rows"]
total_groups = len(all_rows)

qid = row.get("QID", "")
dataset = gt_store.detect_dataset(qid)
gt = gt_store.get(qid)
is_ambrosia = dataset == "ambrosia"

# 0. Navigation & Progress
col_prog1, col_prog2 = st.columns(2)
with col_prog1:
    render_progress(f"Model ({ctx['selected_grammar']}/{ctx['selected_model']})", ctx["model_reviewed"], ctx["model_total"])

with col_prog2:
    # Current QID progress
    qid_keys = [k for i, k in enumerate(ctx["keys"]) if all_rows[i].get("QID", "") == qid]
    qid_reviewed, qid_total = st.session_state.review_state.get_progress(qid_keys)
    render_progress(f"Query ({qid})", qid_reviewed, qid_total)

# Clean Navigation Buttons
col_nav1, col_nav2, col_nav3, col_nav4 = st.columns(4)
with col_nav1:
    if st.button("Previous Query", use_container_width=True):
        advance_query(-1, all_rows)
        st.rerun()
with col_nav2:
    if st.button("Previous Group", use_container_width=True):
        advance_group(-1, total_groups)
        st.rerun()
with col_nav3:
    if st.button("Next Group", use_container_width=True):
        advance_group(1, total_groups)
        st.rerun()
with col_nav4:
    if st.button("Next Query", use_container_width=True):
        advance_query(1, all_rows)
        st.rerun()

st.divider()

# 1. Query
qid_indices = [i for i, r in enumerate(all_rows) if r.get("QID", "") == qid]
group_num_in_qid = qid_indices.index(ctx["current_idx"]) + 1
total_groups_in_qid = len(qid_indices)

unique_qids = list(dict.fromkeys(r.get("QID", "") for r in all_rows))

query_num = unique_qids.index(qid) + 1
total_queries = len(unique_qids)

render_query(row, query_num, total_queries, group_num_in_qid, total_groups_in_qid)

# 2. LLM Verdict
render_llm_verdict(row)

# 2.5 Metadata
render_metadata(row)

# 3. Interactive form
render_review_form(
    row=row,
    state_key=ctx["state_key"],
    express_mode=ctx["express_mode"],
    review_state=st.session_state.review_state,
    total_rows=total_groups,
    is_ambrosia=is_ambrosia,
    gt_num_interpretations=gt.num_interpretations if gt else 10
)

# 4. Ground Truth
render_ground_truth(gt)

# 5. Candidate Output
render_candidate_output(row, ctx["selected_grammar"])

# 6. Rationale
render_llm_rationale(row)
