#!/usr/bin/env python3
"""Export Child-Pugh results (no calculator) to Excel."""

import json
import os
import pandas as pd

PROJECT_PATH = r"C:\Users\sanch\all abstract\no calculator"
OUTPUT_PATH = r"C:\Users\sanch\all abstract\no calculator\outputs\ChildPughBench"
OUTPUT_FILE_RAW = r"C:\Users\sanch\all abstract\no calculator\analysis\child_pugh_traceability_raw.xlsx"
OUTPUT_FILE_DEDUP = r"C:\Users\sanch\all abstract\no calculator\analysis\child_pugh_traceability_v2.xlsx"


def deduplicate_df(df):
    """Deduplicate rows keeping preferred status, then last occurrence."""
    def status_priority(status):
        if status == 'completed':
            return 2
        elif status == 'error':
            return 1
        else:
            return 0
    
    df = df.copy()
    df['_status_priority'] = df['output_status'].apply(status_priority)
    df['_row_num'] = range(len(df))
    
    df = df.sort_values(['agent', 'replicate', 'index', '_status_priority', '_row_num'])
    df = df.drop_duplicates(subset=['agent', 'replicate', 'index'], keep='last')
    df = df.drop(columns=['_status_priority', '_row_num'])
    df = df.sort_values(['agent', 'replicate', 'index'])
    return df


# Load ground truth
ground_truth_file = os.path.join(PROJECT_PATH, "data/medagentbench/test_data_child_pugh.json")
with open(ground_truth_file, 'r', encoding='utf-8') as f:
    child_pugh_data = json.load(f)

ground_truth = {}
for case in child_pugh_data:
    idx = case.get('id')
    sol = case.get('sol', {})
    ground_truth[idx] = {
        'patient_id_expected': sol.get('expected_patient_id'),
        'date_expected': sol.get('expected_date'),
        'bilirubin_raw_expected': sol.get('expected_bilirubin_raw'),
        'albumin_raw_expected': sol.get('expected_albumin_raw'),
        'inr_raw_expected': sol.get('expected_inr_raw'),
        'ascites_present_same_day_expected': sol.get('expected_ascites_present_same_day'),
        'encephalopathy_present_same_day_expected': sol.get('expected_encephalopathy_present_same_day'),
        'bilirubin_points_expected': sol.get('expected_bilirubin_points'),
        'albumin_points_expected': sol.get('expected_albumin_points'),
        'inr_points_expected': sol.get('expected_inr_points'),
        'ascites_points_expected': sol.get('expected_ascites_points'),
        'encephalopathy_points_expected': sol.get('expected_encephalopathy_points'),
        'child_pugh_score_expected': sol.get('expected_child_pugh_score'),
    }

# Find all runs
results = []
for agent in os.listdir(OUTPUT_PATH):
    agent_path = os.path.join(OUTPUT_PATH, agent)
    if not os.path.isdir(agent_path):
        continue
    
    for replicate_dir in os.listdir(agent_path):
        if not replicate_dir.startswith('replicate_'):
            continue
        
        replicate = int(replicate_dir.replace('replicate_', ''))
        task_path = os.path.join(agent_path, replicate_dir, 'child-pugh-std')
        runs_file = os.path.join(task_path, 'runs.jsonl')
        
        if not os.path.exists(runs_file):
            continue
        
        with open(runs_file, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        results.append((data, replicate, agent))
                    except json.JSONDecodeError:
                        continue

print(f"Found {len(results)} results")

# Build DataFrame
rows = []
for data, replicate, agent in results:
    idx = data.get('index')
    gt = ground_truth.get(idx, {})
    
    output = data.get('output', {})
    result_str = output.get('result', '')
    output_status = output.get('status', 'unknown')
    
    # Parse actual result
    actual = {}
    try:
        if result_str:
            actual = json.loads(result_str)
    except:
        pass
    
    row = {
        'agent': agent,
        'replicate': replicate,
        'index': idx,
        'output_status': output_status,
        'patient_id_expected': gt.get('patient_id_expected'),
        'patient_id_actual': actual.get('patient_id'),
        'patient_id_correct': gt.get('patient_id_expected') == actual.get('patient_id'),
        'date_expected': str(gt.get('date_expected')),
        'date_actual': actual.get('date'),
        'date_correct': str(gt.get('date_expected')) == actual.get('date'),
        'bilirubin_raw_expected': gt.get('bilirubin_raw_expected'),
        'bilirubin_raw_actual': actual.get('bilirubin_raw'),
        'bilirubin_raw_correct': gt.get('bilirubin_raw_expected') == actual.get('bilirubin_raw'),
        'albumin_raw_expected': gt.get('albumin_raw_expected'),
        'albumin_raw_actual': actual.get('albumin_raw'),
        'albumin_raw_correct': gt.get('albumin_raw_expected') == actual.get('albumin_raw'),
        'inr_raw_expected': gt.get('inr_raw_expected'),
        'inr_raw_actual': actual.get('inr_raw'),
        'inr_raw_correct': gt.get('inr_raw_expected') == actual.get('inr_raw'),
        'ascites_present_same_day_expected': gt.get('ascites_present_same_day_expected'),
        'ascites_present_same_day_actual': actual.get('ascites_present_same_day'),
        'ascites_present_same_day_correct': gt.get('ascites_present_same_day_expected') == actual.get('ascites_present_same_day'),
        'encephalopathy_present_same_day_expected': gt.get('encephalopathy_present_same_day_expected'),
        'encephalopathy_present_same_day_actual': actual.get('encephalopathy_present_same_day'),
        'encephalopathy_present_same_day_correct': gt.get('encephalopathy_present_same_day_expected') == actual.get('encephalopathy_present_same_day'),
        'bilirubin_points_expected': gt.get('bilirubin_points_expected'),
        'bilirubin_points_actual': actual.get('bilirubin_points'),
        'bilirubin_points_correct': gt.get('bilirubin_points_expected') == actual.get('bilirubin_points'),
        'albumin_points_expected': gt.get('albumin_points_expected'),
        'albumin_points_actual': actual.get('albumin_points'),
        'albumin_points_correct': gt.get('albumin_points_expected') == actual.get('albumin_points'),
        'inr_points_expected': gt.get('inr_points_expected'),
        'inr_points_actual': actual.get('inr_points'),
        'inr_points_correct': gt.get('inr_points_expected') == actual.get('inr_points'),
        'ascites_points_expected': gt.get('ascites_points_expected'),
        'ascites_points_actual': actual.get('ascites_points'),
        'ascites_points_correct': gt.get('ascites_points_expected') == actual.get('ascites_points'),
        'encephalopathy_points_expected': gt.get('encephalopathy_points_expected'),
        'encephalopathy_points_actual': actual.get('encephalopathy_points'),
        'encephalopathy_points_correct': gt.get('encephalopathy_points_expected') == actual.get('encephalopathy_points'),
        'child_pugh_score_expected': gt.get('child_pugh_score_expected'),
        'child_pugh_score_actual': actual.get('child_pugh_score'),
        'child_pugh_score_correct': gt.get('child_pugh_score_expected') == actual.get('child_pugh_score'),
    }
    rows.append(row)

df = pd.DataFrame(rows)
df = df.sort_values(['agent', 'replicate', 'index'])

os.makedirs(os.path.dirname(OUTPUT_FILE_RAW), exist_ok=True)

# Save raw version
df.to_excel(OUTPUT_FILE_RAW, index=False)
print(f"Saved {len(df)} rows to {OUTPUT_FILE_RAW}")

# Save deduplicated version
df_dedup = deduplicate_df(df)
df_dedup.to_excel(OUTPUT_FILE_DEDUP, index=False)
print(f"Saved {len(df_dedup)} rows (deduplicated) to {OUTPUT_FILE_DEDUP}")

# Summary
print("\n=== Summary by Agent (Deduplicated) ===")
for agent in df_dedup['agent'].unique():
    agent_df = df_dedup[df_dedup['agent'] == agent]
    total = len(agent_df)
    correct_score = agent_df['child_pugh_score_correct'].sum()
    print(f"{agent}: {correct_score}/{total} Child-Pugh score correct ({100*correct_score/total:.1f}%)")