#!/usr/bin/env python3
"""
Export TA3 (Threshold Crossing + Date Detection) benchmark results to Excel
with detailed field-level comparison. Creates traceable per-case comparison
between expected and actual values for both the yes/no answer and the date.
"""

import json
import os
import re
import pandas as pd


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------

def load_ground_truth(data_file):
    """Load ground truth from test_data_ta3.json."""
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    ground_truth = {}
    for idx, case in enumerate(data):
        task_id = case.get('id', '')
        # Parse task_id: task_crossing_{biomarker}_{threshold}_{patient}[_neg]
        suffix = task_id.replace('task_crossing_', '')
        parts = suffix.split('_')

        # Detect _neg suffix
        is_negative = parts[-1] == 'neg'
        if is_negative:
            parts = parts[:-1]

        # Patient is the last part (Sxxxxxxx)
        patient = parts[-1] if parts else ''
        biomarker = parts[0] if parts else ''
        threshold = '_'.join(parts[1:-1]) if len(parts) > 2 else ''

        sol = case.get('sol', [])
        expected_answer = str(sol[0]).strip().lower() if sol else None
        expected_date = str(sol[1]).strip() if isinstance(sol, list) and len(sol) >= 2 else None

        ground_truth[idx] = {
            'task_id': task_id,
            'patient_id': case.get('eval_MRN', patient),
            'biomarker': biomarker.upper(),
            'threshold': threshold.replace('p', '.'),
            'is_negative': is_negative,
            'instruction': case.get('instruction', ''),
            'expected_answer': expected_answer,
            'expected_date': expected_date,
        }
    return ground_truth


# ---------------------------------------------------------------------------
# Result loaders
# ---------------------------------------------------------------------------

def load_runs_jsonl(runs_file):
    """Load actual results from runs.jsonl."""
    results = []
    if not os.path.exists(runs_file):
        return results
    with open(runs_file, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.strip():
                try:
                    results.append(json.loads(line))
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


# ---------------------------------------------------------------------------
# TA3-specific parsing  (mirrors refsol._parse_ta3_answer)
# ---------------------------------------------------------------------------

def parse_ta3_result(result_str):
    """
    Parse the result string from agent output for TA3 tasks.
    Returns (answer, date) tuple where answer is 'yes'/'no'/None
    and date is a YYYY-MM-DD string or None.
    """
    if result_str is None:
        return (None, None)

    s = str(result_str).strip()

    # Strip FINISH(...) wrapper
    m = re.match(r"FINISH\(\s*(.*?)\s*\)$", s, re.DOTALL)
    if m:
        s = m.group(1).strip()

    # Try JSON list parsing
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            answer = str(parsed[0]).strip().lower() if len(parsed) >= 1 else None
            date_val = str(parsed[1]).strip() if len(parsed) >= 2 else None
            return (answer, date_val)
        if isinstance(parsed, str):
            return (parsed.strip().lower(), None)
    except (json.JSONDecodeError, TypeError):
        pass

    # Manual bracketed list: ["yes","2023-01-20"]
    list_match = re.match(
        r'\[\s*["\']?(yes|no)["\']?\s*(?:,\s*["\']?(\d{4}-\d{2}-\d{2})["\']?\s*)?\]',
        s, re.IGNORECASE
    )
    if list_match:
        return (list_match.group(1).lower(), list_match.group(2))

    # Plain text
    s_lower = s.strip("[]\"' ").lower()
    if s_lower in ("yes", "no"):
        return (s_lower, None)

    return (None, None)


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def compare_answer(expected, actual):
    """Compare yes/no answer strings."""
    if expected is None or expected == '':
        return None if (actual is None or actual == '') else False
    if actual is None or actual == '':
        return False
    return str(expected).strip().lower() == str(actual).strip().lower()


def compare_date(expected_answer, expected_date, actual_date):
    """
    Compare dates. Only meaningful when expected_answer == 'yes' and a date
    is expected.  For negative tasks (no date expected) we return True if
    answer was correct.
    """
    if expected_answer != 'yes' or expected_date is None:
        return None  # not applicable for negative tasks
    if actual_date is None:
        return False
    return str(expected_date).strip() == str(actual_date).strip()


# ---------------------------------------------------------------------------
# Deduplication (same logic as TA1)
# ---------------------------------------------------------------------------

def deduplicate_df(df):
    """Deduplicate rows keeping preferred status, then last occurrence."""
    def status_priority(status):
        if status == 'completed':
            return 2
        elif status == 'error':
            return 1
        return 0

    df = df.copy()
    df['_status_priority'] = df['output_status'].apply(status_priority)
    df['_row_num'] = range(len(df))
    df = df.sort_values(['agent', 'replicate', 'case_index',
                         '_status_priority', '_row_num'])
    df = df.drop_duplicates(subset=['agent', 'replicate', 'case_index'],
                            keep='last')
    df = df.drop(columns=['_status_priority', '_row_num'])
    df = df.sort_values(['agent', 'replicate', 'case_index'])
    return df


# ---------------------------------------------------------------------------
# Main export
# ---------------------------------------------------------------------------

def export_ta3_to_excel(project_path, output_file):
    """Export TA3 threshold-crossing + date-detection results to Excel."""
    print(f"Exporting TA3 from {project_path}...")

    outputs_dir = os.path.join(project_path, 'outputs_TA3')
    if not os.path.exists(outputs_dir):
        print(f"  No outputs_TA3 directory found in {project_path}")
        return None

    # Find the benchmark sub-directory (e.g. MedAgentBenchv1)
    output_subdirs = [d for d in os.listdir(outputs_dir)
                      if os.path.isdir(os.path.join(outputs_dir, d))]
    if not output_subdirs:
        print(f"  No subdirectories in {outputs_dir}")
        return None

    bench_dir = os.path.join(outputs_dir, output_subdirs[0])
    print(f"  Using benchmark directory: {bench_dir}")

    # Load ground truth
    gt_file = os.path.join(project_path, 'data/medagentbench/test_data_ta3.json')
    ground_truth = load_ground_truth(gt_file)
    print(f"  Loaded {len(ground_truth)} ground truth entries")

    agents = [
        'gpt-5-mini', 'gemini-3.1-flash-lite', 'claude-haiku-4.5',
        'xiaomi-mimo-v2-pro', 'z-ai-glm-5', 'gemma-3-27b-it',
        'nemotron-3-nano-30b', 'gpt-oss-20b',
    ]

    all_rows = []

    for agent in agents:
        agent_dir = os.path.join(bench_dir, agent)
        if not os.path.exists(agent_dir):
            # Try alternative directory names
            for alt_name in os.listdir(bench_dir):
                if alt_name == agent:
                    agent_dir = os.path.join(bench_dir, alt_name)
                    break
        if not os.path.exists(agent_dir):
            print(f"  Agent directory not found: {agent}")
            continue

        print(f"  Processing {agent}...")

        for rep_dir in sorted(os.listdir(agent_dir)):
            rep_path = os.path.join(agent_dir, rep_dir)
            if not os.path.isdir(rep_path):
                continue
            if 'replicate' not in rep_dir.lower():
                continue
            try:
                replicate = int(''.join(filter(str.isdigit, rep_dir)))
            except ValueError:
                replicate = 1

            ta3_dir = os.path.join(rep_path, 'ta3-std')
            if not os.path.exists(ta3_dir):
                continue

            runs_file = os.path.join(ta3_dir, 'runs.jsonl')
            overall_file = os.path.join(ta3_dir, 'overall.json')

            # Load & merge results
            runs_results = load_runs_jsonl(runs_file)
            overall_results = load_overall_json(overall_file)

            runs_index_map = {r.get('index'): r for r in runs_results}
            for oe in overall_results:
                idx = oe.get('index')
                if idx is not None and idx not in runs_index_map:
                    oe['agent'] = agent
                    oe['replicate'] = replicate
                    runs_results.append(oe)

            for result in runs_results:
                index = result.get('index')
                if index not in ground_truth:
                    continue

                expected = ground_truth[index]
                output_data = result.get('output', {})
                actual_result_str = output_data.get('result')
                status = output_data.get('status', 'unknown')

                agent_answer, agent_date = parse_ta3_result(actual_result_str)

                answer_ok = compare_answer(expected['expected_answer'],
                                           agent_answer)
                date_ok = compare_date(expected['expected_answer'],
                                       expected['expected_date'],
                                       agent_date)

                # Fully correct: answer correct AND (date correct or N/A)
                if answer_ok and (date_ok is True or date_ok is None):
                    fully_correct = True
                else:
                    fully_correct = False

                row = {
                    'score_type': 'TA3_Crossing',
                    'agent': agent,
                    'replicate': replicate,
                    'case_index': index,

                    # Task identification
                    'task_id': expected['task_id'],
                    'patient_id': expected['patient_id'],
                    'biomarker': expected['biomarker'],
                    'threshold': expected['threshold'],
                    'is_negative_task': expected['is_negative'],
                    'instruction': expected['instruction'],

                    # Answer comparison
                    'answer_expected': expected['expected_answer'],
                    'answer_actual': agent_answer,
                    'answer_correct': answer_ok,

                    # Date comparison
                    'date_expected': expected['expected_date'],
                    'date_actual': agent_date,
                    'date_correct': date_ok,

                    # Overall
                    'fully_correct': fully_correct,

                    # Raw output
                    'answer_raw': actual_result_str,

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
        print("  No data rows found!")
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os as _os
    project_path = _os.path.dirname(_os.path.abspath(__file__))

    analysis_dir = os.path.join(project_path, "analysis")
    os.makedirs(analysis_dir, exist_ok=True)

    ta3_output = os.path.join(analysis_dir, "benchmark_traceability_ta3.xlsx")
    ta3_output_dedup = os.path.join(analysis_dir, "benchmark_traceability_ta3_deduplicated.xlsx")

    print("=" * 60)
    print("Exporting TA3 (Threshold Crossing + Date) benchmark results...")
    print("=" * 60)
    df = export_ta3_to_excel(project_path, ta3_output)

    if df is not None:
        print("\n" + "=" * 60)
        print("Creating deduplicated export...")
        print("=" * 60)
        df_dedup = deduplicate_df(df)
        df_dedup.to_excel(ta3_output_dedup, index=False)
        print(f"  TA3 deduplicated: {len(df_dedup)} rows (from {len(df)})")

        print("\n" + "=" * 60)
        print("Export complete!")
        print(f"  TA3 raw:   {ta3_output}")
        print(f"  TA3 dedup: {ta3_output_dedup}")
        print("=" * 60)
