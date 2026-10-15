# Fire 50 /ask requests to populate the Grafana dashboard.
import json
import os
import time
import urllib.request

def _load_api_key() -> str:
    """API key for /ask: from the env, else from .env. Never hardcode it."""
    key = os.environ.get("RUNBOOKQA_API_KEY", "")
    if key:
        return key
    try:
        with open(".env") as f:
            for line in f:
                line = line.strip()
                if line.startswith("RUNBOOKQA_API_KEY="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    raise SystemExit("RUNBOOKQA_API_KEY not set (env or .env)")


API_KEY = _load_api_key()

QUESTIONS = [
    "A pod is stuck in CrashLoopBackOff. What are the first diagnostic steps?",
    "How do I tell if high API latency is a downstream dependency problem?",
    "A node is reporting DiskPressure. What should I check before evicting pods?",
    "A deployment just rolled out and error rates spiked. What's the rollback procedure?",
    "How do I verify a database failover completed successfully?",
    "What is our vacation policy for on-call engineers?",
    "My pod keeps crashing and restarting. How do I debug it?",
    "What is the rollback procedure after a bad deployment?",
    "How do I check disk pressure on a node?",
    "What is our PTO policy?",
]

N = 50
errors = 0
for i in range(N):
    q = QUESTIONS[i % len(QUESTIONS)]
    body = json.dumps({"question": q}).encode()
    req = urllib.request.Request(
        "http://localhost:8000/ask",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            resp.read()
        print(f"[{i+1}/{N}] HTTP {resp.status} {time.time()-start:.1f}s - {q[:50]}")
    except Exception as e:
        errors += 1
        print(f"[{i+1}/{N}] ERROR {e} - {q[:50]}")

print(f"done: {N} requests sent, {errors} errors")
