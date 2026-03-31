from typing import Any, Dict, List, TypedDict

class ScoringDef(TypedDict):
    executes_clean: float
    index_created: float = 0.0
    no_destructive_ops: float = 0.0
    existing_rows_preserved: float = 0.0
    null_constraint_handled: float = 0.0
    premium_discount_correct: float = 0.0
    final_amount_correct: float = 0.0

class TaskDef(TypedDict):
    pr_title: str
    broken_sql: str
    schema_context: str
    seed_sql: str
    seed_data: List[Dict[str, Any]]
    task_description: str
    scoring: ScoringDef

TASKS: Dict[str, TaskDef] = {
    "easy": {
        "pr_title": "Fix column types in users table",
        "broken_sql": "ALTER TABLE users ADD COLUMN phone_number TEXTT;\nCREATE INDX idx_users_phone ON users(phone_number);",
        "schema_context": "CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);",
        "seed_sql": "INSERT INTO users (email) VALUES ('alice@example.com'), ('bob@example.com');",
        "seed_data": [{"id": 1, "email": "alice@example.com"}, {"id": 2, "email": "bob@example.com"}],
        "task_description": "Fix the syntax typos in the migration script: 'TEXTT' -> 'TEXT' and 'INDX' -> 'INDEX'.",
        "scoring": {
            "executes_clean": 0.4,
            "index_created": 0.4,
            "no_destructive_ops": 0.2
        }
    },
    "medium": {
        "pr_title": "Add NOT NULL columns to products",
        "broken_sql": "ALTER TABLE products ADD COLUMN category TEXT NOT NULL;\nALTER TABLE products ADD COLUMN warehouse_code TEXT NOT NULL;",
        "schema_context": "CREATE TABLE products (id INTEGER PRIMARY KEY, sku TEXT, price REAL, stock INTEGER);",
        "seed_sql": "INSERT INTO products (sku, price, stock) VALUES ('SKU001', 9.99, 100), ('SKU002', 49.99, 10), ('SKU003', 25.00, 50);",
        "seed_data": [{"id": 1, "sku": "SKU001"}, {"id": 2, "sku": "SKU002"}, {"id": 3, "sku": "SKU003"}],
        "task_description": "Adding a NOT NULL column to a populated table fails in SQLite without a DEFAULT. Add a DEFAULT value or remove NOT NULL.",
        "scoring": {
            "executes_clean": 0.3,
            "existing_rows_preserved": 0.3,
            "null_constraint_handled": 0.4
        }
    },
    "hard": {
        "pr_title": "Safe discount calculation migration",
        "broken_sql": """
BEGIN TRANSACTION;
ALTER TABLE orders ADD COLUMN discount_pct REAL DEFAULT 0.0;
UPDATE orders SET discount_pct = total_amount * 0.1
  WHERE customer_tier = 'premium';
ALTER TABLE orders ADD COLUMN final_amount REAL DEFAULT 0.0;
UPDATE orders SET final_amount = total_amount * (1.0 - discount_pct);
COMMIT;
        """,
        "schema_context": "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, customer_tier TEXT, total_amount REAL, status TEXT);",
        "seed_sql": """
INSERT INTO orders (customer_id, customer_tier, total_amount, status) VALUES 
(1, 'premium', 500.0, 'completed'),
(2, 'standard', 100.0, 'completed'),
(3, 'premium', 1200.0, 'completed'),
(4, 'standard', 50.0, 'completed'),
(5, 'premium', 300.0, 'completed');
        """,
        "seed_data": [
            {"id": 1, "customer_tier": "premium", "total_amount": 500.0},
            {"id": 2, "customer_tier": "standard", "total_amount": 100.0}
        ],
        "task_description": "This migration has a silent bug in transaction/execution order causing incorrect discount calculations. Ensure premium customers get their 10% discount applied to the final_amount correctly.",
        "scoring": {
            "no_destructive_ops": 0.2,
            "executes_clean": 0.2,
            "premium_discount_correct": 0.3,
            "final_amount_correct": 0.3
        }
    }
}
