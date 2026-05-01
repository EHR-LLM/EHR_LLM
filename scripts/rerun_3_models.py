#!/usr/bin/env python3
"""Re-run specific models that had parsing errors for TA3."""
import subprocess
import sys

MODELS = ["claude-haiku-4.5", "nemotron-3-nano-30b", "gpt-oss-20b"]

for i, model in enumerate(MODELS, 1):
    print(f"\n[{i}/{len(MODELS)}] Starting {model}...")
    cmd = [sys.executable, "-m", "src.assigner",
           "--config", "configs/assignments/ta3.yaml",
           "--agent", model, "--num-replicates", "3"]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"  ERROR: {model} failed with exit code {result.returncode}")
    print(f"  Completed {model}")

print("\nAll models re-run complete!")
