import json, glob

# Check the LAST agent response for invalid cases
for model in ['claude-haiku-4.5', 'gpt-oss-20b', 'nemotron-3-nano-30b']:
    print(f"\n=== {model} ===")
    f = f'outputs_TA1/MedAgentBenchv1/{model}/replicate_1/ta1-std/runs.jsonl'
    with open(f) as fh:
        lines = fh.readlines()
    
    invalid_count = 0
    patterns = {}
    for line in lines:
        d = json.loads(line)
        if d['output']['status'] == 'agent invalid action':
            history = d['output'].get('history', [])
            hist_len = len(history)
            
            # Find the last agent response
            last_agent = None
            for h in reversed(history):
                if h['role'] == 'agent':
                    last_agent = h['content']
                    break
            
            # Categorize the pattern
            if last_agent is None:
                pattern = "NO_AGENT_RESPONSE"
            elif last_agent == 'None' or last_agent is None:
                pattern = "NONE_RESPONSE"
            elif 'GET' in str(last_agent) and not str(last_agent).startswith('GET'):
                pattern = f"PREAMBLE_BEFORE_GET (hist_len={hist_len})"
            elif str(last_agent).startswith('GET'):
                pattern = f"STARTS_WITH_GET_BUT_INVALID (hist_len={hist_len})"
            elif 'FINISH' in str(last_agent) and not str(last_agent).startswith('FINISH'):
                pattern = f"PREAMBLE_BEFORE_FINISH (hist_len={hist_len})"
            else:
                pattern = f"OTHER (hist_len={hist_len})"
            
            if pattern not in patterns:
                patterns[pattern] = {'count': 0, 'examples': []}
            patterns[pattern]['count'] += 1
            if len(patterns[pattern]['examples']) < 2:
                patterns[pattern]['examples'].append(repr(str(last_agent)[:400]))
            
            invalid_count += 1
    
    print(f"  Total invalid: {invalid_count}/{len(lines)}")
    for pattern, info in sorted(patterns.items(), key=lambda x: -x[1]['count']):
        print(f"  Pattern: {pattern} ({info['count']} cases)")
        for ex in info['examples']:
            print(f"    Example: {ex}")
