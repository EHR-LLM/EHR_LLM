#!/usr/bin/env python3
"""
Run all scores (MELD, FIB-4, Child-Pugh) with all 8 models sequentially.

Usage:
    python run_all_scores.py                    # Runs all 3 scores with all 8 models
    python run_all_scores.py --task meld        # Runs only MELD score
    python run_all_scores.py --task fib4       # Runs only FIB-4 score
    python run_all_scores.py --task child       # Runs only Child-Pugh score
    python run_all_scores.py --replicates 1   # Run with 1 replicate
"""

import subprocess
import sys
import os
import argparse

MODELS = [
    "gpt-5-mini",
    "gemini-3.1-flash-lite",
    "claude-haiku-4.5",
    "xiaomi-mimo-v2-pro",
    "z-ai-glm-5",
    "gemma-3-27b-it",
    "nemotron-3-nano-30b",
    "gpt-oss-20b",
]

SCORES = {
    "meld": {
        "config": "configs/assignments/meld.yaml",
    },
    "fib4": {
        "config": "configs/assignments/fib4.yaml",
    },
    "child": {
        "config": "configs/assignments/child.yaml",
    },
}


def run_task_with_models(task_key: str, replicates: int, dry_run: bool = False):
    """Run a single task with all models."""
    score = SCORES[task_key]
    config_path = score["config"]
    
    print(f"\n{'='*60}")
    print(f"Running {task_key.upper()} with {len(MODELS)} models")
    print(f"Config: {config_path}")
    print(f"{'='*60}")
    
    # Run each model
    for i, model in enumerate(MODELS, 1):
        print(f"\n[{i}/{len(MODELS)}] {model} on {task_key}...")
        
        cmd = [
            sys.executable, "-m", "src.assigner",
            "--config", config_path,
            "--agent", model,
            "--num-replicates", str(replicates),
        ]
        
        if dry_run:
            print(f"  Would run: {' '.join(cmd)}")
        else:
            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"  ERROR: {model} failed with exit code {result.returncode}")
                response = input("  Continue to next model? [y/N]: ").strip().lower()
                if response != 'y':
                    print("  Aborting.")
                    return False
        
        print(f"  {model} completed")
    
    return True


def main():
    parser = argparse.ArgumentParser(description="Run all scores (MELD, FIB-4, Child-Pugh) with all 8 models")
    parser.add_argument(
        "--task", "-t", type=str, choices=["meld", "fib4", "child"],
        default="all", help="Which task to run (default: all)"
    )
    parser.add_argument(
        "--all", "-a", action="store_true",
        help="Run all scores (same as default)"
    )
    parser.add_argument(
        "--replicates", "-n", type=int, default=1,
        help="Number of replicates per model (default: 1)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show commands without executing"
    )
    args = parser.parse_args()
    
    # Determine which tasks to run
    if args.task == "all":
        tasks_to_run = list(SCORES.keys())
    else:
        tasks_to_run = [args.task]
    
    total_runs = len(tasks_to_run) * len(MODELS) * args.replicates
    
    print(f"\n{'#'*60}")
    print(f"# Running {len(tasks_to_run)} task(s) x {len(MODELS)} models x {args.replicates} replicates")
    print(f"# Total: {total_runs} runs")
    print(f"# Tasks: {', '.join(tasks_to_run)}")
    print(f"# Models: {', '.join(MODELS)}")
    print(f"{'#'*60}\n")
    
    for task_key in tasks_to_run:
        success = run_task_with_models(task_key, args.replicates, args.dry_run)
        if not success:
            print(f"Aborting due to failure in {task_key}")
            sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"All {len(tasks_to_run)} task(s) completed!")
    print(f"Output folders:")
    for task_key in tasks_to_run:
        if task_key == "meld":
            print(f"  - outputs/MELDBench")
        elif task_key == "fib4":
            print(f"  - outputs/FIB4Bench")
        elif task_key == "child":
            print(f"  - outputs/ChildPughBench")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()