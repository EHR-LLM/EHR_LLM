#!/usr/bin/env python3
"""
Run MELD/FIB-4/Child-Pugh benchmarks with explicit mode selection.

Usage:
    python run_benchmark.py                    # Full interactive selection
    python run_benchmark.py --mode calc       # Calculator mode
    python run_benchmark.py --mode nocalc      # No calculator mode
    python run_benchmark.py --task meld --mode calc --agent gpt-5-mini --replicates 3
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

# Task names: use std for no-calc, calc for with-calc
SCORES = {
    "meld": {
        "calc": "configs/assignments/meld_calc.yaml",
        "nocalc": "configs/assignments/meld_nocalc.yaml",
    },
    "fib4": {
        "calc": "configs/assignments/fib4_calc.yaml",
        "nocalc": "configs/assignments/fib4_nocalc.yaml",
    },
    "child": {
        "calc": "configs/assignments/child_calc.yaml",
        "nocalc": "configs/assignments/child_nocalc.yaml",
    },
}

TASK_NAMES = {
    "meld": "MELD",
    "fib4": "FIB-4",
    "child": "Child-Pugh",
}

MODE_DESCRIPTIONS = {
    "calc": "WITH CALCULATOR - Model calls calculator API",
    "nocalc": "NO CALCULATOR - Model computes manually",
}


def run_task(task_key: str, mode: str, agents: list, replicates: int, dry_run: bool = False):
    """Run a single task with specified mode."""
    score = SCORES[task_key]
    config_path = score[mode]
    
    print(f"\n{'='*60}")
    print(f"Running {TASK_NAMES[task_key]} in {MODE_DESCRIPTIONS[mode]}")
    print(f"Config: {config_path}")
    print(f"Agents: {len(agents)}, Replicates: {replicates}")
    print(f"{'='*60}")
    
    for i, agent in enumerate(agents, 1):
        print(f"\n[{i}/{len(agents)}] {agent} on {task_key} ({mode})...")
        
        cmd = [
            sys.executable, "-m", "src.assigner",
            "--config", config_path,
            "--agent", agent,
            "--num-replicates", str(replicates),
        ]
        
        if dry_run:
            print(f"  Would run: {' '.join(cmd)}")
        else:
            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"  ERROR: {agent} failed with exit code {result.returncode}")
    
    return True


def get_choice(prompt: str, options: list, default: int = 0) -> int:
    """Get user choice from a list."""
    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    print(f"  0. Exit")
    
    while True:
        try:
            choice = input(f"\nEnter number (default {default}): ").strip()
            if not choice:
                return default
            idx = int(choice)
            if 0 <= idx <= len(options):
                return idx
        except ValueError:
            pass
        print("Invalid choice. Try again.")


def main():
    parser = argparse.ArgumentParser(description="Run benchmark with full selection")
    parser.add_argument(
        "--mode", "-m", type=str, choices=["calc", "nocalc"],
        help="Calculator mode: 'calc' or 'nocalc'"
    )
    parser.add_argument(
        "--task", "-t", type=str, choices=["meld", "fib4", "child"],
        default=None, help="Which score (meld/fib4/child)"
    )
    parser.add_argument(
        "--agent", "-a", type=str, default=None,
        help="Specific agent (default: all)"
    )
    parser.add_argument(
        "--replicates", "-n", type=int, default=3,
        help="Number of replicates (default: 3)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show commands without executing"
    )
    args = parser.parse_args()
    
    # Full interactive selection if no arguments provided
    if args.task is None and args.mode is None:
        print("\n" + "="*60)
        print("BENCHMARK EXECUTION")
        print("="*60)
        
        # Step 1: Choose task
        task_idx = get_choice("Which SCORE?", list(TASK_NAMES.values()), 1)
        if task_idx == 0:
            print("Exiting.")
            return
        args.task = list(SCORES.keys())[task_idx - 1]
        
        # Step 2: Choose mode
        mode_idx = get_choice(f"\nWhich MODE for {TASK_NAMES[args.task]}?", ["WITH CALCULATOR", "NO CALCULATOR"], 1)
        if mode_idx == 0:
            print("Exiting.")
            return
        args.mode = ["calc", "nocalc"][mode_idx - 1]
        
        # Step 3: Choose agent
        agent_idx = get_choice("\nWhich AGENT?", MODELS + ["All agents"], 8)
        if agent_idx == 0:
            print("Exiting.")
            return
        elif agent_idx == 8:
            args.agent = None  # All agents
        else:
            args.agent = MODELS[agent_idx - 1]
        
        # Step 4: Choose replicates
        try:
            n = input("\nNumber of replicates (default 3): ").strip()
            args.replicates = int(n) if n else 3
        except ValueError:
            args.replicates = 3
    
    # Validate
    if args.task is None:
        args.task = "meld"
    if args.mode is None:
        args.mode = "nocalc"
    
    print(f"\n{'='*60}")
    print(f"EXECUTION SUMMARY")
    print(f"{'='*60}")
    print(f"  Task:      {TASK_NAMES[args.task]}")
    print(f"  Mode:     {MODE_DESCRIPTIONS[args.mode]}")
    print(f"  Agent:    {args.agent if args.agent else 'ALL 8'}")
    print(f"  Replicates: {args.replicates}")
    print(f"{'='*60}")
    
    confirm = input("\nProceed? (Y/n): ").strip().lower()
    if confirm not in ["", "y", "Y"]:
        print("Cancelled.")
        return
    
    # Determine agents
    if args.agent:
        agents = [args.agent]
    else:
        agents = MODELS
    
    success = run_task(args.task, args.mode, agents, args.replicates, args.dry_run)
    
    if success:
        task_name = TASK_NAMES[args.task]
        mode_name = args.mode.upper()
        output_folder = f"outputs/{task_name}Bench_with_calc" if args.mode == "calc" else f"outputs/{task_name}Bench_no_calc"
        
        print(f"\n{'='*60}")
        print(f"Completed {task_name} in {mode_name} mode!")
        print(f"Outputs: {output_folder}/")
        if args.mode == "calc":
            print(f"Calculator evidence: outputs/calculator_calls.jsonl")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()