# EHR_LLM: Unified Medical Score Benchmark

A unified repository for evaluating AI agents on medical scoring tasks (MELD, FIB-4, Child-Pugh) in **two modes**:

1. **WITH CALCULATOR** - Model calls external calculator API to compute scores
2. **WITHOUT CALCULATOR** - Model computes scores manually using provided formulas

Supports both modes seamlessly with clear mode selection at runtime.

---

## Project Overview

This benchmark evaluates AI agents on extracting lab values from a FHIR server and computing medical scores:

| Score | Formula | Description |
|-------|---------|-------------|
| **MELD** | `3.78 × ln(bilirubin) + 11.2 × ln(INR) + 9.57 × ln(creatinine) + 6.43` | Liver disease severity |
| **FIB-4** | `(Age × AST) / (Platelets × √ALT)` | Liver fibrosis staging |
| **Child-Pugh** | Points (1-3) for 5 metrics | Liver cirrhosis grading |

---

## Available Modes

| Mode | Task Name | Description |
|------|----------|-------------|
| WITH CALCULATOR | `meld-calc`, `fib4-calc`, `child-pugh-calc` | Model calls calculator API |
| WITHOUT CALCULATOR | `meld-std`, `fib4-std`, `child-pugh-std` | Model computes manually |

---

## Repository Structure

```
EHR_LLM/
├── src/
│   ├── start_task.py              # Starts worker infrastructure
│   ├── assigner.py                 # Orchestrates sample execution
│   ├── client/                    # Task/Agent clients
│   ├── server/
│   │   └── tasks/medagentbench/
│   │       ├── __init__.py        # Task logic + prompts (both modes)
│   │       ├── meld_calculator.py # Calculator functions
│   │       ├── refsol.py           # Evaluation logic
│   │       └── eval.py
├── configs/
│   ├── start_task.yaml            # Worker config
│   ├── tasks/
│   │   └── medagentbench.yaml     # Task definitions (all 6 variants)
│   └── assignments/
│       ├── meld_calc.yaml         # MELD with calculator
│       ├── meld_nocalc.yaml       # MELD without calculator
│       ├── fib4_calc.yaml         # FIB-4 with calculator
│       ├── fib4_nocalc.yaml       # FIB-4 without calculator
│       ├── child_calc.yaml        # Child-Pugh with calculator
│       └── child_nocalc.yaml       # Child-Pugh without calculator
├── scripts/
│   ├── run_benchmark.py           # Interactive mode selection (RECOMMENDED)
│   ├── validate_calculator_usage.py
│   └── validate_runs_overall_consistency.py
├── data/medagentbench/
│   ├── test_data_meld.json
│   ├── test_data_fib4.json
│   ├── test_data_child_pugh.json
│   └── funcs_v1.json
└── outputs/
    ├── MELDBench_with_calc/       # Calculator mode outputs
    ├── MELDBench_no_calc/        # No-calculator mode outputs
    ├── FIB4Bench_with_calc/
    ├── FIB4Bench_no_calc/
    ├── ChildPughBench_with_calc/
    ├── ChildPughBench_no_calc/
    └── calculator_calls.jsonl     # Evidence of calculator usage
```

---

## Task Matrix (All 6 Supported)

| # | Task Name | Mode | Config File | Output Folder |
|---|-----------|------|------------|----------------|
| 1 | meld-std | WITHOUT CALCULATOR | configs/assignments/meld_nocalc.yaml | outputs/MELDBench_no_calc/ |
| 2 | meld-calc | WITH CALCULATOR | configs/assignments/meld_calc.yaml | outputs/MELDBench_with_calc/ |
| 3 | fib4-std | WITHOUT CALCULATOR | configs/assignments/fib4_nocalc.yaml | outputs/FIB4Bench_no_calc/ |
| 4 | fib4-calc | WITH CALCULATOR | configs/assignments/fib4_calc.yaml | outputs/FIB4Bench_with_calc/ |
| 5 | child-pugh-std | WITHOUT CALCULATOR | configs/assignments/child_nocalc.yaml | outputs/ChildPughBench_no_calc/ |
| 6 | child-pugh-calc | WITH CALCULATOR | configs/assignments/child_calc.yaml | outputs/ChildPughBench_with_calc/ |

---

## How to Run

### Step 1: Start Workers

```bash
python -m src.start_task --config configs/start_task.yaml -a
```

This starts worker processes on ports 5001-5018.

### Step 2: Run Benchmark (RECOMMENDED - Interactive Mode)

```bash
python scripts/run_benchmark.py
```

This will prompt you to select:
- Task (meld, fib4, or child)
- Mode (calc or nocalc)
- Agent(s)

### Step 2: Run with Flags

```bash
# WITH CALCULATOR mode
python scripts/run_benchmark.py --task meld --mode calc --agent gpt-5-mini --replicates 3
python scripts/run_benchmark.py --task fib4 --mode calc --agent gpt-5-mini --replicates 3
python scripts/run_benchmark.py --task child --mode calc --agent gpt-5-mini --replicates 3

# WITHOUT CALCULATOR mode
python scripts/run_benchmark.py --task meld --mode nocalc --agent gpt-5-mini --replicates 3
python scripts/run_benchmark.py --task fib4 --mode nocalc --agent gpt-5-mini --replicates 3
python scripts/run_benchmark.py --task child --mode nocalc --agent gpt-5-mini --replicates 3
```

### Step 2 (Alternative): Direct Assigner Usage

```bash
# WITH CALCULATOR
python -m src.assigner --config configs/assignments/meld_calc.yaml --agent gpt-5-mini --num-replicates 3
python -m src.assigner --config configs/assignments/fib4_calc.yaml --agent gpt-5-mini --num-replicates 3
python -m src.assigner --config configs/assignments/child_calc.yaml --agent gpt-5-mini --num-replicates 3

# WITHOUT CALCULATOR
python -m src.assigner --config configs/assignments/meld_nocalc.yaml --agent gpt-5-mini --num-replicates 3
python -m src.assigner --config configs/assignments/fib4_nocalc.yaml --agent gpt-5-mini --num-replicates 3
python -m src.assigner --config configs/assignments/child_nocalc.yaml --agent gpt-5-mini --num-replicates 3
```

---

## Calculator vs No-Calculator Mode

### WITH CALCULATOR Mode

| Aspect | Behavior |
|--------|----------|
| Model action | Calls `POST /calculate-*` endpoint |
| POST handling | Intercepted, local calculation performed |
| Evidence | Logged to `outputs/calculator_calls.jsonl` |
| Output folder | `{Score}Bench_with_calc/` |
| Tested capability | API/tool usage |

**Example calculator call:**
```
POST http://localhost:8080/fhir/calculate-meld
{"bilirubin_raw": 5.0, "inr_raw": 1.2, "creatinine_raw": 0.71}
```

Response:
```
{"meld_score": 14.56, "bilirubin_used": 5.0, "inr_used": 1.2, "creatinine_used": 1.0}
```

### WITHOUT CALCULATOR Mode

| Aspect | Behavior |
|--------|----------|
| Model action | Computes score manually using formula in prompt |
| POST handling | Generic "POST request accepted" |
| Evidence | NONE |
| Output folder | `{Score}Bench_no_calc/` |
| Tested capability | Mathematical reasoning |

**Prompt contains formula:**
```
MELD formula: MELD = 3.78 * ln(bilirubin_used) + 11.2 * ln(inr_used) + 9.57 * ln(creatinine_used) + 6.43
```

---

## Output Structure

### Calculator Mode

```
outputs/MELDBench_with_calc/gpt-5-mini/replicate_1/meld-calc/
├── runs.jsonl          # Per-sample results
└── overall.json      # Aggregated metrics

outputs/calculator_calls.jsonl   # Evidence of calculator API calls
```

### No-Calculator Mode

```
outputs/MELDBench_no_calc/gpt-5-mini/replicate_1/meld-std/
├── runs.jsonl
└── overall.json
```

---

## Calculator Evidence

For calculator mode, `outputs/calculator_calls.jsonl` preserves evidence:

```json
{"endpoint": "/calculate-meld", "input": {"bilirubin_raw": 5.0, "inr_raw": 1.2, "creatinine_raw": 0.71}, "output": {"meld_score": 14.56, "bilirubin_used": 5.0}, "task_name": "meld-calc", "sample_index": 0, "timestamp": 1234567890}
{"endpoint": "/calculate-child-pugh", "input": {"bilirubin_raw": 2.4, "albumin_raw": 3.2, "inr_raw": 1.8}, "output": {"child_pugh_score": 9}, "task_name": "child-pugh-calc", "sample_index": 0, "timestamp": 1234567891}
```

### Validate Calculator Usage

```bash
# Check all tasks
python scripts/validate_calculator_usage.py

# Check specific task
python scripts/validate_calculator_usage.py --task meld
python scripts/validate_calculator_usage.py --task fib4
python scripts/validate_calculator_usage.py --task child
```

---

## Sample Counts

| Task | Test Data | Samples | With 3 Replicates |
|------|----------|---------|-------------------|
| meld-* | test_data_meld.json | 6 | 18 |
| fib4-* | test_data_fib4.json | 6 | 18 |
| child-pugh-* | test_data_child_pugh.json | 6 | 18 |

---

## Requirements

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Troubleshooting

### "I ran start_task and nothing happened"

`start_task` starts infrastructure only. Workers wait for HTTP requests - the assigner runs the actual samples.

### "Wrong mode used - calculator was called when I didn't want it"

Ensure you're using the correct config file:
- Calculator: `configs/assignments/*_calc.yaml`
- No-calculator: `configs/assignments/*_nocalc.yaml`

### "Results are wrong"

Check:
1. Expected values in `data/medagentbench/test_data_*.json` under `sol` key
2. Model output format matches expected JSON structure

### Expected Output Format (MELD)

```json
{
  "patient_id": "S0674240",
  "date": "2023-07-01",
  "bilirubin_raw": 5.0,
  "inr_raw": 1.2,
  "creatinine_raw": 0.71,
  "bilirubin_used": 5.0,
  "inr_used": 1.2,
  "creatinine_used": 1.0,
  "bilirubin_corrected": false,
  "inr_corrected": false,
  "creatinine_corrected": true,
  "meld_score": 14.56
}
```

