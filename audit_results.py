import json, glob

print(f"{'Model':<25} {'Rep':>4} {'Accuracy':>9} {'SuccRate':>9} {'Completed':>10} {'InvalidAct':>11} {'CtxLimit':>9} {'TaskLimit':>10}")
print("-" * 100)

models = {}
for f in sorted(glob.glob('outputs_TA1/MedAgentBenchv1/*/replicate_*/ta1-std/overall.json')):
    parts = f.split('/')
    model = parts[2]
    rep = int(parts[3].replace('replicate_', ''))
    
    with open(f) as fh:
        d = json.load(fh)
    
    v = d.get('validation', {})
    c = d.get('custom', {})
    total = d.get('total', 42)
    acc = c.get('metric_accuracy', c.get('success rate', 0))
    succ_rate = c.get('success rate', 0)
    completed = v.get('completed', 0)
    invalid = v.get('agent invalid action', 0)
    ctx_limit = v.get('agent context limit', 0)
    task_limit = v.get('task limit reached', 0)
    
    print(f"{model:<25} {rep:>4} {acc:>9.3f} {succ_rate:>9.3f} {completed:>10.1%} {invalid:>11.1%} {ctx_limit:>9.1%} {task_limit:>10.1%}")
    
    if model not in models:
        models[model] = {'accs': [], 'invalid_pcts': [], 'ctx_pcts': [], 'task_pcts': []}
    models[model]['accs'].append(acc)
    models[model]['invalid_pcts'].append(invalid)
    models[model]['ctx_pcts'].append(ctx_limit)
    models[model]['task_pcts'].append(task_limit)

print("\n=== SUMMARY (mean across 3 replicates) ===")
print(f"{'Model':<25} {'Mean Acc':>9} {'Mean Invalid':>13} {'Mean CtxLim':>12} {'Mean TaskLim':>13} {'NEEDS RERUN?':>13}")
print("-" * 90)
needs_rerun = []
for model in sorted(models.keys()):
    m = models[model]
    mean_acc = sum(m['accs']) / len(m['accs'])
    mean_inv = sum(m['invalid_pcts']) / len(m['invalid_pcts'])
    mean_ctx = sum(m['ctx_pcts']) / len(m['ctx_pcts'])
    mean_task = sum(m['task_pcts']) / len(m['task_pcts'])
    rerun = "YES" if mean_inv > 0.1 or mean_ctx > 0.1 or mean_task > 0.1 else "no"
    if rerun == "YES":
        needs_rerun.append(model)
    print(f"{model:<25} {mean_acc:>9.3f} {mean_inv:>13.1%} {mean_ctx:>12.1%} {mean_task:>13.1%} {rerun:>13}")

print(f"\nModels needing re-run: {needs_rerun}")
