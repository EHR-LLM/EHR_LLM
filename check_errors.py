import json, glob

# Check what format the invalid action models are using
for model in ['claude-haiku-4.5', 'gpt-oss-20b', 'nemotron-3-nano-30b']:
    print(f"\n=== {model} ===")
    f = f'outputs_TA1/MedAgentBenchv1/{model}/replicate_1/ta1-std/runs.jsonl'
    with open(f) as fh:
        lines = fh.readlines()
    
    invalid_count = 0
    for line in lines:
        d = json.loads(line)
        if d['output']['status'] == 'agent invalid action':
            if invalid_count < 3:
                history = d['output'].get('history', [])
                if len(history) >= 2:
                    agent_resp = history[1]['content']
                    print(f"  Task {d['index']}: agent response (first 300 chars):")
                    print(f"    {repr(agent_resp[:300])}")
                elif len(history) == 1:
                    # Single turn - check last entry
                    agent_resp = history[-1].get('content', '')
                    print(f"  Task {d['index']}: single-turn response:")
                    print(f"    {repr(agent_resp[:300])}")
            invalid_count += 1
    print(f"  Total invalid: {invalid_count}/{len(lines)}")
