"""Interactive review form with improved conversational UX."""

from datetime import datetime
import streamlit as st

from pipeline.review.config import ERROR_CATEGORIES
from pipeline.review.state import ReviewState
from pipeline.review.components.sidebar import advance_group


def render_review_form(
    row: dict,
    state_key: str,
    express_mode: bool,
    review_state: ReviewState,
    total_rows: int,
    is_ambrosia: bool,
    gt_num_interpretations: int
):
    """Render the main review decision form."""
    st.divider()
    st.markdown("### Judgement Evaluation")
    
    # Display previous review if it exists
    existing_review = review_state.get_review(state_key)
    if existing_review:
        dt = datetime.fromisoformat(existing_review['timestamp'])
        formatted_date = dt.strftime("%d-%m-%Y")
        st.info(f"[REVIEWED] Already reviewed on {formatted_date}: "
                f"**{'Correct' if existing_review['human_correct'] else 'Incorrect'}** "
                f"(Discrepancy: {existing_review['discrepancy']})", icon=None)

    llm_is_correct = str(row.get("Correct", "")).lower() == "true"
    llm_hypotheses = int(row.get("Hypotheses Covered", 1))

    # Hypothesis coverage adjustment
    human_hypotheses = llm_hypotheses
    if is_ambrosia:
        human_hypotheses = st.number_input(
            "Hypotheses Covered", 
            value=llm_hypotheses, 
            min_value=0, 
            max_value=gt_num_interpretations
        )
        st.markdown("---")

    # Workflow state tracking
    if "review_action" not in st.session_state:
        st.session_state.review_action = None

    # Step 1: High level agreement
    st.markdown("Do you agree with the LLM's assessment of this candidate?")
    col1, col2 = st.columns(2)
    
    if col1.button("Agree", type="primary", use_container_width=True):
        st.session_state.review_action = "agree"
    
    if col2.button("Disagree", type="secondary", use_container_width=True):
        st.session_state.review_action = "disagree"


    # Step 2: Dynamic Form based on action
    if st.session_state.review_action == "agree":
        with st.container(border=True):
            if llm_is_correct:
                st.success("You agree this output is Correct.", icon=None)
                if st.button("Confirm & Next", type="primary", use_container_width=True):
                    review_state.mark_reviewed(
                        state_key,
                        human_correct=True,
                        human_hypotheses_covered=human_hypotheses,
                        discrepancy=False
                    )
                    advance_group(1, total_rows)
                    st.rerun()
            else:
                st.error("You agree this output is Incorrect.", icon=None)
                err_cat = ""
                err_notes = ""
                if not express_mode:
                    st.markdown("Please categorize the error found by the LLM:")
                    err_cat = st.selectbox("Error Category", [""] + ERROR_CATEGORIES, key="agree_cat")
                    err_notes = st.text_area("Notes (optional)", key="agree_notes")
                    
                if st.button("Confirm & Next", type="primary", use_container_width=True):
                    review_state.mark_reviewed(
                        state_key,
                        human_correct=False,
                        human_hypotheses_covered=human_hypotheses,
                        discrepancy=False,
                        error_category=err_cat,
                        error_notes=err_notes
                    )
                    advance_group(1, total_rows)
                    st.rerun()


    elif st.session_state.review_action == "disagree":
        with st.container(border=True):
            if llm_is_correct:
                st.warning("You marked this as Incorrect, overriding the evaluator.", icon=None)
            else:
                st.success("You marked this as Correct, overriding the evaluator.", icon=None)
                
            discrepancy_reason = st.text_area("Please provide a justification for overriding the evaluator's assessment", key="dis_reason")
            
            err_cat = ""
            err_notes = ""
            if llm_is_correct and not express_mode:  # If LLM said correct, but human says incorrect
                st.markdown("Please categorize the actual error:")
                err_cat = st.selectbox("Error Category", [""] + ERROR_CATEGORIES, key="dis_cat")
                err_notes = st.text_area("Notes (optional)", key="dis_notes")
                
            if st.button("Confirm & Next", type="primary", use_container_width=True):
                if not discrepancy_reason.strip():
                    st.error("Please provide a reason for the discrepancy.", icon=None)
                else:
                    review_state.mark_reviewed(
                        state_key,
                        human_correct=not llm_is_correct,
                        human_hypotheses_covered=human_hypotheses,
                        discrepancy=True,
                        discrepancy_reason=discrepancy_reason,
                        error_category=err_cat,
                        error_notes=err_notes
                    )
                    advance_group(1, total_rows)
                    st.rerun()
