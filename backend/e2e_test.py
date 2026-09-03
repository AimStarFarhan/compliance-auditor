"""Full E2E test against the running FastAPI server."""
import httpx

BASE = "http://localhost:8000"
FILES = r"C:\Users\Farhan Ali\Desktop\quantum-forgers\backend\sample_configs"

c = httpx.Client(base_url=BASE, timeout=60)

def upload(path, use_ai=False):
    with open(path, "rb") as f:
        return c.post(f"/api/audit?use_ai={str(use_ai).lower()}", files={"file": (path.split("\\")[-1], f, "text/plain")}).json()

print("1. health:", c.get("/api/health").json())

r1 = upload(f"{FILES}\\cisco_ios_sample_1.cfg")
print(f"2. compliant: pass={r1['passed']} fail={r1['failed']} unmapped={len(r1['unmapped_lines'])}")
assert r1["failed"] == 0 and len(r1["unmapped_lines"]) == 0

r2 = upload(f"{FILES}\\cisco_ios_sample_2.cfg")
print(f"3. non-compliant: pass={r2['passed']} fail={r2['failed']} unmapped={len(r2['unmapped_lines'])}")
assert r2["failed"] >= 15

r3 = upload(f"{FILES}\\juniper_srx_sample.cfg")
print(f"4. juniper: pass={r3['passed']} fail={r3['failed']} unmapped={len(r3['unmapped_lines'])}")
assert r3["device_type"] == "juniper_srx"

# 5. unknown vendor -> 422 with clear message
with open(f"{FILES}\\unknown_vendor_sample.cfg", "rb") as f:
    resp = c.post("/api/audit?use_ai=false", files={"file": ("unknown_vendor_sample.cfg", f, "text/plain")})
print(f"5. unknown vendor: HTTP {resp.status_code} -> {resp.json()['detail'][:80]}...")
assert resp.status_code == 422

# 6. confirm one unmapped line from sample 2
line = r2["unmapped_lines"][0]["raw_line"]
conf = c.post("/api/train/confirm", json={"raw_line": line, "category": "auth_settings"}).json()
print(f"6. confirmed '{line}' -> cached pattern '{conf['pattern']}'")

# 7. re-run sample 2: that line must now be human_confirmed
r2b = upload(f"{FILES}\\cisco_ios_sample_2.cfg")
target = next(u for u in r2b["unmapped_lines"] if u["raw_line"] == line)
print(f"7. re-run: '{line}' status = {target['status']} ({target['suggested_category']})")
assert target["status"] == "human_confirmed"

# 8. cache stats grew
stats = c.get("/api/cache/stats").json()
print(f"8. cache stats: {stats}")

# 9. categories endpoint
cats = c.get("/api/categories").json()["categories"]
print(f"9. categories: {len(cats)} available")

# 10. PDF for non-compliant sample
with open(f"{FILES}\\cisco_ios_sample_2.cfg", "rb") as f:
    pdf_resp = c.post("/api/audit/report/pdf?use_ai=false", files={"file": ("cisco_ios_sample_2.cfg", f, "text/plain")})
pdf = pdf_resp.content
print(f"10. PDF: {len(pdf)} bytes, starts {pdf[:8]}")
assert pdf[:5] == b"%PDF-"

print("\nALL E2E TESTS PASSED")
