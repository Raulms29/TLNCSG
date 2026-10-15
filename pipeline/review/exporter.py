"""Export functionality for the Review Module."""

import csv
from pathlib import Path
import streamlit as st


def generate_outputs(out_dir: str, reviews: dict, csv_files: list[Path]):
    """Merge review state with evaluated CSVs and generate export artifacts.

    Everything is written per execution, whatever evaluation directory was opened:
    <out_dir>/<run>/<GRAMMAR>/<model>/Q*_reviewed.csv, plus <out_dir>/<run>/*_errors.csv.
    """
    st.toast("Generating output files...")
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    
    # run -> error rows
    base_llm_errors: dict[str, list[dict]] = {}
    judge_llm_errors: dict[str, list[dict]] = {}
    
    for csv_file in csv_files:
        grammar = csv_file.parent.parent.name
        model = csv_file.parent.name
        run = csv_file.parent.parent.parent.name
        
        rows = []
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
                
        new_rows = []
        
        out_csv = out_root / run / grammar / model / csv_file.name
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
                base_llm_errors.setdefault(run, []).append({
                    "QID": row.get("QID"),
                    "Query": row.get("Query"),
                    "Grammar": grammar,
                    "Model": model,
                    "Error Category": rev["error_category"],
                    "Error Notes": rev["error_notes"],
                    "Representative Output": row.get("Representative Output")
                })
                
            if discrepancy:
                judge_llm_errors.setdefault(run, []).append({
                    "QID": row.get("QID"),
                    "Query": row.get("Query"),
                    "Grammar": grammar,
                    "Model": model,
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
                
    # Save each execution's error logs next to its reviewed CSVs
    for name, errors_by_run in (("base_llm_errors.csv", base_llm_errors), ("judge_llm_errors.csv", judge_llm_errors)):
        for run, errors in errors_by_run.items():
            with open(out_root / run / name, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(errors[0].keys()))
                writer.writeheader()
                writer.writerows(errors)

    runs = sorted({csv_file.parent.parent.parent.name for csv_file in csv_files})
    st.toast(f"Successfully generated outputs to {', '.join(str(out_root / r) for r in runs)}", icon=":material/check_circle:")
