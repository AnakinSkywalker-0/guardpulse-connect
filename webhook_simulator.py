# webhook_simulator.py
"""
Simulates n8n webhook for testing GuardPulse API
"""

import requests
import json
from datetime import datetime

# Your GuardPulse API endpoint
GUARDPULSE_API = "http://localhost:8000/api/match"

def test_matchmaking():
    """Test the matchmaking API directly"""
    
    print("\n" + "="*60)
    print("🧪 Testing GuardPulse Matchmaking API")
    print("="*60)
    
    # Test cases
    test_cases = [
        {
            "name": "DPDP Compliance",
            "problem": "Need a startup for DPDP compliance with consent management and breach notification",
            "email": "ceo@healthcare.com"
        },
        {
            "name": "EU AI Act",
            "problem": "Looking for AI transparency and human oversight for EU AI Act compliance",
            "email": "cto@techcorp.com"
        },
        {
            "name": "General Compliance",
            "problem": "Need compliance automation for legal document review",
            "email": "compliance@enterprise.com"
        }
    ]
    
    for test in test_cases:
        print(f"\n📋 Test: {test['name']}")
        print(f"   Problem: {test['problem'][:80]}...")
        
        # Prepare request
        payload = {
            "problem_text": test['problem'],
            "top_k": 3
        }
        
        try:
            response = requests.post(
                GUARDPULSE_API,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                matches = result.get('matches', [])
                
                print(f"   ✅ Found {len(matches)} matches")
                
                for i, match in enumerate(matches, 1):
                    startup = match['startup']
                    print(f"\n   {i}. {startup['name']} - {match['relevance_score']}/100")
                    print(f"      Score: {startup['guardpulse_score']}/100")
                    print(f"      Badge: {startup['badge']}")
                    print(f"      Capabilities: {', '.join(startup['capabilities'][:3])}")
                    print(f"      Why: {', '.join(match['match_reasons'])}")
                    
                    # Simulate email content
                    if i == 1:  # Top match
                        email_content = f"""
                        🎯 Top Match: {startup['name']}
                        Match Score: {match['relevance_score']}/100
                        GuardPulse Score: {startup['guardpulse_score']}/100
                        Badge: {startup['badge']}
                        Capabilities: {', '.join(startup['capabilities'])}
                        Contact: {startup['contact_email']}
                        Website: {startup['website']}
                        """
                        print(f"\n      📧 Email Preview:\n{email_content}")
            else:
                print(f"   ❌ API Error: {response.status_code} - {response.text}")
                
        except requests.exceptions.ConnectionError:
            print("   ❌ Cannot connect to GuardPulse API. Make sure it's running:")
            print("      python run_api.py")
            return
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n" + "="*60)
    print("✅ Testing complete!")
    print("\nNext steps:")
    print("1. Start n8n: n8n start")
    print("2. Import the workflow JSON")
    print("3. Configure email (or use webhook response)")
    print("4. Test with real submissions")

def simulate_webhook():
    """Simulate a webhook submission to n8n"""
    print("\n" + "="*60)
    print("🔗 Simulating n8n Webhook Call")
    print("="*60)
    
    # This would be the payload n8n sends to your API
    webhook_payload = {
        "body": {
            "problem": "Need a startup for DPDP compliance with consent management and breach notification",
            "email": "ceo@example.com",
            "company": "Enterprise Corp",
            "timestamp": datetime.now().isoformat()
        }
    }
    
    print("\n📤 Webhook Payload:")
    print(json.dumps(webhook_payload, indent=2))
    
    # Call your API (this is what n8n would do)
    response = requests.post(
        GUARDPULSE_API,
        json={"problem_text": webhook_payload["body"]["problem"], "top_k": 3}
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"\n✅ GuardPulse API Response:")
        print(f"   Matches found: {len(result['matches'])}")
        
        # This would be n8n's response back to the webhook
        n8n_response = {
            "status": "success",
            "matches_count": len(result['matches']),
            "top_match": result['matches'][0]['startup']['name'] if result['matches'] else None,
            "email_sent": True,
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"\n📤 n8n Webhook Response:")
        print(json.dumps(n8n_response, indent=2))
    else:
        print(f"❌ API Error: {response.status_code}")

if __name__ == "__main__":
    print("\nChoose an option:")
    print("1. Test GuardPulse API directly")
    print("2. Simulate n8n webhook flow")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "1":
        test_matchmaking()
    elif choice == "2":
        simulate_webhook()
    else:
        print("Invalid choice, running test_matchmaking()")
        test_matchmaking()