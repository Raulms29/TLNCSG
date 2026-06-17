
import os, shutil, glob
import pandas as pd
from datetime import datetime
import re

ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out_dir = f'outputs/summary/{ts}'
os.makedirs(out_dir, exist_ok=True)

dir1 = 'outputs/summary/archive_04-2026_to_06-2026/20260429_143826'
dir2 = 'outputs/summary/archive_04-2026_to_06-2026/20260501_113658'

print(f'Combining {dir1} and {dir2} into {out_dir}')

for d in [dir1, dir2]:
    for item in os.listdir(d):
        p = os.path.join(d, item)
        if os.path.isdir(p):
            shutil.copytree(p, os.path.join(out_dir, item), dirs_exist_ok=True)

df_all_1 = pd.read_csv(os.path.join(dir1, 'model_summary_all_partial_20260429_143826.csv'))
df_all_2 = pd.read_csv(os.path.join(dir2, 'model_summary_all_20260501_113658.csv'))
df_all_comb = pd.concat([df_all_1, df_all_2], ignore_index=True)
df_all_comb.to_csv(os.path.join(out_dir, f'model_summary_all_{ts}.csv'), index=False)

df_comp_1 = pd.read_csv(os.path.join(dir1, 'model_summary_models_comparison_partial_20260429_143826.csv'))
df_comp_2 = pd.read_csv(os.path.join(dir2, 'model_summary_models_comparison_20260501_113658.csv'))
df_comp_comb = pd.concat([df_comp_1, df_comp_2], ignore_index=True)
df_comp_comb.to_csv(os.path.join(out_dir, f'model_summary_models_comparison_{ts}.csv'), index=False)

unique_queries = df_all_comb[['Query ID', 'Query Text']].drop_duplicates()
for _, row in unique_queries.iterrows():
    q_num = row['Query ID']
    q_str = row['Query Text']
    q_df = df_all_comb[df_all_comb['Query ID'] == q_num]
    q_name = re.sub(r'[^a-zA-Z0-9]', '_', str(q_str))
    q_prefix = f'{q_num}_{q_name[:30]}' 
    q_df.to_csv(os.path.join(out_dir, f'query_summary_{q_prefix}_{ts}.csv'), index=False)

print('Done creating', out_dir)

