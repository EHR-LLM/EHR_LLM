#!/usr/bin/env python3
"""Export FIB-4 results (no calculator) to Excel."""

import json
import os
import pandas as pd

PROJECT_PATH = r"C:\Users\sanch\all abstract\no calculator"
OUTPUT_PATH = r"C:\Users\sanch\all abstract\no calculator\outputs\FIB4Bench"
OUTPUT_FILE_RAW = r"C:\Users\sanch\all abstract\no calculator\analysis\fib4_traceability_raw.xlsx"
OUTPUT_FILE_DEDUP = r"C:\Users\sanch\all abstract\no calculator\analysis\fib4_traceability.xlsx"


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
ground_truth_file = os.path.join(PROJECT_PATH, "data/medagentbench/test_data_fib4.json")
with open(ground_truth_file, 'r', encoding='utf-8') as f:
    fib4_data = json.load(f)

ground_truth = {}
for idx, case in enumerate(fib4_data):
    sol = case.get('sol', {})
    ground_truth[idx] = {
        'patient_id_expected': sol.get('expected_patient_id'),
        'date_expected': sol.get('expected_date'),
        'age_expected': sol.get('expected_age'),
        'ast_raw_expected': sol.get('expected_ast_raw'),
        'alt_raw_expected': sol.get('expected_alt_raw'),
        'platelets_raw_expected': sol.get('expected_platelets_raw'),
        'fib4_score_expected': sol.get('expected_fib4'),
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
        task_path = os.path.join(agent_path, replicate_dir, 'fib4-std')
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
        'age_expected': gt.get('age_expected'),
        'age_actual': actual.get('age'),
        'age_correct': gt.get('age_expected') == actual.get('age'),
        'ast_raw_expected': gt.get('ast_raw_expected'),
        'ast_raw_actual': actual.get('ast_raw'),
        'ast_raw_correct': gt.get('ast_raw_expected') == actual.get('ast_raw'),
        'alt_raw_expected': gt.get('alt_raw_expected'),
        'alt_raw_actual': actual.get('alt_raw'),
        'alt_raw_correct': gt.get('alt_raw_expected') == actual.get('alt_raw'),
        'platelets_raw_expected': gt.get('platelets_raw_expected'),
        'platelets_raw_actual': actual.get('platelets_raw'),
        'platelets_raw_correct': gt.get('platelets_raw_expected') == actual.get('platelets_raw'),
        'fib4_score_expected': gt.get('fib4_score_expected'),
        'fib4_score_actual': actual.get('fib4_score'),
        'fib4_score_correct': gt.get('fib4_score_expected') == actual.get('fib4_score'),
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
    correct_fib4 = agent_df['fib4_score_correct'].sum()
    print(f"{agent}: {correct_fib4}/{total} FIB-4 correct ({100*correct_fib4/total:.1f}%)")