#!/usr/bin/env python3
"""
Re-evaluate TA3 runs.jsonl files using the updated (lenient) parser.
Reads each runs.jsonl, applies task_ta3() + compute_ta3_metrics(), and
overwrites overall.json with fresh scores.
"""
import json, os, re, sys, collections
from typing import Optional

# ---------------------------------------------------------------------------
# Inline copies of the updated parser and evaluator (no src import needed)
# ---------------------------------------------------------------------------

def _parse_ta3_answer(result):
    raw = None
    if isinstance(result, dict):
        raw = result.get("result")
    elif hasattr(result, "result"):
        raw = result.result
    else:
        raw = result
    if raw is None:
        return (None, None)
    s = str(raw).strip()
    m = re.match(r"FINISH\(\s*(.*?)\s*\)$", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list) and len(parsed) >= 1:
            p0 = str(parsed[0]).strip()
            p0_lower = p0.lower()
            if p0_lower == "yes":
                answer = "yes"
            elif p0_lower == "no":
                answer = "no"
            elif p0_lower.startswith("yes"):
                answer = "yes"
            elif p0_lower.startswith("no"):
                answer = "no"
            else:
                return (None, None)
            date = None
            if answer == "yes" and len(parsed) >= 2:
                date_m = re.search(r'(\d{4}-\d{2}-\d{2})', str(parsed[1]))
                if date_m:
                    date = date_m.group(1)
            return (answer, date)
        if isinstance(parsed, str):
            return (parsed.strip().lower(), None)
    except (json.JSONDecodeError, TypeError):
        pass
    list_match = re.match(r'\[\s*["\']?(yes|no)["\']?\s*(?:,\s*["\']?(\d{4}-\d{2}-\d{2})["\']?\s*)?\]', s, re.IGNORECASE)
    if list_match:
        return (list_match.group(1).lower(), list_match.group(2))
    s_lower = s.strip("[]\"' ").lower()
    if s_lower in ("yes", "no"):
        return (s_lower, None)
    return (None, None)


def task_ta3(case_data: dict, result) -> dict:
    expected = case_data.get("sol", [])
    if isinstance(expected, list) and len(expected) >= 1:
        expected_answer = str(expected[0]).strip().lower()
    else:
        expected_answer = str(expected).strip().lower()
    expected_date = str(expected[1]).strip() if isinstance(expected, list) and len(expected) >= 2 else None

    agent_answer, agent_date = _parse_ta3_answer(result)

    answer_correct = (agent_answer is not None and agent_answer == expected_answer)

    if expected_answer == "yes" and expected_date is not None:
        date_correct = (agent_date is not None and agent_date == expected_date)
    else:
        date_correct = True if answer_correct else False

    fully_correct = answer_correct and date_correct

    return {
        "index": case_data.get("id", ""),
        "status": "SampleStatus.COMPLETED" if agent_answer is not None else "SampleStatus.AGENT_INVALID_ACTION",
        "evaluation": "Correct" if fully_correct else "Incorrect",
        "correct": fully_correct,
        "answer_correct": answer_correct,
        "date_correct": date_correct,
        "expected_answer": expected_answer,
        "expected_date": expected_date,
        "agent_answer": agent_answer,
        "agent_date": agent_date,
        "result": result.get("result") if isinstance(result, dict) else result,
        "task_id": case_data.get("id", ""),
    }


def compute_ta3_metrics(eval_results: list, case_data_list: list) -> dict:
    if not eval_results:
        return {}
    n = len(eval_results)
    correct_count     = sum(1 for r in eval_results if r.get("correct", False))
    answer_correct    = sum(1 for r in eval_results if r.get("answer_correct", False))
    date_correct      = sum(1 for r in eval_results if r.get("date_correct", False))

    metrics = {
        "metric_accuracy": correct_count / n,
        "metric_answer_accuracy": answer_correct / n,
        "metric_date_accuracy": date_correct / n,
        "metric_correct": correct_count,
        "metric_answer_correct": answer_correct,
        "metric_date_correct": date_correct,
        "metric_total": n,
    }

    # Per-biomarker
    biomarker_stats = {}
    for r, case in zip(eval_results, case_data_list):
        bm = case.get("biomarker", "unknown")
        if bm not in biomarker_stats:
            biomarker_stats[bm] = {"correct": 0, "total": 0}
        biomarker_stats[bm]["total"] += 1
        if r.get("correct", False):
            biomarker_stats[bm]["correct"] += 1
    for bm, stats in biomarker_stats.items():
        metrics[f"metric_accuracy_{bm.lower()}"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0

    # Per-patient
    patient_stats = {}
    for r, case in zip(eval_results, case_data_list):
        mrn = case.get("eval_MRN", "unknown")
        if mrn not in patient_stats:
            patient_stats[mrn] = {"correct": 0, "total": 0}
        patient_stats[mrn]["total"] += 1
        if r.get("correct", False):
            patient_stats[mrn]["correct"] += 1
    for mrn, stats in patient_stats.items():
        metrics[f"metric_accuracy_patient_{mrn}"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0

    # Yes/No distribution
    yes_expected = sum(1 for c in case_data_list if c.get("sol", [""])[0].lower() == "yes")
    no_expected = n - yes_expected
    metrics["metric_yes_expected"] = yes_expected
    metrics["metric_no_expected"] = no_expected

    # Sensitivity / Specificity
    tp = sum(1 for r, c in zip(eval_results, case_data_list)
             if r.get("agent_answer") == "yes" and c.get("sol", [""])[0].lower() == "yes")
    tn = sum(1 for r, c in zip(eval_results, case_data_list)
             if r.get("agent_answer") == "no" and c.get("sol", [""])[0].lower() == "no")
    fp = sum(1 for r, c in zip(eval_results, case_data_list)
             if r.get("agent_answer") == "yes" and c.get("sol", [""])[0].lower() == "no")
    fn = sum(1 for r, c in zip(eval_results, case_data_list)
             if r.get("agent_answer") == "no" and c.get("sol", [""])[0].lower() == "yes")

    metrics["metric_sensitivity"] = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    metrics["metric_specificity"] = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    metrics["metric_tp"] = tp
    metrics["metric_tn"] = tn
    metrics["metric_fp"] = fp
    metrics["metric_fn"] = fn

    pos_results = [(r, c) for r, c in zip(eval_results, case_data_list) if c.get("sol", [""])[0].lower() == "yes"]
    date_acc_pos = sum(1 for r, c in pos_results if r.get("date_correct", False)) / len(pos_results) if pos_results else 0.0
    metrics["metric_date_accuracy_positive"] = date_acc_pos
    metrics["metric_num_cases"] = n

    return metrics


# ---------------------------------------------------------------------------
# Main re-evaluation loop
# ---------------------------------------------------------------------------

PROJ = "/Users/fodepixofarfan/coding/EHR_LLM"
DATA_FILE = os.path.join(PROJ, "data/medagentbench/test_data_ta3.json")
OUTPUTS_DIR = os.path.join(PROJ, "outputs_TA3")

# Load ground truth indexed by id (0-based list index)
with open(DATA_FILE) as f:
    test_data = json.load(f)
case_by_index = {i: case for i, case in enumerate(test_data)}

updated = 0
skipped = 0

for root, dirs, files in os.walk(OUTPUTS_DIR):
    if "runs.jsonl" not in files:
        continue
    runs_path = os.path.join(root, "runs.jsonl")
    overall_path = os.path.join(root, "overall.json")

    # Collect last result per index (handles duplicate entries from restarts)
    last_by_index = {}
    with open(runs_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            idx = rec.get("index")
            last_by_index[idx] = rec

    if not last_by_index:
        skipped += 1
        continue

    eval_results = []
    case_data_list = []
    for idx in sorted(last_by_index.keys()):
        rec = last_by_index[idx]
        case_data = case_by_index.get(idx)
        if case_data is None:
            continue
        output = rec.get("output", {})
        eval_r = task_ta3(case_data, output)
        eval_results.append(eval_r)
        case_data_list.append(case_data)

    metrics = compute_ta3_metrics(eval_results, case_data_list)

    # Build raw_results list for overall.json (mirror existing format)
    raw_results = []
    for er in eval_results:
        raw_results.append({
            "index": er["index"],
            "status": er["status"],
            "evaluation": er["evaluation"],
            "correct": er["correct"],
            "result": er["result"],
        })

    overall = {
        "total": len(eval_results),
        "validation": {},
        "custom": {
            "success rate": metrics.get("metric_accuracy", 0),
            "raw_results": raw_results,
            **metrics,
        },
        "replicate": rec.get("replicate", 1) if last_by_index else 1,
    }

    with open(overall_path, "w") as f:
        json.dump(overall, f, indent=2)
    updated += 1

print(f"Re-evaluated {updated} runs (skipped {skipped}).")
print("overall.json files updated. Run final_results_ta3.py for summary.")
