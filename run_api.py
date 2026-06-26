# run_api.py
"""
Simple script to run the GuardPulse API
"""

# pyrefly: ignore [missing-import]
import uvicorn

if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 GuardPulse Matchmaking API")
    print("="*50)
    print("  API Docs: http://localhost:8000/docs")
    print("  Endpoint: http://localhost:8000/api/match")
    print("  Press Ctrl+C to stop\n")
    
    import os
    # 0.0.0.0 so the API is reachable from outside the container.
    # Reload is disabled in Docker (file-watching is flaky across bind mounts
    # and unnecessary in a deployed container) — toggle via env var locally.
    host = os.getenv("API_HOST", "0.0.0.0")
    reload_enabled = os.getenv("API_RELOAD", "false").lower() == "true"

    uvicorn.run(
        "api:app",
        host=host,
        port=8000,
        reload=reload_enabled,
        log_level="info"
    )