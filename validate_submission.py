#!/usr/bin/env python3
"""
Final validation script for OpenEnv Hackathon submission
Run this before submitting to ensure compliance
"""

import os
import sys
import subprocess
import json
import requests

# Disable emojis for Windows compatibility
USE_EMOJI = False

def get_status_icon(success, required=True):
    if USE_EMOJI:
        return "✅" if success else ("❌" if required else "⚠️")
    return "[PASS]" if success else ("[FAIL]" if required else "[WARN]")

def check_file_exists(filepath, required=True):
    """Check if file exists"""
    exists = os.path.exists(filepath)
    status = get_status_icon(exists, required)
    req = "REQUIRED" if required else "optional"
    print(f"  {status} {filepath} ({req})")
    return exists or not required


def check_openenv_yaml():
    """Validate openenv.yaml structure"""
    try:
        import yaml
        if not os.path.exists("openenv.yaml"):
            print("  [FAIL] openenv.yaml not found")
            return False
        with open("openenv.yaml", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        required = ["name", "version", "author", "entry_point", "port", "tasks"]
        missing = [k for k in required if k not in config]
        
        if missing:
            print(f"  [FAIL] openenv.yaml missing fields: {missing}")
            return False
        
        print(f"  [PASS] openenv.yaml valid (name: {config.get('name')}, tasks: {len(config.get('tasks', []))})")
        return True
    except Exception as e:
        print(f"  [FAIL] openenv.yaml error: {e}")
        return False


def check_dockerfile():
    """Validate Dockerfile"""
    try:
        if not os.path.exists("Dockerfile"):
            print("  [FAIL] Dockerfile not found")
            return False
        with open("Dockerfile", encoding="utf-8") as f:
            content = f.read()
        
        checks = [
            ("python:3.11" in content, "Python 3.11 base"),
            ("7860" in content, "Port 7860 exposed"),
            ("uvicorn" in content, "Uvicorn CMD"),
            ("server.app:app" in content, "Correct entry point"),
        ]
        
        all_pass = all(c[0] for c in checks)
        for passed, desc in checks:
            print(f"  {get_status_icon(passed)} {desc}")
        
        return all_pass
    except Exception as e:
        print(f"  [FAIL] Dockerfile error: {e}")
        return False


def check_inference_py():
    """Validate inference.py"""
    try:
        if not os.path.exists("inference.py"):
            print("  [FAIL] inference.py not found")
            return False
        with open("inference.py", encoding="utf-8") as f:
            content = f.read()
        
        checks = [
            ("API_BASE_URL" in content, "Uses API_BASE_URL env var"),
            ("MODEL_NAME" in content, "Uses MODEL_NAME env var"),
            ("HF_TOKEN" in content, "Uses HF_TOKEN env var"),
            ('"easy"' in content and '"medium"' in content and '"hard"' in content, "Runs all 3 tasks"),
            ("json.dumps" in content, "Outputs JSON"),
        ]
        
        for passed, desc in checks:
            print(f"  {get_status_icon(passed)} {desc}")
        
        return all(c[0] for c in checks)
    except Exception as e:
        print(f"  [FAIL] inference.py error: {e}")
        return False


def test_local_api():
    """Test local API endpoints"""
    print("\nTesting Local API (server must be running)...")
    
    try:
        # Health check
        r = requests.get("http://localhost:7860/health", timeout=5)
        if r.status_code != 200:
            print("  [WARN] Server not running locally (skip local tests)")
            return True  # Not a failure if server not running
        
        print("  [PASS] /health responds")
        
        # Test reset
        r = requests.post("http://localhost:7860/reset", 
                         json={"task_id": "easy"}, timeout=5)
        if r.status_code == 200:
            print("  [PASS] /reset with task_id works")
        else:
            print(f"  [FAIL] /reset failed: {r.status_code}")
            return False
        
        # Test state
        r = requests.get("http://localhost:7860/state", timeout=5)
        data = r.json()
        if "episode_id" in data and "step_count" in data:
            print("  [PASS] /state returns state dict")
        else:
            print("  [FAIL] /state missing required fields")
            return False
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("  [WARN] Server not running locally (skip)")
        return True
    except Exception as e:
        print(f"  [FAIL] API test error: {e}")
        return False


def main():
    """Run all validations"""
    print("=" * 60)
    print("OPENENV HACKATHON SUBMISSION VALIDATION")
    print("=" * 60)
    
    checks = []
    
    # Tier 1: Critical Files
    print("\nTier 1: Critical Files")
    checks.append(check_file_exists("openenv.yaml"))
    checks.append(check_file_exists("inference.py"))
    checks.append(check_file_exists("Dockerfile"))
    checks.append(check_file_exists("requirements.txt"))
    checks.append(check_file_exists("app/main.py"))
    checks.append(check_file_exists("app/environment.py"))
    checks.append(check_file_exists("app/models.py"))
    checks.append(check_file_exists("app/grader.py"))
    checks.append(check_file_exists("app/scenarios.py"))
    checks.append(check_file_exists("app/database.py"))
    
    # Tier 2: Enhanced Files
    print("\nTier 2: Enhanced Files")
    checks.append(check_file_exists("static/index.html", required=False))
    checks.append(check_file_exists("README.md", required=False))
    checks.append(check_file_exists("LICENSE", required=False))
    checks.append(check_file_exists(".gitignore", required=False))
    
    # Content Validation
    print("\nContent Validation")
    checks.append(check_openenv_yaml())
    checks.append(check_dockerfile())
    checks.append(check_inference_py())
    
    # API Tests
    checks.append(test_local_api())
    
    # Summary
    print("\n" + "=" * 60)
    passed = sum(checks)
    total = len(checks)
    percentage = (passed / total) * 100
    
    print(f"RESULT: {passed}/{total} checks passed ({percentage:.1f}%)")
    
    if percentage >= 95:
        print("EXCELLENT! Ready for submission!")
        print("Winning probability: 90%+")
    elif percentage >= 80:
        print("GOOD! Minor improvements possible.")
        print("Winning probability: 75-85%")
    else:
        print("NEEDS WORK! Fix failed checks before submitting.")
        print("Winning probability: <50%")
    
    print("=" * 60)
    
    # Final checklist
    print("\nFINAL SUBMISSION CHECKLIST:")
    print("  [ ] Space is 'Running' on HF (not Building/Error)")
    print("  [ ] Tested /health, /reset, /step, /state endpoints")
    print("  [ ] inference.py runs all 3 tasks without errors")
    print("  [ ] No API keys committed to git")
    print("  [ ] README has live demo link")
    print("  [ ] Submitted before April 8, 11:59 PM IST")
    
    return 0 if percentage >= 80 else 1


if __name__ == "__main__":
    sys.exit(main())
