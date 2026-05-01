#!/usr/bin/env python3
"""
Export TA1 (threshold) benchmark results to Excel with detailed field-level comparison.
Creates traceable per-case comparison between expected and actual values.
"""

import json
import os
import re
import pandas as pd
from datetime import datetime


def load_ground_truth(data_file):
    """Load ground truth from test data file."""
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    ground_truth = {}
    for idx, case in enumerate(data):
        task_id = case.get('id', '')
        # Parse task_id: task_threshold_{biomarker}_{threshold}_{patient}
        # e.g. task_threshold_alb_3p5_S0674240
        parts = task_id.replace('task_threshold_', '').split('_')
        # biomarker is first part, patient is last (Sxxxxxxx), threshold is middle
        patient = parts[-1] if parts else ''
        biomarker = parts[0] if parts else ''
        threshold = '_'.join(parts[1:-1]) if len(parts) > 2 else ''

        # Extract expected answer from sol
        sol = case.get('sol', [])
        expected_answer = sol[0] if sol else None

        ground_truth[idx] = {
            'task_id': task_id,
            'patient_id': case.get('eval_MRN', patient),
            'biomarker': biomarker.upper(),
            'threshold': threshold.replace('p', '.'),
            'instruction': case.get('instruction', ''),
            'expected_answer': expected_answer,
        }
    return ground_truth


def load_runs_jsonl(runs_file):
    """Load actual results from runs.jsonl."""
    results = []
    if not os.path.exists(runs_file):
        return results

    with open(runs_file, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.strip():
                try:
                    data = json.loads(line)
                    results.append(data)
                except json.JSONDecodeError:
                    continue
    return results


def load_overall_json(overall_file):
    """Load results from overall.json to fill missing runs.jsonl entries."""
    results = []
    if not os.path.exists(overall_file):
        return results

    try:
        with open(overall_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        raw_results = data.get('custom', {}).get('raw_results', [])
        for entry in raw_results:
            results.append({
                'index': entry.get('index'),
                'replicate': None,
                'agent': None,
                'task': None,
                'error': None,
                'output': {
                    'result': entry.get('result'),
                    'status': entry.get('status', '').replace('SampleStatus.', '').lower()
                }
            })
    except (json.JSONDecodeError, IOError):
        pass
    return results


def parse_ta1_result(result_str):
    """Parse the result string from agent output for TA1 tasks.
    
    Expected format: '["yes"]' or '["no"]'
    """
    if not result_str:
        return None
    try:
        parsed = json.loads(result_str)
        if isinstance(parsed, list) and len(parsed) > 0:
            return str(parsed[0]).strip().lower()
    except (json.JSONDecodeError, TypeError):
        pass
    # Try plain string
    result_lower = result_str.strip().lower()
    if result_lower in ('yes', 'no'):
        return result_lower
    return None


def compare_values(expected, actual):
    """Compare two values for TA1 (simple string match)."""
    if expected is None or expected == '':
        if actual is None or actual == '':
            return None
        return False
    if actual is None or actual == '':
        return False
    return str(expected).strip().lower() == str(actual).strip().lower()


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

    df = df.sort_values(['agent', 'replicate', 'case_index', '_status_priority', '_row_num'])
    df = df.drop_duplicates(subset=['agent', 'replicate', 'case_index'], keep='last')
    df = df.drop(columns=['_status_priority', '_row_num'])
    df = df.sort_values(['agent', 'replicate', 'case_index'])
    return df


def export_ta1_to_excel(project_path, output_file):
    """Export TA1 threshold results to Excel."""
    print(f"Exporting TA1 from {project_path}...")

    outputs_dir = os.path.join(project_path, 'outputs_TA1')
    if not os.path.exists(outputs_dir):
        print(f"  No outputs_TA1 directory found in {project_path}")
        return

    # Find the benchmark subdirectory
    output_subdirs = [d for d in os.listdir(outputs_dir) if os.path.isdir(os.path.join(outputs_dir, d))]
    if not output_subdirs:
        print(f"  No subdirectories in {outputs_dir}")
        return

    bench_dir = os.path.join(outputs_dir, output_subdirs[0])
    print(f"  Using benchmark directory: {bench_dir}")

    # Load ground truth
    ground_truth = load_ground_truth(os.path.join(project_path, 'data/medagentbench/test_data_ta1.json'))
    print(f"  Loaded {len(ground_truth)} ground truth entries")

    # Agents to process
    agents = ['gpt-5-mini', 'gemini-3.1-flash-lite', 'claude-haiku-4.5',
              'xiaomi-mimo-v2-pro', 'z-ai-glm-5', 'gemma-3-27b-it',
              'nemotron-3-nano-30b', 'gpt-oss-20b']

    # Map old agent directory names to canonical names
    agent_dir_map = {
        'gpt-oss-20b-free': 'gpt-oss-20b',
    }

    all_rows = []

    for agent in agents:
        agent_dir = os.path.join(bench_dir, agent)
        if not os.path.exists(agent_dir):
            # Try alternative directory names
            for alt_name in os.listdir(bench_dir):
                if agent_dir_map.get(alt_name) == agent or alt_name == agent:
                    agent_dir = os.path.join(bench_dir, alt_name)
                    break

        if not os.path.exists(agent_dir):
            print(f"  Agent directory not found: {agent}")
            continue

        print(f"  Processing {agent}...")

        # Find replicate directories
        for rep_dir in sorted(os.listdir(agent_dir)):
            rep_path = os.path.join(agent_dir, rep_dir)
            if not os.path.isdir(rep_path):
                continue

            # Extract replicate number
            if 'replicate' in rep_dir.lower():
                try:
                    replicate = int(''.join(filter(str.isdigit, rep_dir)))
                except ValueError:
                    replicate = 1
            else:
                continue

            # Find ta1-std subdirectory
            ta1_dir = os.path.join(rep_path, 'ta1-std')
            if not os.path.exists(ta1_dir):
                continue

            runs_file = os.path.join(ta1_dir, 'runs.jsonl')
            overall_file = os.path.join(ta1_dir, 'overall.json')

            # Load results from runs.jsonl
            runs_results = load_runs_jsonl(runs_file)

            # Load results from overall.json to fill missing entries
            overall_results = load_overall_json(overall_file)

            # Build index to results map from runs.jsonl
            runs_index_map = {r.get('index'): r for r in runs_results}

            # Merge: add entries from overall.json that are missing in runs.jsonl
            for overall_entry in overall_results:
                idx = overall_entry.get('index')
                if idx is not None and idx not in runs_index_map:
                    overall_entry['agent'] = agent
                    overall_entry['replicate'] = replicate
                    runs_results.append(overall_entry)

            results = runs_results

            for result in results:
                index = result.get('index')
                if index not in ground_truth:
                    continue

                expected = ground_truth[index]
                output_data = result.get('output', {})
                actual_result_str = output_data.get('result')
                status = output_data.get('status', 'unknown')

                # Parse actual answer
                actual_answer = parse_ta1_result(actual_result_str)

                # Build row
                row = {
                    'score_type': 'TA1_Threshold',
                    'agent': agent,
                    'replicate': replicate,
                    'case_index': index,

                    # Task identification
                    'task_id': expected.get('task_id'),
                    'patient_id': expected.get('patient_id'),
                    'biomarker': expected.get('biomarker'),
                    'threshold': expected.get('threshold'),
                    'instruction': expected.get('instruction'),

                    # Expected vs Actual
                    'answer_expected': expected.get('expected_answer'),
                    'answer_actual': actual_answer,
                    'answer_raw': actual_result_str,

                    # Correctness
                    'answer_correct': compare_values(expected.get('expected_answer'), actual_answer),

                    # Status
                    'output_status': status,
                    'output_error': result.get('error'),
                    'output_was_null': actual_result_str is None,
                    'has_any_output': bool(actual_result_str),
                }

                all_rows.append(row)

    if all_rows:
        df = pd.DataFrame(all_rows)
        df.to_excel(output_file, index=False)
        print(f"  Saved {len(all_rows)} rows to {output_file}")
        return df
    else:
        print(f"  No data rows found!")
        return None


if __name__ == "__main__":
    import os as _os
    project_path = _os.path.dirname(_os.path.abspath(__file__))

    # Output files
    analysis_dir = os.path.join(project_path, "analysis")
    os.makedirs(analysis_dir, exist_ok=True)

    ta1_output = os.path.join(analysis_dir, "benchmark_traceability_ta1.xlsx")
    ta1_output_dedup = os.path.join(analysis_dir, "benchmark_traceability_ta1_deduplicated.xlsx")

    # Export TA1
    print("=" * 60)
    print("Exporting TA1 (Threshold) benchmark results...")
    print("=" * 60)
    df = export_ta1_to_excel(project_path, ta1_output)

    if df is not None:
        # Create deduplicated version
        print("\n" + "=" * 60)
        print("Creating deduplicated export...")
        print("=" * 60)
        df_dedup = deduplicate_df(df)
        df_dedup.to_excel(ta1_output_dedup, index=False)
        print(f"  TA1 deduplicated: {len(df_dedup)} rows (from {len(df)})")

        print("\n" + "=" * 60)
        print("Export complete!")
        print(f"  TA1 raw:   {ta1_output}")
        print(f"  TA1 dedup: {ta1_output_dedup}")
        print("=" * 60)
