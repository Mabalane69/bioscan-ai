"""
test_api.py - Tests live HTTP server endpoints for BioScan AI
"""

import os
import json
import base64
import urllib.request

BASE_URL = "http://127.0.0.1:5050"

def test_endpoints():
    print("[*] Testing server endpoints at", BASE_URL)
    
    # 1. Test GET /
    req = urllib.request.Request(f"{BASE_URL}/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "BioScan AI" in html
        print("[OK] GET / returned 200 and valid HTML")

    # 2. Test GET /api/samples
    req = urllib.request.Request(f"{BASE_URL}/api/samples")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "success"
        assert len(data["samples"]) == 4
        print(f"[OK] GET /api/samples returned {len(data['samples'])} sample portraits")

    # 3. Test POST /api/scan
    sample_file = os.path.join(os.path.dirname(__file__), "static", "samples", "sample_2_marcus.jpg")
    with open(sample_file, "rb") as f:
        img_b64 = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")
        
    payload = json.dumps({"image": img_b64, "engine": "biogenetic"}).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}/api/scan", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
        scan_data = json.loads(resp.read().decode("utf-8"))
        assert scan_data["status"] == "success"
        profile = scan_data["data"]["profile"]
        family = scan_data["data"]["family"]
        print(f"[OK] POST /api/scan succeeded for {profile['full_name']} with {len(family)} family relatives")

    # 4. Test POST /api/regenerate-family-member
    regen_payload = json.dumps({
        "id": "rel-sibling",
        "profile": profile,
        "metrics": scan_data["data"]["metrics"]
    }).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}/api/regenerate-family-member", data=regen_payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
        regen_data = json.loads(resp.read().decode("utf-8"))
        assert regen_data["status"] == "success"
        print(f"[OK] POST /api/regenerate-family-member returned: {regen_data['member']['full_name']} ({regen_data['member']['relation']})")

    print("\n[ALL HTTP ENDPOINT INTEGRATION TESTS PASSED!]")

if __name__ == "__main__":
    test_endpoints()
