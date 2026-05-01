import json

# Check if nemotron responses contain FINISH anywhere
model = 'nemotron-3-nano-30b'
f = f'outputs_TA1/MedAgentBenchv1/{model}/replicate_1/ta1-std/runs.jsonl'
with open(f) as fh:
    lines = fh.readlines()

for line in lines:
    d = json.loads(line)
    if d['output']['status'] == 'agent invalid action':
        history = d['output'].get('history', [])
        for h in reversed(history):
            if h['role'] == 'agent':
                content = str(h['content'])
                has_finish = 'FINISH' in content
                has_yes_no = 'yes' in content.lower() or 'no' in content.lower()
                print(f"  Task {d['index']}: has_FINISH={has_finish}, has_yes_no={has_yes_no}")
                print(f"    Last 200 chars: {repr(content[-200:])}")
                break

print("\n=== gpt-oss-20b non-None failures ===")
model = 'gpt-oss-20b'
f = f'outputs_TA1/MedAgentBenchv1/{model}/replicate_1/ta1-std/runs.jsonl'
with open(f) as fh:
    lines = fh.readlines()

for line in lines:
    d = json.loads(line)
    if d['output']['status'] == 'agent invalid action':
        history = d['output'].get('history', [])
        for h in reversed(history):
            if h['role'] == 'agent':
                content = str(h['content'])
                if content != 'None':
                    print(f"  Task {d['index']}: {repr(content[:500])}")
                break
