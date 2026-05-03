import json

with open('battle_logs.json') as f:
    data = json.load(f)

print(f"Total battles: {len(data)}")
if data:
    latest = data[-1]
    print(f"Latest battle has {len(latest.get('turns', []))} turns")
    if latest.get('turns'):
        print(f"First turn keys: {list(latest['turns'][0].keys())}")
        print(f"Sample turn data:\n{json.dumps(latest['turns'][0], indent=2)}")
