"""
MELD task reference solution evaluator.
Implements full traceability evaluation for MELD score computation.
"""
import json
import re
from typing import Optional
import math


MELD_TOLERANCE = 0.3
FIB4_TOLERANCE = 0.3
CHILD_PUGH_TOLERANCE = 0.3


def _parse_finish_output(result) -> Optional[dict]:
    raw = None
    if isinstance(result, dict):
        raw = result.get("result")
    elif hasattr(result, "result"):
        raw = result.result
    else:
        raw = result
    if raw is None:
        return None
    s = str(raw).strip()
    m = re.match(r"FINISH\(\s*(.*)", s, re.DOTALL)
    if m:
        json_str = m.group(1)
    else:
        json_str = s
    if json_str.startswith("{"):
        depth = 0
        end = 0
        for i, ch in enumerate(json_str):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > 0:
            json_str = json_str[:end]
    try:
        obj = json.loads(json_str)
        if isinstance(obj, dict):
            return obj
        return None
    except (json.JSONDecodeError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_bool(val) -> Optional[bool]:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return None


def task_meld(case_data: dict, result, fhir_api_base: str, _debug: bool = False) -> dict:
    """
    Evaluate a single MELD case.
    Returns a dict with per-field correctness and aggregate pass/fail.
    """
    sol = case_data.get("sol", {})
    agent = _parse_finish_output(result)

    if _debug:
        sol = case_data.get("sol", {})
        print(f"[DEBUG] case id={case_data.get('id','?')}")
        print(f"[DEBUG] result type={type(result).__name__}")
        print(f"[DEBUG] agent parsed OK={agent is not None}")
        if agent is not None:
            print(f"[DEBUG] --- AGENT OUTPUT ---")
            for k in ["patient_id", "date", "bilirubin_raw", "inr_raw", "creatinine_raw",
                       "bilirubin_used", "inr_used", "creatinine_used",
                       "bilirubin_corrected", "inr_corrected", "creatinine_corrected", "meld_score"]:
                print(f"  agent.{k} = {agent.get(k)}")
            print(f"[DEBUG] --- EXPECTED ---")
            for k in ["expected_patient_id", "expected_date",
                       "expected_bilirubin_raw", "expected_inr_raw", "expected_creatinine_raw",
                       "expected_bilirubin_used", "expected_inr_used", "expected_creatinine_used",
                       "expected_bilirubin_corrected", "expected_inr_corrected",
                       "expected_creatinine_corrected", "expected_meld"]:
                print(f"  sol.{k} = {sol.get(k)}")

    checks = {}

    checks["patient_id_correct"] = (
        str(agent.get("patient_id", "")) == str(sol.get("expected_patient_id", ""))
    ) if agent is not None else False

    checks["date_correct"] = (
        str(agent.get("date", "")) == str(sol.get("expected_date", ""))
    ) if agent is not None else False

    checks["bilirubin_raw_correct"] = (
        _safe_float(agent.get("bilirubin_raw")) == _safe_float(sol.get("expected_bilirubin_raw"))
    ) if agent is not None else False

    checks["inr_raw_correct"] = (
        _safe_float(agent.get("inr_raw")) == _safe_float(sol.get("expected_inr_raw"))
    ) if agent is not None else False

    checks["creatinine_raw_correct"] = (
        _safe_float(agent.get("creatinine_raw")) == _safe_float(sol.get("expected_creatinine_raw"))
    ) if agent is not None else False

    checks["bilirubin_used_correct"] = (
        _safe_float(agent.get("bilirubin_used")) == _safe_float(sol.get("expected_bilirubin_used"))
    ) if agent is not None else False

    checks["inr_used_correct"] = (
        _safe_float(agent.get("inr_used")) == _safe_float(sol.get("expected_inr_used"))
    ) if agent is not None else False

    checks["creatinine_used_correct"] = (
        _safe_float(agent.get("creatinine_used")) == _safe_float(sol.get("expected_creatinine_used"))
    ) if agent is not None else False

    checks["bilirubin_corrected_correct"] = (
        _safe_bool(agent.get("bilirubin_corrected")) == sol.get("expected_bilirubin_corrected")
    ) if agent is not None else False

    checks["inr_corrected_correct"] = (
        _safe_bool(agent.get("inr_corrected")) == sol.get("expected_inr_corrected")
    ) if agent is not None else False

    checks["creatinine_corrected_correct"] = (
        _safe_bool(agent.get("creatinine_corrected")) == sol.get("expected_creatinine_corrected")
    ) if agent is not None else False

    expected_meld = _safe_float(sol.get("expected_meld"))
    agent_meld = _safe_float(agent.get("meld_score")) if agent is not None else None
    if expected_meld is not None and agent_meld is not None:
        checks["meld_score_correct"] = abs(agent_meld - expected_meld) <= MELD_TOLERANCE
    else:
        checks["meld_score_correct"] = False

    field_checks = [
        "patient_id_correct",
        "date_correct",
        "bilirubin_raw_correct",
        "inr_raw_correct",
        "creatinine_raw_correct",
        "bilirubin_used_correct",
        "inr_used_correct",
        "creatinine_used_correct",
        "bilirubin_corrected_correct",
        "inr_corrected_correct",
        "creatinine_corrected_correct",
        "meld_score_correct",
    ]
    all_correct = all(checks.get(k, False) for k in field_checks)

    checks["passed"] = all_correct
    checks["num_correct_fields"] = sum(1 for k in field_checks if checks.get(k, False))
    checks["total_fields"] = len(field_checks)
    checks["agent_output"] = agent

    return checks


def task_fib4(case_data: dict, result, fhir_api_base: str, _debug: bool = False) -> dict:
    """
    Evaluate a single FIB-4 case.
    Returns a dict with per-field correctness and aggregate pass/fail.
    """
    sol = case_data.get("sol", {})
    agent = _parse_finish_output(result)

    if _debug:
        sol = case_data.get("sol", {})
        print(f"[DEBUG] case id={case_data.get('id','?')}")
        print(f"[DEBUG] result type={type(result).__name__}")
        print(f"[DEBUG] agent parsed OK={agent is not None}")
        if agent is not None:
            print(f"[DEBUG] --- AGENT OUTPUT ---")
            for k in ["patient_id", "date", "age", "ast_raw", "alt_raw", "platelets_raw", "fib4_score"]:
                print(f"  agent.{k} = {agent.get(k)}")
            print(f"[DEBUG] --- EXPECTED ---")
            for k in ["expected_patient_id", "expected_date", "expected_age",
                      "expected_ast_raw", "expected_alt_raw", "expected_platelets_raw", "expected_fib4"]:
                print(f"  sol.{k} = {sol.get(k)}")

    checks = {}

    checks["patient_id_correct"] = (
        str(agent.get("patient_id", "")) == str(sol.get("expected_patient_id", ""))
    ) if agent is not None else False

    checks["date_correct"] = (
        str(agent.get("date", "")) == str(sol.get("expected_date", ""))
    ) if agent is not None else False

    checks["age_correct"] = (
        _safe_float(agent.get("age")) == _safe_float(sol.get("expected_age"))
    ) if agent is not None else False

    checks["ast_raw_correct"] = (
        _safe_float(agent.get("ast_raw")) == _safe_float(sol.get("expected_ast_raw"))
    ) if agent is not None else False

    checks["alt_raw_correct"] = (
        _safe_float(agent.get("alt_raw")) == _safe_float(sol.get("expected_alt_raw"))
    ) if agent is not None else False

    checks["platelets_raw_correct"] = (
        _safe_float(agent.get("platelets_raw")) == _safe_float(sol.get("expected_platelets_raw"))
    ) if agent is not None else False

    expected_fib4 = _safe_float(sol.get("expected_fib4"))
    agent_fib4 = _safe_float(agent.get("fib4_score")) if agent is not None else None
    if expected_fib4 is not None and agent_fib4 is not None:
        checks["fib4_score_correct"] = abs(agent_fib4 - expected_fib4) <= FIB4_TOLERANCE
    else:
        checks["fib4_score_correct"] = False

    field_checks = [
        "patient_id_correct",
        "date_correct",
        "age_correct",
        "ast_raw_correct",
        "alt_raw_correct",
        "platelets_raw_correct",
        "fib4_score_correct",
    ]
    all_correct = all(checks.get(k, False) for k in field_checks)

    checks["passed"] = all_correct
    checks["num_correct_fields"] = sum(1 for k in field_checks if checks.get(k, False))
    checks["total_fields"] = len(field_checks)
    checks["agent_output"] = agent

    return checks


def task_child_pugh(case_data: dict, result, fhir_api_base: str, _debug: bool = False) -> dict:
    """
    Evaluate a single Child-Pugh case.
    Returns a dict with per-field correctness and aggregate pass/fail.
    """
    sol = case_data.get("sol", {})
    agent = _parse_finish_output(result)

    if _debug:
        sol = case_data.get("sol", {})
        print(f"[DEBUG] case id={case_data.get('id','?')}")
        print(f"[DEBUG] result type={type(result).__name__}")
        print(f"[DEBUG] agent parsed OK={agent is not None}")
        if agent is not None:
            print(f"[DEBUG] --- AGENT OUTPUT ---")
            for k in ["patient_id", "date", "bilirubin_raw", "albumin_raw", "inr_raw",
                      "ascites_present_same_day", "encephalopathy_present_same_day",
                      "bilirubin_points", "albumin_points", "inr_points",
                      "ascites_points", "encephalopathy_points", "child_pugh_score"]:
                print(f"  agent.{k} = {agent.get(k)}")
            print(f"[DEBUG] --- EXPECTED ---")
            for k in ["expected_patient_id", "expected_date",
                      "expected_bilirubin_raw", "expected_albumin_raw", "expected_inr_raw",
                      "expected_ascites_present_same_day", "expected_encephalopathy_present_same_day",
                      "expected_bilirubin_points", "expected_albumin_points", "expected_inr_points",
                      "expected_ascites_points", "expected_encephalopathy_points", "expected_child_pugh_score"]:
                print(f"  sol.{k} = {sol.get(k)}")

    checks = {}

    checks["patient_id_correct"] = (
        str(agent.get("patient_id", "")) == str(sol.get("expected_patient_id", ""))
    ) if agent is not None else False

    checks["date_correct"] = (
        str(agent.get("date", "")) == str(sol.get("expected_date", ""))
    ) if agent is not None else False

    checks["bilirubin_raw_correct"] = (
        _safe_float(agent.get("bilirubin_raw")) == _safe_float(sol.get("expected_bilirubin_raw"))
    ) if agent is not None else False

    checks["albumin_raw_correct"] = (
        _safe_float(agent.get("albumin_raw")) == _safe_float(sol.get("expected_albumin_raw"))
    ) if agent is not None else False

    checks["inr_raw_correct"] = (
        _safe_float(agent.get("inr_raw")) == _safe_float(sol.get("expected_inr_raw"))
    ) if agent is not None else False

    checks["ascites_present_same_day_correct"] = (
        _safe_bool(agent.get("ascites_present_same_day")) == sol.get("expected_ascites_present_same_day")
    ) if agent is not None else False

    checks["encephalopathy_present_same_day_correct"] = (
        _safe_bool(agent.get("encephalopathy_present_same_day")) == sol.get("expected_encephalopathy_present_same_day")
    ) if agent is not None else False

    checks["bilirubin_points_correct"] = (
        _safe_float(agent.get("bilirubin_points")) == _safe_float(sol.get("expected_bilirubin_points"))
    ) if agent is not None else False

    checks["albumin_points_correct"] = (
        _safe_float(agent.get("albumin_points")) == _safe_float(sol.get("expected_albumin_points"))
    ) if agent is not None else False

    checks["inr_points_correct"] = (
        _safe_float(agent.get("inr_points")) == _safe_float(sol.get("expected_inr_points"))
    ) if agent is not None else False

    checks["ascites_points_correct"] = (
        _safe_float(agent.get("ascites_points")) == _safe_float(sol.get("expected_ascites_points"))
    ) if agent is not None else False

    checks["encephalopathy_points_correct"] = (
        _safe_float(agent.get("encephalopathy_points")) == _safe_float(sol.get("expected_encephalopathy_points"))
    ) if agent is not None else False

    expected_score = _safe_float(sol.get("expected_child_pugh_score"))
    agent_score = _safe_float(agent.get("child_pugh_score")) if agent is not None else None
    if expected_score is not None and agent_score is not None:
        checks["child_pugh_score_correct"] = abs(agent_score - expected_score) <= CHILD_PUGH_TOLERANCE
    else:
        checks["child_pugh_score_correct"] = False

    field_checks = [
        "patient_id_correct",
        "date_correct",
        "bilirubin_raw_correct",
        "albumin_raw_correct",
        "inr_raw_correct",
        "ascites_present_same_day_correct",
        "encephalopathy_present_same_day_correct",
        "bilirubin_points_correct",
        "albumin_points_correct",
        "inr_points_correct",
        "ascites_points_correct",
        "encephalopathy_points_correct",
        "child_pugh_score_correct",
    ]
    all_correct = all(checks.get(k, False) for k in field_checks)

    checks["passed"] = all_correct
    checks["num_correct_fields"] = sum(1 for k in field_checks if checks.get(k, False))
    checks["total_fields"] = len(field_checks)
    checks["agent_output"] = agent

    return checks


def compute_aggregate_metrics(results: list) -> dict:
    """
    Compute aggregate metrics across all case evaluations.
    Called by calculate_overall in __init__.py.
    Automatically detects MELD vs FIB-4 vs Child-Pugh based on field presence.
    """
    if not results:
        return {}

    # Detect task type from first result
    is_fib4 = "fib4_score_correct" in results[0] if results else False
    is_meld = "meld_score_correct" in results[0] if results else False
    is_child_pugh = "child_pugh_score_correct" in results[0] if results else False

    if is_child_pugh:
        # Child-Pugh metrics (13 fields)
        fields = [
            "patient_id_correct",
            "date_correct",
            "bilirubin_raw_correct",
            "albumin_raw_correct",
            "inr_raw_correct",
            "ascites_present_same_day_correct",
            "encephalopathy_present_same_day_correct",
            "bilirubin_points_correct",
            "albumin_points_correct",
            "inr_points_correct",
            "ascites_points_correct",
            "encephalopathy_points_correct",
            "child_pugh_score_correct",
        ]
        total_fields = 13
    elif is_fib4:
        # FIB-4 metrics (7 fields)
        fields = [
            "patient_id_correct",
            "date_correct",
            "age_correct",
            "ast_raw_correct",
            "alt_raw_correct",
            "platelets_raw_correct",
            "fib4_score_correct",
        ]
        total_fields = 7
    elif is_meld:
        # MELD metrics (12 fields)
        fields = [
            "patient_id_correct",
            "date_correct",
            "bilirubin_raw_correct",
            "inr_raw_correct",
            "creatinine_raw_correct",
            "bilirubin_used_correct",
            "inr_used_correct",
            "creatinine_used_correct",
            "bilirubin_corrected_correct",
            "inr_corrected_correct",
            "creatinine_corrected_correct",
            "meld_score_correct",
        ]
        total_fields = 12
    else:
        # Fallback - compute from actual results
        field_set = set()
        for r in results:
            for k in r.keys():
                if k.endswith("_correct") and k != "passed":
                    field_set.add(k)
        fields = list(field_set)
        total_fields = len(fields)

    metrics = {}
    for field in fields:
        correct = sum(1 for r in results if r.get(field, False))
        metrics[f"metric_{field}"] = correct / len(results)

    metrics["metric_full_case_success"] = sum(1 for r in results if r.get("passed", False)) / len(results)

    if is_meld:
        lab_raw_fields = ["bilirubin_raw_correct", "inr_raw_correct", "creatinine_raw_correct"]
        metrics["metric_all_lab_raws_correct"] = sum(
            1 for r in results if all(r.get(f, False) for f in lab_raw_fields)
        ) / len(results)

        lab_used_fields = ["bilirubin_used_correct", "inr_used_correct", "creatinine_used_correct"]
        metrics["metric_all_lab_useds_correct"] = sum(
            1 for r in results if all(r.get(f, False) for f in lab_used_fields)
        ) / len(results)

        correction_fields = ["bilirubin_corrected_correct", "inr_corrected_correct", "creatinine_corrected_correct"]
        metrics["metric_all_corrections_correct"] = sum(
            1 for r in results if all(r.get(f, False) for f in correction_fields)
        ) / len(results)

    if is_fib4:
        lab_fields = ["ast_raw_correct", "alt_raw_correct", "platelets_raw_correct"]
        metrics["metric_all_labs_correct"] = sum(
            1 for r in results if all(r.get(f, False) for f in lab_fields)
        ) / len(results)

    if is_child_pugh:
        lab_raw_fields = ["bilirubin_raw_correct", "albumin_raw_correct", "inr_raw_correct"]
        metrics["metric_all_lab_raws_correct"] = sum(
            1 for r in results if all(r.get(f, False) for f in lab_raw_fields)
        ) / len(results)

        points_fields = ["bilirubin_points_correct", "albumin_points_correct", "inr_points_correct",
                         "ascites_points_correct", "encephalopathy_points_correct"]
        metrics["metric_all_points_correct"] = sum(
            1 for r in results if all(r.get(f, False) for f in points_fields)
        ) / len(results)

        clinical_fields = ["ascites_present_same_day_correct", "encephalopathy_present_same_day_correct"]
        metrics["metric_all_clinical_correct"] = sum(
            1 for r in results if all(r.get(f, False) for f in clinical_fields)
        ) / len(results)

    metrics["metric_num_cases"] = len(results)

    avg_fields_correct = sum(r.get("num_correct_fields", 0) for r in results) / len(results)
    metrics["metric_avg_fields_correct"] = avg_fields_correct / total_fields if total_fields > 0 else 0

    return metrics


# --------------------------------------------------------------------------
# TA1: Binary Threshold Classification Evaluator
# --------------------------------------------------------------------------

def _parse_ta1_answer(result) -> Optional[str]:
    """
    Extract the yes/no answer from a TA1 FINISH output.
    Handles formats like: FINISH(["yes"]), ["yes"], "yes", yes
    """
    raw = None
    if isinstance(result, dict):
        raw = result.get("result")
    elif hasattr(result, "result"):
        raw = result.result
    else:
        raw = result
    if raw is None:
        return None
    s = str(raw).strip()
    # Strip FINISH(...) wrapper
    m = re.match(r"FINISH\(\s*(.*?)\s*\)$", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    # Try to parse as JSON list
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list) and len(parsed) >= 1:
            return str(parsed[0]).strip().lower()
        if isinstance(parsed, str):
            return parsed.strip().lower()
    except (json.JSONDecodeError, TypeError):
        pass
    # Try stripping quotes and brackets manually
    s = s.strip("[]\"' ")
    if s.lower() in ("yes", "no"):
        return s.lower()
    return None


def task_ta1(case_data: dict, result) -> dict:
    """
    Evaluate a single TA1 binary threshold task.
    Returns dict with correct flag and metadata.
    """
    expected = case_data.get("sol", [])
    if isinstance(expected, list) and len(expected) >= 1:
        expected_answer = str(expected[0]).strip().lower()
    else:
        expected_answer = str(expected).strip().lower()

    agent_answer = _parse_ta1_answer(result)

    correct = (agent_answer is not None and agent_answer == expected_answer)

    return {
        "correct": correct,
        "expected": expected_answer,
        "agent_answer": agent_answer,
        "task_id": case_data.get("id", ""),
    }


def compute_ta1_metrics(eval_results: list, case_data_list: list) -> dict:
    """
    Compute aggregate metrics for TA1 binary threshold tasks.
    """
    if not eval_results:
        return {}

    n = len(eval_results)
    correct_count = sum(1 for r in eval_results if r.get("correct", False))

    metrics = {
        "metric_accuracy": correct_count / n,
        "metric_correct": correct_count,
        "metric_total": n,
    }

    # Per-biomarker accuracy
    biomarker_stats = {}
    for r, case in zip(eval_results, case_data_list):
        task_id = case.get("id", "")
        # Extract biomarker from task_id like task_threshold_alb_3p5_S0674240
        parts = task_id.replace("task_threshold_", "").split("_")
        if len(parts) >= 1:
            biomarker = parts[0]
            if biomarker not in biomarker_stats:
                biomarker_stats[biomarker] = {"correct": 0, "total": 0}
            biomarker_stats[biomarker]["total"] += 1
            if r.get("correct", False):
                biomarker_stats[biomarker]["correct"] += 1

    for bio, stats in biomarker_stats.items():
        metrics[f"metric_accuracy_{bio}"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0

    # Per-patient accuracy
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

    # Yes/No answer distribution
    yes_expected = sum(1 for case in case_data_list if case.get("sol", [""])[0].lower() == "yes")
    no_expected = n - yes_expected
    metrics["metric_yes_expected"] = yes_expected
    metrics["metric_no_expected"] = no_expected

    # Sensitivity (true positive rate) and Specificity (true negative rate)
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
    metrics["metric_num_cases"] = n

    return metrics


# --------------------------------------------------------------------------
# TA3: Threshold Crossing + Date Detection Evaluator
# --------------------------------------------------------------------------

def _parse_ta3_answer(result) -> tuple:
    """
    Extract the yes/no answer and optional date from a TA3 FINISH output.
    Returns (answer, date) where answer is 'yes'/'no'/None and date is str/None.
    Handles: FINISH(["yes","2023-01-20"]), ["yes","2023-01-20"], FINISH(["no"]), etc.
    """
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
    # Strip FINISH(...) wrapper
    m = re.match(r"FINISH\(\s*(.*?)\s*\)$", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    # Try to parse as JSON list
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list) and len(parsed) >= 1:
            p0 = str(parsed[0]).strip()
            p0_lower = p0.lower()
            # Strict match: first element is exactly "yes" or "no"
            if p0_lower == "yes":
                answer = "yes"
            elif p0_lower == "no":
                answer = "no"
            # Lenient match: first element starts with "yes" or "no" (model added narrative)
            elif p0_lower.startswith("yes"):
                answer = "yes"
            elif p0_lower.startswith("no"):
                answer = "no"
            else:
                # Unrecognisable first element — cannot extract answer
                return (None, None)
            # Extract date: try parsed[1] first, extract YYYY-MM-DD pattern
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
    # Manual bracketed list parsing: ["yes", "2023-01-20"]
    list_match = re.match(r'\[\s*["\']?(yes|no)["\']?\s*(?:,\s*["\']?(\d{4}-\d{2}-\d{2})["\']?\s*)?\]', s, re.IGNORECASE)
    if list_match:
        answer = list_match.group(1).lower()
        date = list_match.group(2)
        return (answer, date)
    # Plain text
    s_lower = s.strip("[]\"' ").lower()
    if s_lower in ("yes", "no"):
        return (s_lower, None)
    return (None, None)


def task_ta3(case_data: dict, result) -> dict:
    """
    Evaluate a single TA3 threshold crossing + date detection task.
    Returns dict with correct flag, date_correct flag, and metadata.
    """
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
        # Negative task: no date expected
        date_correct = True if answer_correct else False

    fully_correct = answer_correct and date_correct

    return {
        "correct": fully_correct,
        "answer_correct": answer_correct,
        "date_correct": date_correct,
        "expected_answer": expected_answer,
        "expected_date": expected_date,
        "agent_answer": agent_answer,
        "agent_date": agent_date,
        "task_id": case_data.get("id", ""),
    }


def compute_ta3_metrics(eval_results: list, case_data_list: list) -> dict:
    """
    Compute aggregate metrics for TA3 threshold crossing + date detection tasks.
    """
    if not eval_results:
        return {}

    n = len(eval_results)
    correct_count = sum(1 for r in eval_results if r.get("correct", False))
    answer_correct_count = sum(1 for r in eval_results if r.get("answer_correct", False))
    date_correct_count = sum(1 for r in eval_results if r.get("date_correct", False))

    metrics = {
        "metric_accuracy": correct_count / n,
        "metric_answer_accuracy": answer_correct_count / n,
        "metric_date_accuracy": date_correct_count / n,
        "metric_correct": correct_count,
        "metric_answer_correct": answer_correct_count,
        "metric_date_correct": date_correct_count,
        "metric_total": n,
    }

    # Per-biomarker accuracy
    biomarker_stats = {}
    for r, case in zip(eval_results, case_data_list):
        task_id = case.get("id", "")
        parts = task_id.replace("task_crossing_", "").split("_")
        if len(parts) >= 1:
            biomarker = parts[0]
            if biomarker not in biomarker_stats:
                biomarker_stats[biomarker] = {"correct": 0, "total": 0}
            biomarker_stats[biomarker]["total"] += 1
            if r.get("correct", False):
                biomarker_stats[biomarker]["correct"] += 1

    for bio, stats in biomarker_stats.items():
        metrics[f"metric_accuracy_{bio}"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0

    # Per-patient accuracy
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

    # Yes/No answer distribution
    yes_expected = sum(1 for case in case_data_list if case.get("sol", [""])[0].lower() == "yes")
    no_expected = n - yes_expected
    metrics["metric_yes_expected"] = yes_expected
    metrics["metric_no_expected"] = no_expected

    # Sensitivity & Specificity
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

    # Date accuracy among positive tasks only
    pos_results = [(r, c) for r, c in zip(eval_results, case_data_list) if c.get("sol", [""])[0].lower() == "yes"]
    if pos_results:
        date_correct_pos = sum(1 for r, _ in pos_results if r.get("date_correct", False))
        metrics["metric_date_accuracy_positive"] = date_correct_pos / len(pos_results)
    else:
        metrics["metric_date_accuracy_positive"] = 0.0

    metrics["metric_num_cases"] = n

    return metrics


def _standard_task_not_available(*args, **kwargs):
    raise NotImplementedError(
        "The original MedAgentBench reference solution functions (task1-task10) are not "
        "available in this refsol.py. These are required for evaluating the standard "
        "medagentbench-std task. To run medagentbench-std, download the original refsol.py "
        "from https://stanfordmedicine.box.com/s/fizv0unyjgkb1r3a83rfn5p3dc673uho "
        "and save it as src/server/tasks/medagentbench/refsol.py, then merge it with "
        "the MELD task functions above. "
        "To run only the MELD task, modify configs/assignments/default.yaml to remove medagentbench-std."
    )


task1 = _standard_task_not_available
task2 = _standard_task_not_available
task3 = _standard_task_not_available
task4 = _standard_task_not_available
task5 = _standard_task_not_available
task6 = _standard_task_not_available
task7 = _standard_task_not_available
task8 = _standard_task_not_available
task9 = _standard_task_not_available
task10 = _standard_task_not_available
