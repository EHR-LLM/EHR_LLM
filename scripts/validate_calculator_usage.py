#!/usr/bin/env python3
"""
Validate calculator usage after a run.
Verifies that calculator API calls were made for all samples in calculator mode.

Usage:
    python scripts/validate_calculator_usage.py
    python scripts/validate_calculator_usage.py --task meld
    python scripts/validate_calculator_usage.py --task child
"""

import json
import os
import sys
import argparse
from pathlib import Path
from collections import Counter


def get_task_samples(task_name: str, config_path: str = "configs/tasks/medagentbench.yaml") -> int:
    """Get number of samples for a task."""
    if not os.path.exists(config_path):
        return 0
    
    import yaml
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    if task_name in config:
        params = config[task_name].get('parameters', {})
        data_file = params.get('data_file', '')
        if os.path.exists(data_file):
            with open(data_file, 'r') as f:
                data = json.load(f)
                return len(data)
    
    return 0


def validate_calculator_usage(task_name: str = None, output_dir: str = "outputs"):
    """Validate calculator usage for a task or all tasks."""
    
    calc_log = os.path.join(output_dir, "calculator_calls.jsonl")
    
    if not os.path.exists(calc_log):
        print(f"[ERROR] Calculator log not found: {calc_log}")
        return False
    
    # Read all calculator calls
    all_calls = []
    with open(calc_log, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.strip():
                try:
                    all_calls.append(json.loads(line))
                except:
                    pass
    
    print("=== Calculator Usage Validation ===\n")
    
    if task_name:
        # Filter to specific task
        calls = [c for c in all_calls if c.get('task_name', '').startswith(task_name)]
        tasks_to_check = [task_name]
    else:
        # Check all tasks
        calls = all_calls
        task_names = set(c.get('task_name', 'unknown') for c in calls)
        tasks_to_check = sorted(task_names)
    
    if not calls:
        print("[ERROR] No calculator calls recorded!")
        return False
    
    # Analyze by task
    all_ok = True
    
    for task in tasks_to_check:
        task_calls = [c for c in calls if c.get('task_name') == task]
        
        if not task_calls:
            continue
        
        # Get score type and expected samples
        score_type = task_calls[0].get('score_type', task)
        expected_samples = get_task_samples(task)
        
        if expected_samples == 0:
            # Try to infer from calls
            sample_indices = set(c.get('sample_index', -1) for c in task_calls if c.get('sample_index') is not None)
            expected_samples = max(sample_indices) + 1 if sample_indices else 0
        
        actual_calls = len(task_calls)
        expected_calls = expected_samples
        
        print(f"Task: {task} ({score_type})")
        print(f"  Expected calculator calls: {expected_calls}")
        print(f"  Actual calculator calls:   {actual_calls}")
        
        # Analyze missing samples
        if expected_calls > 0:
            if actual_calls < expected_calls:
                missing = set(range(expected_calls)) - set(c.get('sample_index', -1) for c in task_calls)
                missing.discard(-1)
                if missing:
                    print(f"  [WARNING] Missing calculator calls for samples: {sorted(missing)[:10]}...")
                else:
                    print(f"  [WARNING] Mismatch: fewer calls than expected samples")
                all_ok = False
            elif actual_calls > expected_calls:
                # Check for multiple calls per sample
                sample_counts = Counter(c.get('sample_index') for c in task_calls)
                multi_call = [idx for idx, cnt in sample_counts.items() if cnt > 1]
                if multi_call:
                    print(f"  [WARNING] Multiple calculator calls for samples: {multi_call[:5]}...")
                all_ok = False
            else:
                print(f"  Status: OK")
        else:
            print(f"  Status: UNKNOWN (could not determine expected count)")
        
        print()
    
    # Summary
    total_calls = len(calls)
    unique_tasks = len(tasks_to_check)
    
    print(f"=== Summary ===")
    print(f"Total calculator calls: {total_calls}")
    print(f"Tasks checked: {unique_tasks}")
    print(f"Overall status: {'OK' if all_ok else 'MISMATCH'}")
    
    return all_ok


def main():
    parser = argparse.ArgumentParser(description='Validate calculator usage')
    parser.add_argument('--task', '-t', choices=['meld', 'fib4', 'child'], 
                        help='Specific task to validate')
    parser.add_argument('--output', '-o', default='outputs',
                        help='Output directory')
    args = parser.parse_args()
    
    success = validate_calculator_usage(args.task, args.output)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()