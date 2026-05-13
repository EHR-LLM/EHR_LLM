# MedAgentBench task implementation.
# Supports BOTH calculator and no-calculator modes
# Use use_calculator: true in task config to enable calculator mode
# Structure documentation https://github.com/THUDM/AgentBench/blob/main/docs/Extension_en.md
import os
import re
from typing import Callable, Dict, List, Any, Optional
from src.server.task import Task, Session
from src.typings import TaskOutput, SampleStatus, AgentOutputStatus
from .utils import *
from .eval import eval as medagentbench_eval
from .refsol import task_meld, compute_aggregate_metrics, task_fib4, task_child_pugh, task_ta1, compute_ta1_metrics, task_ta3, compute_ta3_metrics
from .meld_calculator import calculate_meld, calculate_fib4, calculate_child_pugh
import time
import json
import importlib

# ============================================================================
# GENERIC PROMPT (used for TA1 and TA3 tasks)
# ============================================================================

MedAgentBench_prompt = """You are an expert in using FHIR functions to assist medical professionals. You are given a question and a set of possible functions. Based on the question, you will need to make one or more function/tool calls to achieve the purpose.

1. If you decide to invoke a GET function, you MUST put it in the format of
GET url?param_name1=param_value1&param_name2=param_value2...

2. If you decide to invoke a POST function, you MUST put it in the format of
POST url
[your payload data in JSON format]

3. If you have got answers for all the questions and finished all the requested tasks, you MUST call to finish the conversation in the format of (make sure the list is JSON loadable.)
FINISH([answer1, answer2, ...])

Your response must be in the format of one of the three cases, and you can call only one function each time. You SHOULD NOT include any other text in the response.

Here is a list of functions in JSON format that you can invoke. Note that you should use {api_base} as the api_base.
{functions}

Context: {context}
Question: {question}"""

# ============================================================================
# TA3 PROMPT (threshold-crossing tasks — requires date for affirmative answers)
# ============================================================================

TA3_prompt = """You are an expert in using FHIR functions to assist medical professionals. You are given a question and a set of possible functions. Based on the question, you will need to make one or more function/tool calls to achieve the purpose.

1. If you decide to invoke a GET function, you MUST put it in the format of
GET url?param_name1=param_value1&param_name2=param_value2...

2. If you decide to invoke a POST function, you MUST put it in the format of
POST url
[your payload data in JSON format]

3. If you have got answers for all the questions and finished all the requested tasks, you MUST call to finish the conversation in the format of (make sure the list is JSON loadable.)

- If the patient DID cross the threshold, respond with the exact date (YYYY-MM-DD) of the first measurement that crossed it:
  FINISH(["yes", "YYYY-MM-DD"])
  Example: FINISH(["yes", "2023-07-14"])

- If the patient did NOT cross the threshold:
  FINISH(["no"])

IMPORTANT:
- The first element MUST be exactly "yes" or "no" (lowercase, no extra words or punctuation).
- The date MUST be in YYYY-MM-DD format (date only, not a timestamp). It is required when the answer is "yes" and must be omitted when the answer is "no".
- Do NOT include any other text in the response.

Your response must be in the format of one of the three cases above, and you can call only one function each time.

Here is a list of functions in JSON format that you can invoke. Note that you should use {api_base} as the api_base.
{functions}

Context: {context}
Question: {question}"""

# ============================================================================
# PROMPTS FOR NO-CALCULATOR MODE (model computes score itself)
# ============================================================================

MELD_prompt = """You are an expert in using FHIR functions to assist medical professionals. You are given a question and a set of possible functions. Based on the question, you will need to make one or more function/tool calls to achieve the purpose.

IMPORTANT — OBSERVATION SELECTION RULE:
If multiple Observation resources exist for the same patient, date, and lab code, you MUST select the one with the earliest effectiveDateTime (earliest timestamp) on that date. This applies to TBIL, INR, and CR.

1. If you decide to invoke a GET function, you MUST put it in the format of
GET url?param_name1=param_value1&param_name2=param_value2...

2. If you decide to invoke a POST function, you MUST put it in the format of
POST url
[your payload data in JSON format]

3. If you have got answers for all the questions and finished all the requested tasks, you MUST call to finish with a JSON object. Do NOT include any markdown fences, explanation, or extra text. The format is:

FINISH({{"patient_id": "<PATIENT_ID>", "date": "<YYYY-MM-DD>", "bilirubin_raw": <number>, "inr_raw": <number>, "creatinine_raw": <number>, "bilirubin_used": <number>, "inr_used": <number>, "creatinine_used": <number>, "bilirubin_corrected": <true_or_false>, "inr_corrected": <true_or_false>, "creatinine_corrected": <true_or_false>, "meld_score": <number>}})

Important — apply this rule strictly BEFORE computing MELD:
For each lab value (bilirubin, INR, creatinine):
- If the raw value is < 1: set the used value to 1, and set the corrected flag to true
- If the raw value is >= 1: use the raw value as-is, and set the corrected flag to false

A raw value of exactly 1.0 is NOT corrected.

You MUST compute these fields in this order:
1. First extract the raw values (bilirubin_raw, inr_raw, creatinine_raw)
2. Then compute the used values (bilirubin_used, inr_used, creatinine_used)
3. Then set the corrected flags (bilirubin_corrected, inr_corrected, creatinine_corrected)
4. Then compute MELD using only the used values

MELD formula:
MELD = 3.78 * ln(bilirubin_used) + 11.2 * ln(inr_used) + 9.57 * ln(creatinine_used) + 6.43

Use natural logarithm (ln). Round the final MELD score to 2 decimal places.

All values in the final JSON object must be numeric where numeric values are expected (not strings). The patient_id and date are strings.

Example (where all three labs are below 1):
FINISH({{"patient_id": "S6545016", "date": "2023-11-05", "bilirubin_raw": 0.4, "inr_raw": 1.0, "creatinine_raw": 0.58, "bilirubin_used": 1.0, "inr_used": 1.0, "creatinine_used": 1.0, "bilirubin_corrected": true, "inr_corrected": false, "creatinine_corrected": true, "meld_score": 6.43}})

Your response must be one of these three types only — no other text:
  1. GET url?param_name1=param_value1&param_name2=param_value2...  (to query FHIR data)
  2. POST url followed by a JSON payload  (to create FHIR data)
  3. FINISH(...) with the required JSON object  (to return your answer)

Here is a list of functions in JSON format that you can invoke. Note that you should use {api_base} as the api_base.
{functions}

Context: {context}
Question: {question}"""

FIB4_prompt = """You are an expert in using FHIR functions to assist medical professionals. You are given a question and a set of possible functions. Based on the question, you will need to make one or more function/tool calls to achieve the purpose.

IMPORTANT — OBSERVATION SELECTION RULE:
If multiple Observation resources exist for the same patient, date, and lab code, you MUST select the one with the earliest effectiveDateTime (earliest timestamp) on that date. This applies to AST, ALT, and PLT.

1. If you decide to invoke a GET function, you MUST put it in the format of
GET url?param_name1=param_value1&param_name2=param_value2...

2. If you decide to invoke a POST function, you MUST put it in the format of
POST url
[your payload data in JSON format]

3. If you have got answers for all the questions and finished all the requested tasks, you MUST call to finish with a JSON object. Do NOT include any markdown fences, explanation, or extra text. The format is:

FINISH({{"patient_id": "<PATIENT_ID>", "date": "<YYYY-MM-DD>", "age": <number>, "ast_raw": <number>, "alt_raw": <number>, "platelets_raw": <number>, "fib4_score": <number>}})

Steps to compute FIB-4:
1. Get the patient's date of birth from the Patient resource
2. Calculate age at the lab date (lab date - date of birth in years, rounded down)
3. Retrieve AST, ALT, and Platelets values from the specified date
4. Compute FIB-4 = (Age × AST) / (Platelets × sqrt(ALT))
5. Use square root (sqrt) for ALT
6. Round the final FIB-4 score to 2 decimal places

All values in the final JSON object must be numeric where numeric values are expected (not strings). The patient_id and date are strings.

Example:
FINISH({{"patient_id": "S0674240", "date": "2023-07-01", "age": 71, "ast_raw": 189, "alt_raw": 137, "platelets_raw": 164, "fib4_score": 6.99}})

Your response must be one of these three types only — no other text:
  1. GET url?param_name1=param_value1&param_name2=param_value2...  (to query FHIR data)
  2. POST url followed by a JSON payload  (to create FHIR data)
  3. FINISH(...) with the required JSON object  (to return your answer)

Here is a list of functions in JSON format that you can invoke. Note that you should use {api_base} as the api_base.
{functions}

Context: {context}
Question: {question}"""

ChildPugh_prompt = """You are an expert in using FHIR functions to assist medical professionals. You are given a question and a set of possible functions. Based on the question, you will need to make one or more function/tool calls to achieve the purpose.

IMPORTANT — OBSERVATION SELECTION RULE:
If multiple Observation resources exist for the same patient, date, and lab code, you MUST select the one with the earliest effectiveDateTime (earliest timestamp) on that date. This applies to Bilirubin (TBIL), Albumin (ALB), and INR.

1. If you decide to invoke a GET function, you MUST put it in the format of
GET url?param_name1=param_value1&param_name2=param_value2...

2. If you decide to invoke a POST function, you MUST put it in the format of
POST url
[your payload data in JSON format]

3. If you have got answers for all the questions and finished all the requested tasks, you MUST call to finish with a JSON object. Do NOT include any markdown fences, explanation, or extra text. The format is:

FINISH({{"patient_id": "<PATIENT_ID>", "date": "<YYYY-MM-DD>", "bilirubin_raw": <number>, "albumin_raw": <number>, "inr_raw": <number>, "ascites_present_same_day": <true_or_false>, "encephalopathy_present_same_day": <true_or_false>, "bilirubin_points": <1_or_2_or_3>, "albumin_points": <1_or_2_or_3>, "inr_points": <1_or_2_or_3>, "ascites_points": <1_or_2>, "encephalopathy_points": <1_or_2>, "child_pugh_score": <integer>}})

Steps to compute Child-Pugh score:
1. Use GET requests to fetch TBIL, Albumin, and INR observations for the patient and date
2. Use GET requests to fetch Condition resources to check for ascites and encephalopathy on the same date
3. Assign bilirubin points:
   - 1 point if bilirubin_raw <= 2 mg/dL
   - 2 points if bilirubin_raw > 2 and bilirubin_raw <= 3 mg/dL
   - 3 points if bilirubin_raw > 3 mg/dL
4. Assign albumin points:
   - 1 point if albumin_raw > 3.5 g/dL
   - 2 points if albumin_raw >= 2.8 and albumin_raw <= 3.5 g/dL
   - 3 points if albumin_raw < 2.8 g/dL
5. Assign INR points:
   - 1 point if inr_raw < 1.7
   - 2 points if inr_raw >= 1.7 and inr_raw <= 2.3
   - 3 points if inr_raw > 2.3
6. Assign ascites points:
   - 1 point if ascites_present_same_day is false
   - 2 points if ascites_present_same_day is true
7. Assign encephalopathy points:
   - 1 point if encephalopathy_present_same_day is false
   - 2 points if encephalopathy_present_same_day is true
8. Sum all points to get the Child-Pugh score
9. The final child_pugh_score must be an integer

All values in the final JSON object must be numeric where numeric values are expected (not strings). The patient_id and date are strings. The boolean fields must be true or false (not strings).

Example:
FINISH({{"patient_id": "S0674240", "date": "2023-07-01", "bilirubin_raw": 2.4, "albumin_raw": 3.2, "inr_raw": 1.8, "ascites_present_same_day": false, "encephalopathy_present_same_day": true, "bilirubin_points": 2, "albumin_points": 2, "inr_points": 2, "ascites_points": 1, "encephalopathy_points": 2, "child_pugh_score": 9}})

Your response must be one of these three types only — no other text:
  1. GET url?param_name1=param_value1&param_name2=param_value2...  (to query FHIR data)
  2. POST url followed by a JSON payload  (to create FHIR data)
  3. FINISH(...) with the required JSON object  (to return your answer)

Here is a list of functions in JSON format that you can invoke. Note that you should use {api_base} as the api_base.
{functions}

Context: {context}
Question: {question}"""

# ============================================================================
# PROMPTS FOR CALCULATOR MODE (model calls calculator API)
# ============================================================================

MELD_prompt_calc = """You are an expert in using FHIR functions to assist medical professionals. You are given a question and a set of possible functions. Based on the question, you will need to make one or more function/tool calls to achieve the purpose.

IMPORTANT — YOU MUST USE THE CALCULATOR API:
After retrieving lab values, you MUST call the calculator API to compute the score. Do NOT compute the score manually.

IMPORTANT — OBSERVATION SELECTION RULE:
If multiple Observation resources exist for the same patient, date, and lab code, you MUST select the one with the earliest effectiveDateTime (earliest timestamp) on that date. This applies to TBIL, INR, and CR.

1. If you decide to invoke a GET function, you MUST put it in the format of
GET url?param_name1=param_value1&param_name2=param_value2...

2. If you decide to invoke a POST function, you MUST put it in the format of
POST url
[your payload data in JSON format]

3. After getting lab values, you MUST call the calculator API:
POST {api_base}/calculate-meld
{{"bilirubin_raw": <value>, "inr_raw": <value>, "creatinine_raw": <value>}}

4. If you have got answers for all the questions and finished all the requested tasks, you MUST call to finish with a JSON object. Do NOT include any markdown fences, explanation, or extra text. The format is:

FINISH({{"patient_id": "<PATIENT_ID>", "date": "<YYYY-MM-DD>", "bilirubin_raw": <number>, "inr_raw": <number>, "creatinine_raw": <number>, "bilirubin_used": <number>, "inr_used": <number>, "creatinine_used": <number>, "bilirubin_corrected": <true_or_false>, "inr_corrected": <true_or_false>, "creatinine_corrected": <true_or_false>, "meld_score": <number>}})

All values in the final JSON object must be numeric where numeric values are expected (not strings). The patient_id and date are strings.

Your response must be one of these types only — no other text:
  1. GET url?param_name1=param_value1&param_name2=param_value2...  (to query FHIR data)
  2. POST url followed by a JSON payload  (to calculator or FHIR data)
  3. FINISH(...) with the required JSON object  (to return your answer)

Here is a list of functions in JSON format that you can invoke. Note that you should use {api_base} as the api_base.
{functions}

Context: {context}
Question: {question}"""

FIB4_prompt_calc = """You are an expert in using FHIR functions to assist medical professionals. You are given a question and a set of possible functions. Based on the question, you will need to make one or more function/tool calls to achieve the purpose.

IMPORTANT — YOU MUST USE THE CALCULATOR API:
After retrieving lab values and patient age, you MUST call the calculator API to compute the score. Do NOT compute the score manually.

IMPORTANT — OBSERVATION SELECTION RULE:
If multiple Observation resources exist for the same patient, date, and lab code, you MUST select the one with the earliest effectiveDateTime (earliest timestamp) on that date. This applies to AST, ALT, and PLT.

1. If you decide to invoke a GET function, you MUST put it in the format of
GET url?param_name1=param_value1&param_name2=param_value2...

2. If you decide to invoke a POST function, you MUST put it in the format of
POST url
[your payload data in JSON format]

3. After getting lab values, you MUST call the calculator API:
POST {api_base}/calculate-fib4
{{"age": <age>, "ast_raw": <value>, "alt_raw": <value>, "platelets_raw": <value>}}

4. If you have got answers for all the questions and finished all the requested tasks, you MUST call to finish with a JSON object. Do NOT include any markdown fences, explanation, or extra text. The format is:

FINISH({{"patient_id": "<PATIENT_ID>", "date": "<YYYY-MM-DD>", "age": <number>, "ast_raw": <number>, "alt_raw": <number>, "platelets_raw": <number>, "fib4_score": <number>}})

All values in the final JSON object must be numeric where numeric values are expected (not strings). The patient_id and date are strings.

Your response must be one of these types only — no other text:
  1. GET url?param_name1=param_value1&param_name2=param_value2...  (to query FHIR data)
  2. POST url followed by a JSON payload  (to calculator or FHIR data)
  3. FINISH(...) with the required JSON object  (to return your answer)

Here is a list of functions in JSON format that you can invoke. Note that you should use {api_base} as the api_base.
{functions}

Context: {context}
Question: {question}"""

ChildPugh_prompt_calc = """You are an expert in using FHIR functions to assist medical professionals. You are given a question and a set of possible functions. Based on the question, you will need to make one or more function/tool calls to achieve the purpose.

IMPORTANT — YOU MUST USE THE CALCULATOR API:
After retrieving lab values and clinical conditions, you MUST call the calculator API to compute the score. Do NOT compute the score manually.

IMPORTANT — OBSERVATION SELECTION RULE:
If multiple Observation resources exist for the same patient, date, and lab code, you MUST select the one with the earliest effectiveDateTime (earliest timestamp) on that date. This applies to Bilirubin (TBIL), Albumin (ALB), and INR.

1. If you decide to invoke a GET function, you MUST put it in the format of
GET url?param_name1=param_value1&param_name2=param_value2...

2. If you decide to invoke a POST function, you MUST put it in the format of
POST url
[your payload data in JSON format]

3. After getting lab values and clinical conditions, you MUST call the calculator API:
POST {api_base}/calculate-child-pugh
{{"bilirubin_raw": <value>, "albumin_raw": <value>, "inr_raw": <value>, "ascites_present": <true_or_false>, "encephalopathy_present": <true_or_false>}}

4. If you have got answers for all the questions and finished all the requested tasks, you MUST call to finish with a JSON object. Do NOT include any markdown fences, explanation, or extra text. The format is:

FINISH({{"patient_id": "<PATIENT_ID>", "date": "<YYYY-MM-DD>", "bilirubin_raw": <number>, "albumin_raw": <number>, "inr_raw": <number>, "ascites_present_same_day": <true_or_false>, "encephalopathy_present_same_day": <true_or_false>, "bilirubin_points": <1_or_2_or_3>, "albumin_points": <1_or_2_or_3>, "inr_points": <1_or_2_or_3>, "ascites_points": <1_or_2>, "encephalopathy_points": <1_or_2>, "child_pugh_score": <integer>}})

All values in the final JSON object must be numeric where numeric values are expected (not strings). The patient_id and date are strings.

Your response must be one of these types only — no other text:
  1. GET url?param_name1=param_value1&param_name2=param_value2...  (to query FHIR data)
  2. POST url followed by a JSON payload  (to calculator or FHIR data)
  3. FINISH(...) with the required JSON object  (to return your answer)

Here is a list of functions in JSON format that you can invoke. Note that you should use {api_base} as the api_base.
{functions}

Context: {context}
Question: {question}"""


class MedAgentBench(Task):
    def __init__(self, **configs):
        super().__init__(**configs)
        self.data_file = configs.pop("data_file")
        with open(self.data_file, 'r') as f:
            self.data = json.load(f)

        self.func_file = configs.pop("func_file")
        with open(self.func_file, 'r') as f:
            self.funcs = json.load(f)

        self.max_round = configs.pop("max_round", 5)

        self.fhir_api_base = configs.pop("fhir_api_base")
        self.task_name = configs.pop("name", "medagentbench")
        self._is_meld = self.task_name.startswith("meld")
        self._is_fib4 = self.task_name.startswith("fib4")
        self._is_child_pugh = self.task_name.startswith("child-pugh")
        self._is_ta1 = self.task_name.startswith("ta1")
        self._is_ta3 = self.task_name.startswith("ta3")
        
        # Calculator mode flag - controls behavior
        self.use_calculator = configs.pop("use_calculator", False)
        
        # Calculator evidence log file path
        self._calc_log_path = None
        if self.use_calculator:
            output_dir = configs.get("output_dir", "outputs")
            self._calc_log_path = os.path.join(output_dir, "calculator_calls.jsonl")

        if verify_fhir_server(self.fhir_api_base) is False:
            print('WARNING: FHIR server connection error! Please check FHIR server status and fhir_api_base in configs/tasks/medagentbench.yaml')
        try:
            module_name = 'src.server.tasks.medagentbench.refsol'
            refsol = importlib.import_module(module_name)
        except Exception:
            print('Make sure refsol.py exists at src/server/tasks/medagentbench/refsol.py')
            exit()

    def get_indices(self) -> List[Any]:
        return list(range(len(self.data)))

    def _get_prompt(self, case: dict) -> str:
        # Select prompt based on task type AND calculator mode
        if self._is_meld:
            prompt_template = MELD_prompt_calc if self.use_calculator else MELD_prompt
        elif self._is_fib4:
            prompt_template = FIB4_prompt_calc if self.use_calculator else FIB4_prompt
        elif self._is_child_pugh:
            prompt_template = ChildPugh_prompt_calc if self.use_calculator else ChildPugh_prompt
        elif self._is_ta3:
            prompt_template = TA3_prompt
        elif self._is_ta1:
            prompt_template = MedAgentBench_prompt
        else:
            raise ValueError(f"Unknown task type: {self.task_name}. Expected meld-*, fib4-*, child-pugh-*, ta1-*, or ta3-*")
        
        return prompt_template.format(
            api_base=self.fhir_api_base,
            functions=json.dumps(self.funcs),
            context=case.get('context', ''),
            question=case['instruction']
        )

    def _log_calculator_call(self, endpoint: str, input_data: dict, output_data: dict, sample_index, agent: str = None, replicate: int = None):
        """Log calculator API calls to JSONL file for evidence"""
        if self._calc_log_path is None:
            return
        entry = {
            "endpoint": endpoint,
            "input": input_data,
            "output": output_data,
            "task_name": self.task_name,
            "sample_index": sample_index,
            "timestamp": int(time.time() * 1000)
        }
        if agent:
            entry["agent"] = agent
        if replicate:
            entry["replicate"] = replicate
        
        # BUG FIX #6: dirname returns '' for a plain filename; makedirs('') raises FileNotFoundError
        parent_dir = os.path.dirname(self._calc_log_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(self._calc_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _parse_finish_json_object(self, r: str) -> Optional[dict]:
        s = r.strip()
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
        except json.JSONDecodeError:
            return None

    async def start_sample(self, index, session: Session):
        print(f"task start {index}")
        case = self.data[index]
        session.inject({"role": "user", "content": self._get_prompt(case)})
        try:
            for round in range(self.max_round):
                res = (await session.action())
                if res.status == AgentOutputStatus.AGENT_CONTEXT_LIMIT:
                    return TaskOutput(
                        status=SampleStatus.AGENT_CONTEXT_LIMIT,
                        history=session.history
                    )
                r = res.content
                if r is None:
                    r = ""
                r = r.strip().replace('```tool_code', '').replace('```', '').strip()
                r = re.sub(r'\[TOOL_CALL\]\s*', '', r)
                r = re.sub(r'\s*\[\/TOOL_CALL\]', '', r)
                think_match = re.search(r'\</think>\s*(.*)', r, re.DOTALL)
                if think_match:
                    r = think_match.group(1).strip()
                r = r.strip()

                # Handle <function_calls><invoke name="GET url"> XML format (used by Claude)
                fc_match = re.search(r'<function_calls>.*?<invoke\s+name=["\']?(GET\s+\S[^"\'>\n]*)["\']?', r, re.DOTALL)
                if fc_match:
                    r = fc_match.group(1).strip()

                # If model prefixed the command with explanatory text, extract the command
                if not (r.startswith('GET') or r.startswith('POST') or r.startswith('FINISH(')):
                    cmd_match = re.search(r'(?m)^(GET\s|POST\s|FINISH\()', r)
                    if cmd_match:
                        r = r[cmd_match.start():].strip()

                tool_match = re.search(r'\[TOOL_CALL\]\s*(.*?)\s*\[\/TOOL_CALL\]', r, re.DOTALL)
                if tool_match:
                    r = tool_match.group(1).strip()
                    try:
                        tool_obj = json.loads(r)
                        if isinstance(tool_obj, dict):
                            tool_name = str(tool_obj.get('tool', ''))
                            args_obj = tool_obj.get('args', {})
                            if isinstance(args_obj, dict):
                                if tool_name.startswith('GET') or 'Observation' in tool_name or 'Patient' in tool_name or 'Condition' in tool_name or 'MedicationRequest' in tool_name or 'Procedure' in tool_name or 'ServiceRequest' in tool_name:
                                    base = tool_name.split('{api_base}')[-1] if '{api_base}' in tool_name else tool_name
                                    params = '&'.join(f"{k}={v}" for k, v in args_obj.items() if v is not None)
                                    r = 'GET ' + base + ('?' if params else '') + params
                                elif tool_name.startswith('POST'):
                                    payload = json.dumps(args_obj, indent=2)
                                    r = 'POST ' + payload
                    except (json.JSONDecodeError, Exception):
                        pass

                if r.startswith('GET'):
                    # BUG FIX #3: use '?' when there are no existing query params
                    raw_url = r[3:].strip().split('\n')[0].strip()
                    sep = '&' if '?' in raw_url else '?'
                    url = raw_url + sep + '_format=json'
                    get_res = send_get_request(url)
                    if "data" in get_res:
                        session.inject({"role": "user", "content": f"Here is the response from the GET request:\n{get_res['data']}. Please call FINISH if you have got answers for all the questions and finished all the requested tasks"})
                    else:
                        session.inject({"role": "user", "content": f"Error in sending the GET request: {get_res['error']}"})

                elif r.startswith('POST'):
                    try:
                        payload = json.loads('\n'.join(r.split('\n')[1:]))
                    except Exception as e:
                        session.inject({"role": "user", "content": "Invalid POST request"})
                    else:
                        # ====================================================================
                        # CALCULATOR MODE: Intercept calculator API calls
                        # ====================================================================
                        if self.use_calculator and '/calculate-' in r:
                            if '/calculate-meld' in r:
                                try:
                                    result = calculate_meld(
                                        float(payload.get('bilirubin_raw', 0)),
                                        float(payload.get('inr_raw', 0)),
                                        float(payload.get('creatinine_raw', 0))
                                    )
                                    response = json.dumps(result)
                                    self._log_calculator_call('/calculate-meld', payload, result, index, None, None)
                                    session.inject({
                                        "role": "user",
                                        "content": f"MELD calculation result: {response}. Please include these values in your FINISH response."
                                    })
                                except Exception as e:
                                    session.inject({"role": "user", "content": f"Error in MELD calculation: {str(e)}"})
                            elif '/calculate-fib4' in r:
                                try:
                                    result = calculate_fib4(
                                        int(payload.get('age', 0)),
                                        float(payload.get('ast_raw', 0)),
                                        float(payload.get('alt_raw', 0)),
                                        float(payload.get('platelets_raw', 0))
                                    )
                                    response = json.dumps(result)
                                    self._log_calculator_call('/calculate-fib4', payload, result, index, None, None)
                                    session.inject({
                                        "role": "user",
                                        "content": f"FIB-4 calculation result: {response}. Please include these values in your FINISH response."
                                    })
                                except Exception as e:
                                    session.inject({"role": "user", "content": f"Error in FIB-4 calculation: {str(e)}"})
                            elif '/calculate-child-pugh' in r:
                                try:
                                    result = calculate_child_pugh(
                                        float(payload.get('bilirubin_raw', 0)),
                                        float(payload.get('albumin_raw', 0)),
                                        float(payload.get('inr_raw', 0)),
                                        bool(payload.get('ascites_present', False)),
                                        bool(payload.get('encephalopathy_present', False))
                                    )
                                    response = json.dumps(result)
                                    self._log_calculator_call('/calculate-child-pugh', payload, result, index, None, None)
                                    session.inject({
                                        "role": "user",
                                        "content": f"Child-Pugh calculation result: {response}. Please include these values in your FINISH response."
                                    })
                                except Exception as e:
                                    session.inject({"role": "user", "content": f"Error in Child-Pugh calculation: {str(e)}"})
                            else:
                                # Unknown calculator endpoint - generic response
                                session.inject({"role": "user", "content": "POST request accepted and executed successfully. Please call FINISH if you have got answers for all the questions and finished all the requested tasks"})
                        else:
                            # ====================================================================
                        # NO CALCULATOR MODE: Generic POST response
                            # ====================================================================
                            session.inject({"role": "user", "content": "POST request accepted and executed successfully. Please call FINISH if you have got answers for all the questions and finished all the requested tasks"})

                elif r.startswith('FINISH('):
                    if self._is_meld or self._is_fib4 or self._is_child_pugh:
                        result_obj = self._parse_finish_json_object(r)
                        if result_obj is not None:
                            return TaskOutput(
                                status=SampleStatus.COMPLETED,
                                result=json.dumps(result_obj),
                                history=session.history
                            )
                        else:
                            return TaskOutput(
                                status=SampleStatus.AGENT_INVALID_ACTION,
                                result=f"Could not parse JSON object from FINISH: {r[:200]}",
                                history=session.history
                            )
                    else:
                        return TaskOutput(
                            status=SampleStatus.COMPLETED,
                            result=r[len('FINISH('):-1],
                            history=session.history
                        )
                else:
                    return TaskOutput(
                        status=SampleStatus.AGENT_INVALID_ACTION,
                        history=session.history
                    )

        except Exception as e:
            return TaskOutput(
                status=SampleStatus.TASK_ERROR,
                result={"error": str(e)},
                history=session.history
            )

        return TaskOutput(
            status=SampleStatus.TASK_LIMIT_REACHED,
            history=session.history
        )

    def calculate_overall(self, results: List[TaskOutput]) -> Dict[str, Any]:
        total_task = len(results)
        assert len(self.get_indices()) == total_task

        if self._is_meld:
            eval_results = []
            annot_results = []
            for i in range(total_task):
                ds_index = results[i].index
                eval_result = task_meld(self.data[ds_index], results[i], self.fhir_api_base, _debug=(i == 0))
                eval_results.append(eval_result)
                passed = eval_result.get("passed", False)
                annot_results.append({
                    "index": ds_index,
                    "status": str(results[i].status),
                    "evaluation": "Correct" if passed else "Incorrect",
                    "correct": passed,
                    "result": results[i].result,
                })

            aggregate = compute_aggregate_metrics(eval_results)
            return {
                'success rate': aggregate.get('metric_full_case_success', 0.0),
                'raw_results': annot_results,
                **aggregate,
            }
        elif self._is_fib4:
            eval_results = []
            annot_results = []
            for i in range(total_task):
                ds_index = results[i].index
                eval_result = task_fib4(self.data[ds_index], results[i], self.fhir_api_base, _debug=(i == 0))
                eval_results.append(eval_result)
                passed = eval_result.get("passed", False)
                annot_results.append({
                    "index": ds_index,
                    "status": str(results[i].status),
                    "evaluation": "Correct" if passed else "Incorrect",
                    "correct": passed,
                    "result": results[i].result,
                })

            aggregate = compute_aggregate_metrics(eval_results)
            return {
                'success rate': aggregate.get('metric_full_case_success', 0.0),
                'raw_results': annot_results,
                **aggregate,
            }
        elif self._is_child_pugh:
            eval_results = []
            annot_results = []
            for i in range(total_task):
                ds_index = results[i].index
                eval_result = task_child_pugh(self.data[ds_index], results[i], self.fhir_api_base, _debug=(i == 0))
                eval_results.append(eval_result)
                passed = eval_result.get("passed", False)
                annot_results.append({
                    "index": ds_index,
                    "status": str(results[i].status),
                    "evaluation": "Correct" if passed else "Incorrect",
                    "correct": passed,
                    "result": results[i].result,
                })

            aggregate = compute_aggregate_metrics(eval_results)
            return {
                'success rate': aggregate.get('metric_full_case_success', 0.0),
                'raw_results': annot_results,
                **aggregate,
            }
        elif self._is_ta1:
            eval_results = []
            annot_results = []
            for i in range(total_task):
                ds_index = results[i].index
                eval_result = task_ta1(self.data[ds_index], results[i])
                eval_results.append(eval_result)
                passed = eval_result.get("correct", False)
                annot_results.append({
                    "index": ds_index,
                    "status": str(results[i].status),
                    "evaluation": "Correct" if passed else "Incorrect",
                    "correct": passed,
                    "result": results[i].result,
                })

            aggregate = compute_ta1_metrics(eval_results, [self.data[r.index] for r in results])
            return {
                'success rate': aggregate.get('metric_accuracy', 0.0),
                'raw_results': annot_results,
                **aggregate,
            }
        elif self._is_ta3:
            eval_results = []
            annot_results = []
            for i in range(total_task):
                ds_index = results[i].index
                eval_result = task_ta3(self.data[ds_index], results[i])
                eval_results.append(eval_result)
                passed = eval_result.get("correct", False)
                annot_results.append({
                    "index": ds_index,
                    "status": str(results[i].status),
                    "evaluation": "Correct" if passed else "Incorrect",
                    "correct": passed,
                    "result": results[i].result,
                })

            aggregate = compute_ta3_metrics(eval_results, [self.data[r.index] for r in results])
            return {
                'success rate': aggregate.get('metric_accuracy', 0.0),
                'raw_results': annot_results,
                **aggregate,
            }
        else:
            correct_count = 0
            annot_results = []
            for i in range(total_task):
                correct = False
                if getattr(results[i], "result") is not None:
                    index = results[i].index
                    if medagentbench_eval(self.data[index], results[i], self.fhir_api_base) is True:
                        correct_count += 1
                        correct = True
                annot_results.append({
                    "index": results[i].index,
                    "status": str(results[i].status),
                    "evaluation": "Correct" if correct else "Incorrect",
                    "correct": correct,
                    "result": results[i].result,
                })

            return {'success rate': correct_count / total_task, 'raw_results': annot_results}