import pandas as pd
import numpy as np
from scipy.stats import norm, t
import os

df = pd.read_csv('outputs/grammar_eval/combined/scores_all_evaluations.csv')

# Ensure we have standard names
if 'Eval Score' not in df.columns and 'Run_Overall_Score' in df.columns:
    df.rename(columns={'Run_Overall_Score': 'Eval Score', 'Run_Supported_Score': 'Supported_Score'}, inplace=True)

def compute_parametric_ci(sample, confidence_level=0.95):
    sample = np.array(sample)
    sample = sample[~np.isnan(sample)]
    if len(sample) == 0:
        return np.nan, np.nan
    alpha = 1 - confidence_level
    mean = float(np.mean(sample))
    std = float(np.std(sample, ddof=1)) if len(sample) > 1 else 0.0
    n = len(sample)
    if n > 30:
        z = norm.ppf(1 - alpha / 2)
        h = z * std / np.sqrt(n)
    else:
        t_value = t.ppf(1 - alpha / 2, n - 1)
        h = t_value * std / np.sqrt(n)
    return mean - h, mean + h

def format_ci(ci_tuple):
    if pd.isna(ci_tuple[0]) or pd.isna(ci_tuple[1]):
        return ""
    return f"[{ci_tuple[0]:.4f}, {ci_tuple[1]:.4f}]"

# Step 1: Median over executions for each Query
# This gives the 45 elements (or fewer if some failed) per model/grammar/criterion
mmqc_cols = ['Grammar', 'Model', 'Thinking', 'Query ID', 'Query', 'Criterion ID', 'Criterion']
# scores_by_model_query_criterion
mmqc_df = df.groupby(mmqc_cols, dropna=False)[['Eval Score', 'Supported_Score']].median().reset_index()
mmqc_df.rename(columns={'Eval Score': 'Median_Score', 'Supported_Score': 'Median_Supported_Score'}, inplace=True)

# Let's count executions per query
runs_per_query = df.groupby(mmqc_cols, dropna=False).size().reset_index(name='Total_Runs')
mmqc_df = pd.merge(mmqc_df, runs_per_query, on=mmqc_cols)

# We can also compute CI over the runs for each query if needed, but user said "do the CI over the medians, giving 45 total elements"
# So CI over runs might not be what he wants, or we can just leave it out of mmqc_df.

def save_csv_rounded(df, path):
    num_cols = df.select_dtypes(include=['float64', 'float32']).columns
    df[num_cols] = df[num_cols].round(4)
    df.to_csv(path, index=False)

save_csv_rounded(mmqc_df, 'outputs/grammar_eval/combined/scores_by_model_query_criterion.csv')

# scores_by_model_query
# Aggregate over Criteria (usually just one overall criterion per grammar, but let's be safe)
mmq_cols = ['Grammar', 'Model', 'Thinking', 'Query ID', 'Query']
mmq_df = df.groupby(mmq_cols, dropna=False)[['Eval Score', 'Supported_Score']].median().reset_index()
mmq_df.rename(columns={'Eval Score': 'Median_Score', 'Supported_Score': 'Median_Supported_Score'}, inplace=True)
save_csv_rounded(mmq_df, 'outputs/grammar_eval/combined/scores_by_model_query.csv')

# Step 2: Aggregate over the 45 queries (Medians)
def aggregate_over_queries(group_df, group_cols):
    res = []
    for name, group in group_df.groupby(group_cols, dropna=False):
        name_tuple = name if isinstance(name, tuple) else (name,)
        row = dict(zip(group_cols, name_tuple))
        
        scores = group['Median_Score'].values
        supported = group['Median_Supported_Score'].values
        
        row['Queries_Evaluated'] = len(scores)
        row['Mean_of_Medians'] = np.mean(scores)
        row['Std_of_Medians'] = np.std(scores, ddof=1) if len(scores) > 1 else 0.0
        
        ci = compute_parametric_ci(scores)
        row['95% CI (Score)'] = format_ci(ci)
        
        # Supported
        supp_valid = supported[~np.isnan(supported)]
        if len(supp_valid) > 0:
            row['Supported_Mean_of_Medians'] = np.mean(supp_valid)
            ci_supp = compute_parametric_ci(supp_valid)
            row['95% CI (Supported)'] = format_ci(ci_supp)
        else:
            row['Supported_Mean_of_Medians'] = np.nan
            row['95% CI (Supported)'] = ""
            
        res.append(row)
    return pd.DataFrame(res)

def save_csv_rounded(df, path):
    num_cols = df.select_dtypes(include=['float64', 'float32']).columns
    df[num_cols] = df[num_cols].round(4)
    df.to_csv(path, index=False)

# scores_by_model
mm_cols = ['Grammar', 'Model', 'Thinking']
by_model = aggregate_over_queries(mmq_df, mm_cols)
save_csv_rounded(by_model, 'outputs/grammar_eval/combined/scores_by_model.csv')

# scores_by_criterion
mmc_cols = ['Grammar', 'Model', 'Thinking', 'Criterion ID', 'Criterion']
by_criterion = aggregate_over_queries(mmqc_df, mmc_cols)
save_csv_rounded(by_criterion, 'outputs/grammar_eval/combined/scores_by_criterion.csv')

# scores_by_query
q_cols = ['Grammar', 'Query ID', 'Query']
# Aggregate over Models for each query
by_query = aggregate_over_queries(mmq_df, q_cols)
by_query.rename(columns={'Queries_Evaluated': 'Models_Evaluated'}, inplace=True)
save_csv_rounded(by_query, 'outputs/grammar_eval/combined/scores_by_query.csv')

# scores_by_query_criterion
qc_cols = ['Grammar', 'Query ID', 'Query', 'Criterion ID', 'Criterion']
by_query_criterion = aggregate_over_queries(mmqc_df, qc_cols)
by_query_criterion.rename(columns={'Queries_Evaluated': 'Models_Evaluated'}, inplace=True)
save_csv_rounded(by_query_criterion, 'outputs/grammar_eval/combined/scores_by_query_criterion.csv')

print("Aggregated CSVs generated successfully using medians.")
