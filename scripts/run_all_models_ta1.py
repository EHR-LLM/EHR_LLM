#!/usr/bin/env python3
"""Run all 8 models for TA1 sequentially in non-interactive mode."""
import subprocess
import sys

MODELS = [
    "gpt-5-mini", "gemini-3.1-flash-lite", "claude-haiku-4.5",
    "xiaomi-mimo-v2-pro", "z-ai-glm-5", "gemma-3-27b-it",
    "nemotron-3-nano-30b", "gpt-oss-20b",
]


def main():
    replicates = 3
    config = "configs/assignments/ta1.yaml"
    num_models = len(MODELS)
    total_runs = num_models * replicates

    print(f"\n{'='*60}")
    print(f"TA1: Running {num_models} models x {replicates} replicates = {total_runs} total runs")
    print(f"{'='*60}\n")

    failed = []
    for i, model in enumerate(MODELS, 1):
        print(f"\n[{i}/{num_models}] Starting {model}...")
        cmd = [sys.executable, "-m", "src.assigner",
               "--config", config, "--agent", model, "--num-replicates", str(replicates)]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"  ERROR: {model} failed with exit code {result.returncode}")
            failed.append(model)
        else:
            print(f"  Completed {model}")

    print(f"\n{'='*60}")
    if failed:
        print(f"Failed models: {', '.join(failed)}")
    else:
        print(f"All {num_models} models completed successfully!")


if __name__ == "__main__":
    main()
