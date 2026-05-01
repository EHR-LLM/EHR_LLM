#!/usr/bin/env python3
"""Compile final TA1 benchmark results across all 8 models × 3 replicates."""
import json, os, statistics

base = 'outputs_TA1/MedAgentBenchv1'
models = sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])

# Collect data
all_data = {}
for model in models:
    all_data[model] = {}
    for rep in range(1, 4):
        path = f'{base}/{model}/replicate_{rep}/ta1-std/overall.json'
        if os.path.exists(path):
            d = json.load(open(path))
            c = d.get('custom', {})
            v = d.get('validation', {})
            all_data[model][rep] = {
                'accuracy': c.get('metric_accuracy', 0.0),
                'correct': c.get('metric_correct', 0),
                'total': c.get('metric_num_cases', c.get('metric_total', 42)),
                'sensitivity': c.get('metric_sensitivity', 0.0),
                'specificity': c.get('metric_specificity', 0.0),
                'tp': c.get('metric_tp', 0),
                'tn': c.get('metric_tn', 0),
                'fp': c.get('metric_fp', 0),
                'fn': c.get('metric_fn', 0),
                'invalid_pct': v.get('agent invalid action', 0.0) * 100,
                'completed_pct': v.get('completed', 0.0) * 100,
                'ctx_limit_pct': v.get('agent context limit', 0.0) * 100,
                'task_limit_pct': v.get('task limit reached', 0.0) * 100,
                'avg_hist': v.get('average_history_length', 0),
                # Per-biomarker
                'acc_tbil': c.get('metric_accuracy_tbil', None),
                'acc_alb': c.get('metric_accuracy_alb', None),
                'acc_plt': c.get('metric_accuracy_plt', None),
                # Per-patient
                'patients': {k.replace('metric_accuracy_patient_', ''): v2
                             for k, v2 in c.items() if k.startswith('metric_accuracy_patient_')},
            }

# ====================
# TABLE 1: Overall Summary (Mean ± Std across 3 replicates)
# ====================
print("=" * 110)
print("TABLE 1: TA1 Overall Results — Mean ± Std across 3 replicates")
print("=" * 110)
print(f"{'Model':<25} {'Accuracy':<14} {'Sensitivity':<14} {'Specificity':<14} {'Invalid%':<12} {'Completed%':<12}")
print("-" * 110)

model_summaries = []
for model in models:
    reps = all_data[model]
    accs = [reps[r]['accuracy'] for r in reps]
    sens_ = [reps[r]['sensitivity'] for r in reps]
    spec_ = [reps[r]['specificity'] for r in reps]
    inv_ = [reps[r]['invalid_pct'] for r in reps]
    comp_ = [reps[r]['completed_pct'] for r in reps]

    mean_acc = statistics.mean(accs)
    std_acc = statistics.stdev(accs) if len(accs) > 1 else 0
    mean_sens = statistics.mean(sens_)
    std_sens = statistics.stdev(sens_) if len(sens_) > 1 else 0
    mean_spec = statistics.mean(spec_)
    std_spec = statistics.stdev(spec_) if len(spec_) > 1 else 0
    mean_inv = statistics.mean(inv_)
    mean_comp = statistics.mean(comp_)

    model_summaries.append((model, mean_acc, std_acc, mean_sens, std_sens, mean_spec, std_spec, mean_inv, mean_comp))
    print(f"{model:<25} {mean_acc:.3f}±{std_acc:.3f}    {mean_sens:.3f}±{std_sens:.3f}    {mean_spec:.3f}±{std_spec:.3f}    {mean_inv:>6.1f}%      {mean_comp:>6.1f}%")

# Sort by accuracy for ranking
model_summaries.sort(key=lambda x: -x[1])
print()
print("RANKING by mean accuracy:")
for rank, (model, acc, std, *_) in enumerate(model_summaries, 1):
    print(f"  {rank}. {model:<25} {acc:.3f} ± {std:.3f}")

# ====================
# TABLE 2: Per-Replicate Detail
# ====================
print()
print("=" * 120)
print("TABLE 2: Per-Replicate Accuracy & Confusion Matrix")
print("=" * 120)
print(f"{'Model':<25} {'Rep':<5} {'Accuracy':<10} {'TP':<5} {'TN':<5} {'FP':<5} {'FN':<5} {'Sens':<8} {'Spec':<8} {'Invalid%':<10} {'AvgHist':<8}")
print("-" * 120)

for model in models:
    for rep in range(1, 4):
        r = all_data[model].get(rep)
        if r:
            print(f"{model:<25} {rep:<5} {r['accuracy']:<10.3f} {r['tp']:<5} {r['tn']:<5} {r['fp']:<5} {r['fn']:<5} {r['sensitivity']:<8.3f} {r['specificity']:<8.3f} {r['invalid_pct']:<10.1f} {r['avg_hist']:<8.1f}")
    print()

# ====================
# TABLE 3: Per-Biomarker Accuracy (Mean across replicates)
# ====================
print("=" * 90)
print("TABLE 3: Per-Biomarker Accuracy (Mean across 3 replicates)")
print("=" * 90)
biomarkers = ['tbil', 'alb', 'plt']
print(f"{'Model':<25}", end='')
for b in biomarkers:
    print(f" {b.upper():<12}", end='')
print()
print("-" * 90)

for model in models:
    reps = all_data[model]
    print(f"{model:<25}", end='')
    for b in biomarkers:
        vals = [reps[r][f'acc_{b}'] for r in reps if reps[r][f'acc_{b}'] is not None]
        if vals:
            m = statistics.mean(vals)
            print(f" {m:<12.3f}", end='')
        else:
            print(f" {'N/A':<12}", end='')
    print()

# ====================
# TABLE 4: Per-Patient Accuracy (Mean across replicates)
# ====================
print()
print("=" * 120)
print("TABLE 4: Per-Patient Accuracy (Mean across 3 replicates)")
print("=" * 120)

# Collect all patient IDs
all_patients = set()
for model in models:
    for rep in all_data[model]:
        all_patients.update(all_data[model][rep].get('patients', {}).keys())
all_patients = sorted(all_patients)

print(f"{'Model':<25}", end='')
for p in all_patients:
    print(f" {p[-7:]:<10}", end='')  # shortened patient ID
print()
print("-" * 120)

for model in models:
    reps = all_data[model]
    print(f"{model:<25}", end='')
    for p in all_patients:
        vals = [reps[r]['patients'].get(p) for r in reps if reps[r]['patients'].get(p) is not None]
        if vals:
            m = statistics.mean(vals)
            print(f" {m:<10.3f}", end='')
        else:
            print(f" {'N/A':<10}", end='')
    print()

print()
print("=" * 110)
print("NOTES:")
print("  - 42 TA1 tasks: 6 patients × 7 biomarker threshold checks (TBIL, ALB, PLT)")
print("  - 3 replicates per model to assess stochastic variability")
print("  - Invalid% = tasks where the model failed to produce a valid response")
print("  - Sensitivity = TP/(TP+FN), Specificity = TN/(TN+FP)")
print("  - Models accessed FHIR R4 server via agentic GET/FINISH loop")
print("=" * 110)
