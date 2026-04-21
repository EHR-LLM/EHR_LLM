#!/usr/bin/env python3
"""Export MELD results (no calculator) to Excel."""

import json
import os
import pandas as pd

PROJECT_PATH = r"C:\Users\sanch\all abstract\no calculator"
OUTPUT_PATH = r"C:\Users\sanch\all abstract\no calculator\outputs\MELDBench"
OUTPUT_FILE_RAW = r"C:\Users\sanch\all abstract\no calculator\analysis\meld_traceability_raw.xlsx"
OUTPUT_FILE_DEDUP = r"C:\Users\sanch\all abstract\no calculator\analysis\meld_traceability_v2.xlsx"


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
ground_truth_file = os.path.join(PROJECT_PATH, "data/medagentbench/test_data_meld.json")
with open(ground_truth_file, 'r', encoding='utf-8') as f:
    meld_data = json.load(f)

# Map by id (e.g., "meld_1") or index
ground_truth = {}
for case in meld_data:
    case_id = case.get('id', '')
    # Extract index from id like "meld_1" -> 0
    idx = int(case_id.replace('meld_', '')) - 1 if case_id.startswith('meld_') else case.get('id')
    sol = case.get('sol', {})
    ground_truth[idx] = {
        'patient_id_expected': sol.get('expected_patient_id'),
        'date_expected': sol.get('expected_date'),
        'bilirubin_raw_expected': sol.get('expected_bilirubin_raw'),
        'inr_raw_expected': sol.get('expected_inr_raw'),
        'creatinine_raw_expected': sol.get('expected_creatinine_raw'),
        'bilirubin_used_expected': sol.get('expected_bilirubin_used'),
        'inr_used_expected': sol.get('expected_inr_used'),
        'creatinine_used_expected': sol.get('expected_creatinine_used'),
        'meld_expected': sol.get('expected_meld'),
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
        task_path = os.path.join(agent_path, replicate_dir, 'meld-std')
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
        'inr_raw_expected': gt.get('inr_raw_expected'),
        'inr_raw_actual': actual.get('inr_raw'),
        'inr_raw_correct': gt.get('inr_raw_expected') == actual.get('inr_raw'),
        'creatinine_raw_expected': gt.get('creatinine_raw_expected'),
        'creatinine_raw_actual': actual.get('creatinine_raw'),
        'creatinine_raw_correct': gt.get('creatinine_raw_expected') == actual.get('creatinine_raw'),
        'meld_expected': gt.get('meld_expected'),
        'meld_actual': actual.get('meld_score'),
        'meld_correct': gt.get('meld_expected') == actual.get('meld_score'),
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
    correct_score = agent_df['meld_correct'].sum()
    print(f"{agent}: {correct_score}/{total} MELD score correct ({100*correct_score/total:.1f}%)")