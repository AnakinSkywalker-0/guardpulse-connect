# Modified webhook_simulator.py for api_n8n.py
import requests
import json

GUARDPULSE_API = "http://localhost:8000/webhook/audit"  # Changed endpoint

def simulate_webhook_for_n8n():
    """Simulate a webhook submission to api_n8n.py"""
    print("\n" + "="*60)
    print("🔗 Simulating n8n Webhook Call to /webhook/audit")
    print("="*60)
    
    # Create a test file
    test_file_path = "test_startup_doc.txt"
    with open(test_file_path, "w") as f:
        f.write("""
        Startup Name: TestAI Solutions
        Description: AI compliance platform for GDPR and DPDP
        Capabilities: consent management, data breach notification, privacy impact assessments
        """)
    
    # Send multipart form data (what api_n8n.py expects)
    with open(test_file_path, "rb") as f:
        files = {
            'document': ('test_startup_doc.txt', f, 'text/plain')
        }
        data = {
            'startup_name': 'TestAI Solutions',
            'contact_email': 'ceo@example.com'
        }
        
        response = requests.post(GUARDPULSE_API, files=files, data=data)
    
    if response.status_code == 200:
        print(f"\n✅ GuardPulse API Response:")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"❌ API Error: {response.status_code} - {response.text}")