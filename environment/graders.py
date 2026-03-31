import sqlite3
import re
from environment.tasks import TASKS

def run_migration(schema_sql, seed_sql, migration_sql):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(schema_sql)
        if seed_sql:
            conn.executescript(seed_sql)
        conn.executescript(migration_sql)
        conn.commit()
        return {"ok": True, "error": None, "conn": conn}
    except sqlite3.Error as e:
        try: conn.close()
        except: pass
        return {"ok": False, "error": str(e), "conn": None}

def grade(task_id: str, fixed_sql: str) -> dict:
    if task_id not in TASKS:
        return {"score": 0.0, "error": f"Task {task_id} not found."}
    
    task = TASKS[task_id]
    scoring = task["scoring"]
    breakdown = {}
    total = 0.0

    # ── EASY GRADER ──────────────────────────────────────────────
    if task_id == "easy":
        r = run_migration(task["schema_context"], task["seed_sql"], fixed_sql)
        if r["ok"]:
            breakdown["executes_clean"] = scoring.get("executes_clean", 0.0)
            total += breakdown["executes_clean"]
            # Did they create the index specifically?
            try:
                idx = r["conn"].execute(
                    "SELECT name FROM sqlite_master WHERE type='index' "
                    "AND name='idx_users_phone'"
                ).fetchone()
                breakdown["index_created"] = scoring.get("index_created", 0.0) if idx else 0.0
            except:
                breakdown["index_created"] = 0.0
            total += breakdown["index_created"]
            if r["conn"]: r["conn"].close()
        else:
            breakdown["executes_clean"] = 0.0
            breakdown["error"] = r["error"]
            total = 0.05  # tiny partial for attempt

        # Penalize destructive ops
        has_destructive = bool(re.search(r'DROP|TRUNCATE|DELETE', fixed_sql, re.I))
        breakdown["no_destructive_ops"] = scoring.get("no_destructive_ops", 0.0) if not has_destructive else -0.1
        total += breakdown["no_destructive_ops"]

    # ── MEDIUM GRADER ────────────────────────────────────────────
    elif task_id == "medium":
        r = run_migration(task["schema_context"], task["seed_sql"], fixed_sql)
        if r["ok"]:
            breakdown["executes_clean"] = scoring.get("executes_clean", 0.0)
            total += breakdown["executes_clean"]
            # Were existing rows preserved?
            try:
                count = r["conn"].execute("SELECT COUNT(*) FROM products").fetchone()[0]
                preserved = count >= 3  # we seeded 3 rows
                breakdown["existing_rows_preserved"] = scoring.get("existing_rows_preserved", 0.0) if preserved else -0.1
            except:
                breakdown["existing_rows_preserved"] = -0.1
            total += breakdown["existing_rows_preserved"]
            if r["conn"]: r["conn"].close()
        else:
            breakdown["executes_clean"] = 0.0
            breakdown["error"] = r["error"]
            total = 0.05

        # Did they handle the NULL constraint? (added DEFAULT or removed NOT NULL)
        has_default = bool(re.search(r"DEFAULT\s+'[^']*'|DEFAULT\s+\d+|DEFAULT\s+NULL", fixed_sql, re.I))
        removed_not_null = bool(re.search(r"ADD\s+COLUMN\s+\w+\s+TEXT($|[\s,;])", fixed_sql, re.I))
        breakdown["null_constraint_handled"] = scoring.get("null_constraint_handled", 0.0) if (has_default or removed_not_null) else 0.0
        total += breakdown["null_constraint_handled"]

    # ── HARD GRADER ──────────────────────────────────────────────
    elif task_id == "hard":
        # Immediate penalty for destructive ops
        has_destructive = bool(re.search(r'DROP TABLE|TRUNCATE|DELETE FROM', fixed_sql, re.I))
        breakdown["no_destructive_ops"] = scoring.get("no_destructive_ops", 0.0) if not has_destructive else -0.3
        total += breakdown["no_destructive_ops"]

        r = run_migration(task["schema_context"], task["seed_sql"], fixed_sql)
        if r["ok"]:
            breakdown["executes_clean"] = scoring.get("executes_clean", 0.0)
            total += breakdown["executes_clean"]
            # THE REAL TEST: did premium customers get their discount?
            try:
                result = r["conn"].execute(
                    "SELECT "
                    "AVG(CASE WHEN customer_tier='premium' THEN discount_pct ELSE NULL END) as avg_premium, "
                    "AVG(CASE WHEN customer_tier='standard' THEN discount_pct ELSE NULL END) as avg_standard "
                    "FROM orders"
                ).fetchone()
                avg_premium = result[0] or 0.0
                avg_standard = result[1] or 0.0
                
                # If discount_pct is a ratio (e.g. 0.1), avg_premium should be > 0.05
                # The previous 5.0 was likely assuming absolute amount, 
                # but that conflicts with the final_amount ratio formula.
                premium_correct = avg_premium > 0.05
                standard_correct = avg_standard < 0.01  # near zero
                
                if premium_correct and standard_correct:
                    breakdown["premium_discount_correct"] = scoring.get("premium_discount_correct", 0.0)
                elif premium_correct:
                    breakdown["premium_discount_correct"] = scoring.get("premium_discount_correct", 0.0) * 0.7
                else:
                    breakdown["premium_discount_correct"] = 0.0  # silent bug NOT fixed
                total += breakdown["premium_discount_correct"]

                # Was final_amount correctly computed too?
                final_check = r["conn"].execute(
                    "SELECT COUNT(*) FROM orders WHERE final_amount > 0 AND "
                    "ABS(final_amount - (total_amount * (1.0 - discount_pct))) < 0.01"
                ).fetchone()[0]
                all_correct = final_check >= 5
                breakdown["final_amount_correct"] = scoring.get("final_amount_correct", 0.0) if all_correct else scoring.get("final_amount_correct", 0.0) * 0.3
                total += breakdown["final_amount_correct"]
            except Exception as e:
                breakdown["premium_discount_correct"] = 0.0
                breakdown["final_amount_correct"] = 0.0
                breakdown["validation_error"] = str(e)
            if r["conn"]: r["conn"].close()
        else:
            breakdown["executes_clean"] = 0.0
            breakdown["error"] = r["error"]
            total = max(total, 0.05)

    score = round(min(1.0, max(-1.0, total)), 4)
    return {
        "score": score,
        "breakdown": breakdown,
        "passed": score >= 0.6,
        "error": breakdown.get("error")
    }
