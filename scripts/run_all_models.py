#!/usr/bin/env python3
"""
Run all 8 models sequentially in non-interactive mode.

Usage:
    python run_all_models.py                  # Runs all 8 models with default 3 replicates
    python run_all_models.py --replicates 5  # Runs all 8 models with 5 replicates
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

def main():
    parser = argparse.ArgumentParser(description="Run all 8 models sequentially")
    parser.add_argument(
        "--replicates", "-n", type=int, default=3,
        help="Number of replicates per model (default: 3)"
    )
    parser.add_argument(
        "--config", "-c", type=str, 
        default="configs/assignments/meld.yaml",
        help="Config file path"
    )
    parser.add_argument(
        "--retry", "-r", action="store_true",
        help="Enable auto-retry on failure"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show commands without executing"
    )
    args = parser.parse_args()
    
    num_models = len(MODELS)
    total_runs = num_models * args.replicates
    
    print(f"\n{'='*60}")
    print(f"Running {num_models} models x {args.replicates} replicates = {total_runs} total runs")
    print(f"{'='*60}\n")
    
    for i, model in enumerate(MODELS, 1):
        print(f"\n[{i}/{num_models}] Starting {model}...")
        
        cmd = [
            sys.executable, "-m", "src.assigner",
            "--config", args.config,
            "--agent", model,
            "--num-replicates", str(args.replicates),
        ]
        
        if args.retry:
            cmd.append("--auto-retry")
        
        if args.dry_run:
            print(f"  Would run: {' '.join(cmd)}")
        else:
            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"  ERROR: {model} failed with exit code {result.returncode}")
                response = input("  Continue to next model? [y/N]: ").strip().lower()
                if response != 'y':
                    print("  Aborting.")
                    sys.exit(1)
        
        print(f"  Completed {model}")
    
    print(f"\n{'='*60}")
    print(f"All {num_models} models completed!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()