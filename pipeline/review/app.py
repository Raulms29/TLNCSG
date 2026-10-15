"""Main Streamlit app for the Review Module.

Run with: `streamlit run pipeline/review/app.py`

One page per query: the query and its ground truth once, then every distinct
answer to it (all models and thinking modes) as a card. The reviewer judges
each answer and saves the whole query.
"""

import streamlit as st

from pipeline.evaluation.ground_truth import GroundTruthStore
from pipeline.review.components.cards import render_answers
from pipeline.review.components.topbar import go_to_query, next_pending_qid, render_topbar
from pipeline.review.components.views import render_ground_truth, render_query
from pipeline.review.config import ReviewConfig


# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------
st.set_page_config(page_title="TLNCSG Review", layout="wide", initial_sidebar_state="collapsed")
# Wide enough for the top bar and side-by-side card header, but not edge to edge
st.markdown(
    "<style>[data-testid='stMainBlockContainer'] { max-width: 1150px; margin: 0 auto; }</style>",
    unsafe_allow_html=True,
)

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
# Page
# ------------------------------------------------------------------
ctx = render_topbar(st.session_state.config)
query = ctx["query"]
review_state = st.session_state.review_state
gt = gt_store.get(query.qid)

# 1. The query and its ground truth, read once for every answer
render_query(query.qid, query.text, len(query.answers))
with st.container(border=True):
    st.markdown("**Ground truth**")
    render_ground_truth(gt)


def _next_query() -> None:
    nxt = next_pending_qid(ctx["queries"], query.qid, review_state)
    if nxt is None:
        st.toast(f"All queries of {ctx['grammar']} are reviewed.")
    else:
        go_to_query(nxt)


# 2. Every distinct answer, then save
render_answers(
    query,
    grammar=ctx["grammar"],
    review_state=review_state,
    is_ambrosia=gt_store.detect_dataset(query.qid) == "ambrosia",
    gt_num_interpretations=gt.num_interpretations if gt else 10,
    on_saved=_next_query,
)
