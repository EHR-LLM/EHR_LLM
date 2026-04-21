#!/usr/bin/env python3
"""
Validate and repair consistency between runs.jsonl and overall.json.
Ensures that every index processed by overall is also in runs.jsonl.

This script detects the following issues:
1. Index present in overall but NOT in runs.jsonl - logs warning, can attempt repair
2. Index present in runs.jsonl but NOT in overall - logs warning
3. overall.json missing entirely - logs critical error

Usage:
    python validate_runs_overall_consistency.py [--base PATH] [--repair]
"""

import json
import os
import sys
import argparse
from pathlib import Path

def get_indexes_from_runs(runs_path: str) -> set:
    """Extract indexes from runs.jsonl file."""
    indexes = set()
    if not os.path.exists(runs_path):
        return indexes
    
    with open(runs_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.strip():
                try:
                    data = json.loads(line)
                    idx = data.get('index')
                    if idx is not None:
                        indexes.add(idx)
                except json.JSONDecodeError:
                    continue
    return indexes


def get_indexes_from_overall(overall_path: str) -> set:
    """Extract indexes from overall.json file (from custom.raw_results)."""
    indexes = set()
    if not os.path.exists(overall_path):
        return indexes
    
    with open(overall_path, 'r', encoding='utf-8', errors='replace') as f:
        try:
            overall = json.load(f)
            if 'custom' in overall and 'raw_results' in overall['custom']:
                for r in overall['custom']['raw_results']:
                    idx = r.get('index')
                    if idx is not None:
                        indexes.add(idx)
        except json.JSONDecodeError:
            pass
    return indexes


def repair_missing_runs_entry(overall_path: str, runs_path: str, missing_index: int) -> bool:
    """
    Attempt to repair a missing runs.jsonl entry by reading from overall.json.
    Returns True if repair was successful.
    """
    if not os.path.exists(overall_path):
        return False
    
    with open(overall_path, 'r', encoding='utf-8', errors='replace') as f:
        try:
            overall = json.load(f)
        except json.JSONDecodeError:
            return False
    
    # Find the entry in overall
    target_entry = None
    if 'custom' in overall and 'raw_results' in overall['custom']:
        for r in overall['custom']['raw_results']:
            if r.get('index') == missing_index:
                target_entry = r
                break
    
    if target_entry is None:
        return False
    
    # Extract replicate and agent from path
    # Path structure: outputs/{bench}/{agent}/replicate_{n}/{task}/overall.json
    parts = overall_path.split(os.sep)
    agent = None
    replicate = None
    task = None
    
    for i, part in enumerate(parts):
        if part.startswith('replicate_'):
            replicate = int(part.replace('replicate_', ''))
        if agent is None and 'Bench' in part:
            # prev part should be agent
            if i > 0:
                agent = parts[i - 1]
        if task is None and '.json' in part:
            task = parts[i].replace('.json', '').replace('overall', '').strip('/')
    
    if agent is None or replicate is None:
        return False
    
    # Get the task from overall.json structure
    task = None
    for key in ['meld-std', 'fib4-std', 'child-pugh-std']:
        path_check = os.path.join(os.path.dirname(overall_path), key)
        if os.path.exists(path_check):
            task = key
            break
    
    # Build runs entry from overall entry
    runs_entry = {
        'index': missing_index,
        'replicate': replicate,
        'agent': agent,
        'task': task,
    }
    
    # Add output info from overall entry
    runs_entry['output'] = {
        'status': target_entry.get('status', 'unknown'),
        'result': target_entry.get('result'),
    }
    runs_entry['error'] = None
    runs_entry['info'] = None
    
    # Add timestamp
    import time
    timestamp = int(time.time() * 1000)
    runs_entry['time'] = {
        'timestamp': timestamp,
        'str': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Append to runs.jsonl
    runs_exists = os.path.exists(runs_path)
    with open(runs_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(runs_entry, ensure_ascii=False) + '\n')
    
    return True


def validate_folder(folder_path: str, task_name: str, repair: bool = False) -> dict:
    """Validate all subfolders in a benchmark folder."""
    stats = {
        'total': 0,
        'missing_in_runs': 0,
        'missing_in_overall': 0,
        'overall_missing': 0,
        'fixed': 0,
    }
    
    if not os.path.exists(folder_path):
        return stats
    
    for agent in os.listdir(folder_path):
        agent_path = os.path.join(folder_path, agent)
        if not os.path.isdir(agent_path):
            continue
        
        for rep_dir in os.listdir(agent_path):
            if not rep_dir.startswith('replicate_'):
                continue
            replicate = rep_dir.replace('replicate_', '')
            
            runs_path = os.path.join(agent_path, rep_dir, task_name, 'runs.jsonl')
            overall_path = os.path.join(agent_path, rep_dir, task_name, 'overall.json')
            
            stats['total'] += 1
            
            runs_indexes = get_indexes_from_runs(runs_path)
            overall_indexes = get_indexes_from_overall(overall_path)
            
            # Check for missing indexes
            missing_in_runs = overall_indexes - runs_indexes
            missing_in_overall = runs_indexes - overall_indexes
            
            if not os.path.exists(overall_path) and runs_indexes:
                print(f'  [CRITICAL] {agent}/replicate_{replicate}: overall.json MISSING')
                stats['overall_missing'] += 1
            
            if missing_in_runs:
                print(f'  [WARN] {agent}/replicate_{replicate}: missing in runs.jsonl = {sorted(missing_in_runs)}')
                stats['missing_in_runs'] += len(missing_in_runs)
                
                if repair:
                    for idx in missing_in_runs:
                        if repair_missing_runs_entry(overall_path, runs_path, idx):
                            print(f'    [REPAIRED] Added index {idx} to runs.jsonl')
                            stats['fixed'] += 1
            
            if missing_in_overall:
                print(f'  [WARN] {agent}/replicate_{replicate}: missing in overall = {sorted(missing_in_overall)}')
                stats['missing_in_overall'] += len(missing_in_overall)
    
    return stats


def main():
    parser = argparse.ArgumentParser(description='Validate runs.jsonl and overall.json consistency')
    parser.add_argument('--base', '-b', type=str, default='outputs',
        help='Base output folder to validate')
    parser.add_argument('--repair', '-r', action='store_true',
        help='Attempt to repair missing entries')
    args = parser.parse_args()
    
    print(f"=== Validating {args.base} ===")
    print()
    
    all_stats = {'missing_in_runs': 0, 'missing_in_overall': 0, 'overall_missing': 0, 'fixed': 0}
    
    # Check each benchmark folder
    for bench_folder in ['MELDBench', 'FIB4Bench', 'ChildPughBench']:
        folder_path = os.path.join(args.base, bench_folder)
        if not os.path.exists(folder_path):
            continue
        
        if bench_folder == 'MELDBench':
            task = 'meld-std'
        elif bench_folder == 'FIB4Bench':
            task = 'fib4-std'
        else:
            task = 'child-pugh-std'
        
        print(f"Checking {bench_folder}...")
        stats = validate_folder(folder_path, task, args.repair)
        
        for k, v in stats.items():
            if k != 'total':
                all_stats[k] += v
    
    print()
    print(f"=== Summary ===")
    print(f"Missing in runs.jsonl (in overall only): {all_stats['missing_in_runs']}")
    print(f"Missing in overall (in runs only): {all_stats['missing_in_overall']}")
    print(f"Overall.json completely missing: {all_stats['overall_missing']}")
    if args.repair:
        print(f"Entries repaired: {all_stats['fixed']}")
    
    # Exit with error if issues found
    if all_stats['missing_in_runs'] > 0 or all_stats['overall_missing'] > 0:
        print()
        print("WARNING: Consistency issues detected!")
        sys.exit(1)
    else:
        print()
        print("SUCCESS: All outputs are consistent")
        sys.exit(0)


if __name__ == "__main__":
    main()