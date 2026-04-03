"""
Pre-Submission Checklist for OpenEnv Hackathon 2026
Verifies every disqualification criterion before git push.
Run: python pre_submit_check.py
"""
import os, re, sys

PASS_STR = "  PASS"
FAIL_STR = "  FAIL"

def header(n, title):
    print(f"\n{'='*60}")
    print(f"CHECK {n}: {title}")
    print('='*60)

errors = []

# ---- CHECK 1: inference.py in root ---------------------------
header(1, "inference.py in root directory")
if os.path.exists("inference.py"):
    print(PASS_STR, "inference.py exists at project root")
else:
    print(FAIL_STR, "inference.py MISSING from root")
    errors.append("inference.py missing")

src = open("inference.py", encoding="utf-8").read()

# ---- CHECK 2: Mandatory env vars -----------------------------
header(2, "Mandatory env vars (API_BASE_URL, MODEL_NAME, HF_TOKEN)")
for var in ["API_BASE_URL", "MODEL_NAME", "HF_TOKEN", "OPENAI_API_KEY"]:
    if var in src:
        print(PASS_STR, f"{var} defined")
    else:
        print(FAIL_STR, f"{var} MISSING")
        errors.append(f"{var} missing from inference.py")

# ---- CHECK 3: OpenAI client ----------------------------------
header(3, "OpenAI client used for all LLM calls")
if "from openai import OpenAI" in src and "OpenAI(" in src:
    print(PASS_STR, "OpenAI client imported and instantiated")
else:
    print(FAIL_STR, "OpenAI client not used")
    errors.append("OpenAI client missing")

# ---- CHECK 4: Mandatory log format ---------------------------
header(4, "[START] / [STEP] / [END] stdout format")
for tag in ["[START]", "[STEP]", "[END]"]:
    if tag in src:
        print(PASS_STR, f"{tag} emitted")
    else:
        print(FAIL_STR, f"{tag} MISSING")
        errors.append(f"{tag} missing")

if all(f in src for f in ["task=", "env=", "model="]):
    print(PASS_STR, "[START] has task= env= model= fields")
else:
    print(FAIL_STR, "[START] missing required fields")

if all(f in src for f in ["step=", "action=", "reward=", "done=", "error="]):
    print(PASS_STR, "[STEP]  has step= action= reward= done= error= fields")
else:
    print(FAIL_STR, "[STEP] missing required fields")

if all(f in src for f in ["success=", "steps=", "rewards="]):
    print(PASS_STR, "[END]   has success= steps= rewards= fields")
else:
    print(FAIL_STR, "[END] missing required fields")

# ---- CHECK 5: Stdout discipline  -----------------------------
header(5, "Stdout discipline -- only spec lines go to stdout")
# Join continuation lines so multiline print() calls are one logical line
joined = re.sub(r',\s*\n\s*', ', ', src)      # join comma-continued lines
joined = re.sub(r'\(\s*\n\s*', '(', joined)   # join opening-paren continuations

dirty = []
for line in joined.split("\n"):
    stripped = line.strip()
    if not stripped.startswith("print("):
        continue
    if "file=sys.stderr" in line:
        continue
    spec_tags = ["[START]", "[STEP]", "[END]"]
    if any(t in line for t in spec_tags):
        continue
    dirty.append(stripped[:90])

if dirty:
    print(FAIL_STR, f"{len(dirty)} non-spec print(s) going to stdout:")
    for d in dirty:
        print("    >>", d)
    errors.append("non-spec stdout prints")
else:
    print(PASS_STR, "All non-spec output routed to sys.stderr")

# ---- CHECK 6: 3+ tasks --------------------------------------
header(6, "3+ tasks defined (easy / medium / hard)")
from app.scenarios import ALL_SCENARIOS, EASY_SCENARIOS, MEDIUM_SCENARIOS, HARD_SCENARIOS
print(PASS_STR, f"Total scenarios : {len(ALL_SCENARIOS)}")
print(PASS_STR, f"Easy={len(EASY_SCENARIOS)}  Medium={len(MEDIUM_SCENARIOS)}  Hard={len(HARD_SCENARIOS)}")
if len(ALL_SCENARIOS) >= 3:
    print(PASS_STR, "Minimum 3 tasks requirement satisfied")
else:
    print(FAIL_STR, "Fewer than 3 tasks found")
    errors.append("fewer than 3 tasks")

# ---- CHECK 7: Grader reward range 0.0-1.0 -------------------
header(7, "Grader reward range [0.0, 1.0]")
from app.grader import MigrationGrader
from app.models import Action

test_cases = [
    ("easy_001_missing_comma",              "SELECT 1;", "easy"  ),
    ("medium_001_notnull_no_default",       "SELECT 1;", "medium"),
    ("hard_001_execution_order_corruption", "SELECT 1;", "hard"  ),
]
for sid, sql, diff in test_cases:
    scenario = ALL_SCENARIOS[sid]
    result = MigrationGrader(scenario).grade(
        Action(fixed_sql=sql, explanation="test", confidence=0.5)
    )
    norm = result.total_score / 100.0
    in_range = 0.0 <= norm <= 1.0
    st = PASS_STR if in_range else FAIL_STR
    print(st, f"{diff:6s}  [{sid}]  raw={result.total_score:.1f}/100  normalized={norm:.4f}")
    if not in_range:
        errors.append(f"score out of range for {sid}")

# Verify a near-perfect fix also stays <=1.0
perfect_sql = "ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT '', ADD COLUMN age INTEGER;"
scenario = ALL_SCENARIOS["easy_001_missing_comma"]
result = MigrationGrader(scenario).grade(
    Action(fixed_sql=perfect_sql, explanation="perfect fix", confidence=1.0)
)
norm = result.total_score / 100.0
st = PASS_STR if norm <= 1.0 else FAIL_STR
print(st, f"Perfect-fix score: raw={result.total_score}  normalized={norm:.4f}  (must be <=1.0)")

# ---- CHECK 8: openenv.yaml  ---------------------------------
header(8, "openenv.yaml manifest compliance")
import yaml
with open("openenv.yaml", encoding="utf-8") as f:
    manifest = yaml.safe_load(f)

for k in ["name", "version", "entry_point", "port", "tasks"]:
    val = manifest.get(k)
    ok = val is not None
    print(PASS_STR if ok else FAIL_STR, f"{k}: {val}")
    if not ok:
        errors.append(f"openenv.yaml missing {k}")

if manifest.get("port") == 7860:
    print(PASS_STR, "port=7860 (HF Spaces requirement)")
else:
    print(FAIL_STR, f"port={manifest.get('port')} (must be 7860)")
    errors.append("wrong port in openenv.yaml")

tasks_in_yaml = manifest.get("tasks", [])
if len(tasks_in_yaml) >= 3:
    print(PASS_STR, f"{len(tasks_in_yaml)} tasks declared in manifest")
else:
    print(FAIL_STR, "fewer than 3 tasks in openenv.yaml")
    errors.append("fewer than 3 tasks in yaml")

# ---- CHECK 9: Dockerfile ------------------------------------
header(9, "Dockerfile -- port 7860, HEALTHCHECK, non-root user")
df = open("Dockerfile", encoding="utf-8").read()
dockerfile_checks = [
    ("EXPOSE 7860",            "EXPOSE 7860"  ),
    ("Port 7860 in CMD",       '"7860"'       ),
    ("HEALTHCHECK defined",    "HEALTHCHECK"  ),
    ("Non-root user appuser",  "appuser"      ),
    ("python:3.11 base image", "python:3.11"  ),
]
for label, token in dockerfile_checks:
    ok = token in df
    print(PASS_STR if ok else FAIL_STR, label)
    if not ok:
        errors.append(f"Dockerfile missing: {label}")

# ---- CHECK 10: Runtime estimate -----------------------------
header(10, "Runtime estimate (must be < 20 min on 2vCPU/8GB)")
steps_match = re.findall(r"MAX_STEPS\s*=\s*(\d+)", src)
max_steps   = int(steps_match[0]) if steps_match else 999
tasks_count = 3
est_secs    = max_steps * tasks_count * 15   # 15s per LLM call (conservative)
print(PASS_STR if max_steps <= 5 else FAIL_STR,
      f"MAX_STEPS={max_steps} (recommended <= 5)")
print(PASS_STR if est_secs < 1200 else FAIL_STR,
      f"Estimated worst-case runtime: {est_secs}s ({est_secs//60}m{est_secs%60}s) limit=20min")
if est_secs >= 1200:
    errors.append("estimated runtime >20min")

# ---- FINAL RESULT -------------------------------------------
print("\n" + "="*60)
if not errors:
    print("FINAL RESULT: ALL CHECKS PASSED -- SAFE TO SUBMIT")
else:
    print(f"FINAL RESULT: {len(errors)} ISSUE(S) FOUND -- FIX BEFORE SUBMITTING:")
    for e in errors:
        print(f"  - {e}")
print("="*60)
