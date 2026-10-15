"""Export functionality for the Review Module."""

import csv
from pathlib import Path
import streamlit as st

from pipeline.grouping.normalizers import decode_breakdown, split_breakdown_key


def generate_outputs(eval_dir: str, out_dir: str, reviews: dict, csv_files: list[Path]):
    """Merge review state with evaluated CSVs and generate export artifacts."""
    st.info("Generating output files...")
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    
    base_llm_errors = []
    judge_llm_errors = []
    
    for csv_file in csv_files:
        grammar = csv_file.parent.name
        run = csv_file.parent.parent.name
        
        rows = []
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
                
        new_rows = []
        
        # Output csv goes to outputs/review/<run>/<GRAMMAR>/Q*_reviewed.csv
        out_csv = out_root / csv_file.relative_to(Path(eval_dir))
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        
        for row in rows:
            rev = reviews.get(row["Output Key"])
            if not rev:
                continue

            # The verdict may come from another run, whose evaluator could have said
            # something else: the discrepancy is always against this run's evaluator.
            llm_correct = str(row.get("Correct", "")).lower() == "true"
            discrepancy = rev["human_correct"] != llm_correct
            same_run = rev.get("run", "") == run
            if same_run:
                discrepancy_reason = rev["discrepancy_reason"]
            else:
                discrepancy_reason = f"(verdict reused from run {rev.get('run', '?')}) {rev['discrepancy_reason']}".strip()
            models = ", ".join(
                f"{m} (Thinking)" if thinking else m
                for m, thinking in (split_breakdown_key(k) for k in decode_breakdown(row.get("Run Breakdown", "")))
            )
                
            row.update({
                "Human Correct": rev["human_correct"],
                "Human Hypotheses Covered": rev["human_hypotheses_covered"],
                "Discrepancy": discrepancy,
                "Discrepancy Reason": discrepancy_reason if discrepancy else "",
                "Error Category": rev["error_category"],
                "Error Notes": rev["error_notes"],
                "Review Timestamp": rev["timestamp"],
                "Reviewed In Run": rev.get("run", ""),
            })
            new_rows.append(row)
            
            # Populate error logs
            if not rev["human_correct"]:
                base_llm_errors.append({
                    "QID": row.get("QID"),
                    "Query": row.get("Query"),
                    "Grammar": grammar,
                    "Models": models,
                    "Error Category": rev["error_category"],
                    "Error Notes": rev["error_notes"],
                    "Representative Output": row.get("Representative Output")
                })
                
            if discrepancy:
                judge_llm_errors.append({
                    "QID": row.get("QID"),
                    "Query": row.get("Query"),
                    "Grammar": grammar,
                    "Models": models,
                    "LLM Said": row.get("Correct"),
                    "Human Said": rev["human_correct"],
                    "Discrepancy Reason": discrepancy_reason,
                    "LLM Rationale": row.get("Rationale")
                })
                
        # Save reviewed CSV
        if new_rows:
            fieldnames = list(new_rows[0].keys())
            reviewed_csv_path = out_csv.with_name(out_csv.name.replace("_evaluated.csv", "_reviewed.csv"))
            with open(reviewed_csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(new_rows)
                
    # Save global error logs
    if base_llm_errors:
        with open(out_root / "base_llm_errors.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(base_llm_errors[0].keys()))
            writer.writeheader()
            writer.writerows(base_llm_errors)
            
    if judge_llm_errors:
        with open(out_root / "judge_llm_errors.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(judge_llm_errors[0].keys()))
            writer.writeheader()
            writer.writerows(judge_llm_errors)
            
    st.success(f"Successfully generated outputs to {out_root}")
