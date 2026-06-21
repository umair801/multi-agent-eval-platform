import httpx

BASE = "http://localhost:8000"

print("=" * 55)
print("  AgAI_31 FINAL END-TO-END TEST")
print("=" * 55)

# 1. Health check
r = httpx.get(f"{BASE}/health")
print(f"[1] Health:         {r.status_code} - {r.json()['status']}")

# 2. Chat - policy query
r = httpx.post(f"{BASE}/api/v1/chat",
    json={"message": "What is your refund policy?"},
    timeout=120)
d = r.json()
print(f"[2] Chat:           {r.status_code} - intent={d.get('intent')} citations={len(d.get('citations') or [])}")

# 3. Chat - billing query
r = httpx.post(f"{BASE}/api/v1/chat",
    json={"message": "Show my invoice history"},
    timeout=120)
d = r.json()
print(f"[3] Billing:        {r.status_code} - intent={d.get('intent')} outcome={d.get('outcome')}")

# 4. Chat - refund request
r = httpx.post(f"{BASE}/api/v1/chat",
    json={"message": "I was charged twice. I need a refund of 99 dollars."},
    timeout=120)
d = r.json()
print(f"[4] Refund:         {r.status_code} - intent={d.get('intent')} pending={len(d.get('pending_approvals') or [])}")

# 5. Conversations list
r = httpx.get(f"{BASE}/api/v1/conversations?limit=5")
d = r.json()
convs = d.get("conversations", [])
print(f"[5] Conversations:  {r.status_code} - count={len(convs)}")

# 6. Trace for first conversation
if convs:
    cid = convs[0]["id"]
    r = httpx.get(f"{BASE}/api/v1/conversations/{cid}/trace")
    d2 = r.json()
    print(f"[6] Trace:          {r.status_code} - steps={len(d2.get('steps', []))}")
else:
    print("[6] Trace:          SKIP (no conversations)")

# 7. Approvals queue
r = httpx.get(f"{BASE}/api/v1/approvals")
d = r.json()
print(f"[7] Approvals:      {r.status_code} - pending={d.get('count', 0)}")

# 8. Metrics
r = httpx.get(f"{BASE}/api/v1/metrics", timeout=30)
d = r.json()
print(f"[8] Metrics:        {r.status_code} - conversations={d.get('total_conversations')} success={d.get('task_success_rate')}")

# 9. Failures
r = httpx.get(f"{BASE}/api/v1/failures", timeout=30)
d = r.json()
print(f"[9] Failures:       {r.status_code} - categories={list(d.get('failure_categories', {}).keys())}")

# 10. API docs
r = httpx.get(f"{BASE}/docs", timeout=30)
print(f"[10] API Docs:      {r.status_code}")

print("=" * 55)
print("  ALL TESTS COMPLETE")
print("=" * 55)