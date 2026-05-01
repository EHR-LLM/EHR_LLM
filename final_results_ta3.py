#!/usr/bin/env python3
"""Compile TA3 results across all models and replicates."""
import json
import os
import glob

BASE = "outputs_TA3/MedAgentBenchv1"

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

print(f"\n{'='*110}")
print(f"TA3 Threshold Crossing + Date Detection — Final Results")
print(f"{'='*110}")
print(f"\n{'Model':<25} {'Rep':<5} {'Accuracy':>10} {'Ans Acc':>10} {'Date Acc':>10} {'Sens':>8} {'Spec':>8} {'TP':>5} {'TN':>5} {'FP':>5} {'FN':>5} {'N':>5}")
print("-" * 110)

model_avgs = {}

for model in MODELS:
    reps = []
    for rep in [1, 2, 3]:
        path = os.path.join(BASE, model, f"replicate_{rep}", "ta3-std", "overall.json")
        if not os.path.exists(path):
            print(f"  MISSING: {path}")
            continue
        with open(path) as f:
            data = json.load(f)
        
        custom = data.get("custom", {})
        acc = custom.get("metric_accuracy", 0)
        ans_acc = custom.get("metric_answer_accuracy", 0)
        date_acc = custom.get("metric_date_accuracy", 0)
        sens = custom.get("metric_sensitivity", 0)
        spec = custom.get("metric_specificity", 0)
        tp = custom.get("metric_tp", 0)
        tn = custom.get("metric_tn", 0)
        fp = custom.get("metric_fp", 0)
        fn = custom.get("metric_fn", 0)
        n = custom.get("metric_total", 0)
        
        reps.append({
            "acc": acc, "ans_acc": ans_acc, "date_acc": date_acc,
            "sens": sens, "spec": spec,
            "tp": tp, "tn": tn, "fp": fp, "fn": fn, "n": n
        })
        
        print(f"  {model:<23} {rep:<5} {acc:>9.1%} {ans_acc:>9.1%} {date_acc:>9.1%} {sens:>7.1%} {spec:>7.1%} {tp:>5} {tn:>5} {fp:>5} {fn:>5} {n:>5}")
    
    if reps:
        avg_acc = sum(r["acc"] for r in reps) / len(reps)
        avg_ans = sum(r["ans_acc"] for r in reps) / len(reps)
        avg_date = sum(r["date_acc"] for r in reps) / len(reps)
        avg_sens = sum(r["sens"] for r in reps) / len(reps)
        avg_spec = sum(r["spec"] for r in reps) / len(reps)
        model_avgs[model] = {
            "acc": avg_acc, "ans_acc": avg_ans, "date_acc": avg_date,
            "sens": avg_sens, "spec": avg_spec
        }
        print(f"  {'→ AVG':<23} {'':5} {avg_acc:>9.1%} {avg_ans:>9.1%} {avg_date:>9.1%} {avg_sens:>7.1%} {avg_spec:>7.1%}")
    print()

print(f"\n{'='*110}")
print(f"{'SUMMARY — Average Accuracy across 3 Replicates':^110}")
print(f"{'='*110}")
print(f"\n{'Rank':<6} {'Model':<25} {'Full Acc':>10} {'Answer Acc':>12} {'Date Acc':>10} {'Sensitivity':>12} {'Specificity':>12}")
print("-" * 90)

sorted_models = sorted(model_avgs.items(), key=lambda x: x[1]["acc"], reverse=True)
for rank, (model, avgs) in enumerate(sorted_models, 1):
    print(f"  {rank:<4} {model:<25} {avgs['acc']:>9.1%} {avgs['ans_acc']:>11.1%} {avgs['date_acc']:>9.1%} {avgs['sens']:>11.1%} {avgs['spec']:>11.1%}")

print(f"\n{'='*110}\n")
