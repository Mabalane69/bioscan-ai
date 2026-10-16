"""
test_server.py - Automated verification test for BioScan AI APIs
"""

import os
import base64
import json
import urllib.request

def run_tests():
    print("[*] Running BioScan AI test suite...")
    
    # 1. Test image loading & metrics extraction
    sample_path = os.path.join(os.path.dirname(__file__), "static", "samples", "sample_1_elena.jpg")
    assert os.path.exists(sample_path), f"Sample image {sample_path} not found"
    
    with open(sample_path, "rb") as f:
        img_bytes = f.read()
    
    import ai_engine
    metrics = ai_engine.extract_image_metrics(img_bytes)
    print(f"[OK] Image metrics extracted successfully: {metrics['dominant_hex']}, Hair: {metrics['hair_color']}, DNA: {metrics['dna_hash']}")
    assert "dna_hash" in metrics
    assert "dominant_rgb" in metrics
    
    # 2. Test biogenetic offline synthesis
    result = ai_engine.generate_biogenetic_profile_offline(metrics)
    profile = result["profile"]
    family = result["family"]
    
    print(f"[OK] Profile synthesized: {profile['full_name']}, Age: {profile['estimated_age']}, Archetype: {profile['personality_archetype']}")
    assert profile["full_name"]
    assert profile["estimated_age"] >= 18
    assert len(profile["bio"]) > 50
    assert len(profile["attributes"]) >= 4
    
    print(f"[OK] Family generated ({len(family)} close relatives):")
    for mem in family:
        print(f"    - {mem['relation']}: {mem['full_name']} ({mem['age']} yrs, {mem['occupation']})")
        assert mem["full_name"]
        assert mem["shared_genetics"]
        assert mem["relationship_dynamic"]
        assert "avatar" in mem
        
    print("\n[ALL TESTS PASSED SUCCESSFULLY!]")

if __name__ == "__main__":
    run_tests()
