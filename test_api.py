# test_api.py
import requests
import json

print("Testing GuardPulse API...")
print("=" * 50)

# Test 1: Root endpoint
print("\n1. Testing root endpoint...")
try:
    response = requests.get("http://localhost:8000/", timeout=5)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
except requests.exceptions.ConnectionError:
    print("   ❌ ERROR: Cannot connect to API. Is it running?")
    print("   Make sure you have the API running in another terminal:")
    print("   python api.py")
    exit(1)
except Exception as e:
    print(f"   ❌ Error: {e}")
    exit(1)

# Test 2: List startups
print("\n2. Testing /api/startups endpoint...")
response = requests.get("http://localhost:8000/api/startups")
if response.status_code == 200:
    startups = response.json()
    print(f"   Found {len(startups)} startups:")
    for s in startups:
        print(f"   - {s['name']}: {s['guardpulse_score']}/100 ({s['badge']})")
else:
    print(f"   Error: {response.status_code}")

# Test 3: Matchmaking
print("\n3. Testing matchmaking...")
data = {
    "problem_text": "Need a startup for DPDP compliance with consent management and breach notification",
    "top_k": 3
}

response = requests.post(
    "http://localhost:8000/api/match",
    json=data,
    headers={"Content-Type": "application/json"}
)

if response.status_code == 200:
    result = response.json()
    print(f"   Success: {result['success']}")
    print(f"   Found {len(result['matches'])} matches:")
    for i, match in enumerate(result['matches'], 1):
        print(f"\n   {i}. {match['startup']['name']} - {match['relevance_score']}/100")
        print(f"      Badge: {match['startup']['badge']}")
        print(f"      Score: {match['startup']['guardpulse_score']}/100")
        print(f"      Why: {', '.join(match['match_reasons'])}")
        if match['missing_capabilities']:
            print(f"      Missing: {', '.join(match['missing_capabilities'])}")
else:
    print(f"   Error: {response.status_code}")
    print(f"   Response: {response.text}")

print("\n" + "=" * 50)
print("✅ Test complete!")