"""
Migration test scenarios for sql-migration-env
15 test cases: 5 Easy, 5 Medium, 5 Hard (Silent Corruption)
"""

from app.models import MigrationScenario, DifficultyLevel, SchemaInfo


# ============================================================================
# EASY SCENARIOS: Syntax Errors (5 cases)
# ============================================================================

EASY_SCENARIOS = [
    MigrationScenario(
        id="easy_001_missing_comma",
        difficulty=DifficultyLevel.EASY,
        description="Missing comma between column definitions",
        setup_sql="""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL
            );
            INSERT INTO users (username) VALUES ('alice'), ('bob');
        """,
        broken_migration="""
            ALTER TABLE users 
            ADD COLUMN email TEXT NOT NULL
            ADD COLUMN age INTEGER;
        """,
        expected_schema=SchemaInfo(
            table_name="users",
            columns=[
                {"cid": 0, "name": "id", "type": "INTEGER", "notnull": 0, "dflt_value": None, "pk": 1},
                {"cid": 1, "name": "username", "type": "TEXT", "notnull": 1, "dflt_value": None, "pk": 0},
                {"cid": 2, "name": "email", "type": "TEXT", "notnull": 1, "dflt_value": None, "pk": 0},
                {"cid": 3, "name": "age", "type": "INTEGER", "notnull": 0, "dflt_value": None, "pk": 0},
            ],
            indexes=[],
            foreign_keys=[]
        ),
        validation_queries=["SELECT * FROM users"],
        expected_results=[[
            {"id": 1, "username": "alice", "email": "", "age": None},
            {"id": 2, "username": "bob", "email": "", "age": None}
        ]],
        hint="Check for missing commas between ADD COLUMN statements. Use DEFAULT for NOT NULL columns.",
        is_silent_corruption=False
    ),
    
    MigrationScenario(
        id="easy_002_typo_keyword",
        difficulty=DifficultyLevel.EASY,
        description="Typo in SQL keyword (TALBE instead of TABLE)",
        setup_sql="""
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name TEXT
            );
        """,
        broken_migration="""
            ALTER TALBE products ADD COLUMN price DECIMAL(10,2);
        """,
        expected_schema=SchemaInfo(
            table_name="products",
            columns=[
                {"cid": 0, "name": "id", "type": "INTEGER", "notnull": 0, "dflt_value": None, "pk": 1},
                {"cid": 1, "name": "name", "type": "TEXT", "notnull": 0, "dflt_value": None, "pk": 0},
                {"cid": 2, "name": "price", "type": "DECIMAL(10,2)", "notnull": 0, "dflt_value": None, "pk": 0},
            ],
            indexes=[],
            foreign_keys=[]
        ),
        validation_queries=["SELECT * FROM products"],
        expected_results=[[{"id": 1, "name": "Widget", "price": None}]], # Assuming standard SQLite loose typing
        hint="Check SQL keyword spelling. 'TABLE' not 'TALBE'.",
        is_silent_corruption=False
    ),
    
    MigrationScenario(
        id="easy_003_unclosed_quote",
        difficulty=DifficultyLevel.EASY,
        description="Unclosed string literal in DEFAULT value",
        setup_sql="""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                status TEXT DEFAULT 'pending'
            );
            INSERT INTO orders (status) VALUES ('shipped');
        """,
        broken_migration="""
            ALTER TABLE orders ADD COLUMN notes TEXT DEFAULT 'No notes;
        """,
        expected_schema=None,
        validation_queries=["SELECT * FROM orders"],
        expected_results=[[{"id": 1, "status": "shipped", "notes": "No notes"}]],
        hint="Check for closing quote on string literals.",
        is_silent_corruption=False
    ),
    
    MigrationScenario(
        id="easy_004_missing_semicolon",
        difficulty=DifficultyLevel.EASY,
        description="Missing semicolon between statements",
        setup_sql="""
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY
            );
        """,
        broken_migration="""
            ALTER TABLE logs ADD COLUMN level TEXT
            ALTER TABLE logs ADD COLUMN message TEXT
        """,
        expected_schema=None,
        validation_queries=["SELECT * FROM logs"],
        expected_results=[[]],
        hint="Each SQL statement should end with a semicolon.",
        is_silent_corruption=False
    ),
    
    MigrationScenario(
        id="easy_005_wrong_quotes",
        difficulty=DifficultyLevel.EASY,
        description="Using double quotes for string literal instead of single",
        setup_sql="""
            CREATE TABLE config (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """,
        broken_migration="""
            ALTER TABLE config ADD COLUMN description TEXT DEFAULT "Configuration parameter";
        """,
        expected_schema=None,
        validation_queries=["SELECT * FROM config"],
        expected_results=[[]],
        hint="SQLite uses single quotes for string literals. Double quotes are for identifiers.",
        is_silent_corruption=False
    ),
]


# ============================================================================
# MEDIUM SCENARIOS: Constraint Violations (5 cases)
# ============================================================================

MEDIUM_SCENARIOS = [
    MigrationScenario(
        id="medium_001_notnull_no_default",
        difficulty=DifficultyLevel.MEDIUM,
        description="Adding NOT NULL column without default on non-empty table",
        setup_sql="""
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                name TEXT
            );
            INSERT INTO customers (name) VALUES ('Alice'), ('Bob'), ('Charlie');
        """,
        broken_migration="""
            ALTER TABLE customers ADD COLUMN email TEXT NOT NULL;
        """,
        expected_schema=None,  # Will fail without default
        validation_queries=["SELECT * FROM customers"],
        expected_results=[[
            {"id": 1, "name": "Alice", "email": "unknown@example.com"},
            {"id": 2, "name": "Bob", "email": "unknown@example.com"},
            {"id": 3, "name": "Charlie", "email": "unknown@example.com"}
        ]],
        hint="SQLite: ALTER TABLE ... ADD COLUMN col TYPE NOT NULL DEFAULT 'value' - DEFAULT is required for existing rows!",
        is_silent_corruption=False
    ),
    
    MigrationScenario(
        id="medium_002_fk_violation",
        difficulty=DifficultyLevel.MEDIUM,
        description="Foreign key constraint violation on existing data",
        setup_sql="""
            CREATE TABLE departments (
                id INTEGER PRIMARY KEY,
                name TEXT
            );
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY,
                name TEXT,
                dept_id INTEGER
            );
            INSERT INTO departments VALUES (1, 'Engineering'), (2, 'Sales');
            INSERT INTO employees VALUES (1, 'Alice', 1), (2, 'Bob', 999); -- 999 doesn't exist
        """,
        broken_migration="""
            ALTER TABLE employees ADD FOREIGN KEY (dept_id) REFERENCES departments(id);
        """,
        expected_schema=None,
        validation_queries=["SELECT * FROM employees"],
        expected_results=[[
            {"id": 1, "name": "Alice", "dept_id": 1},
            {"id": 2, "name": "Bob", "dept_id": 999}
        ]],
        hint="SQLite cannot add FK constraints to existing tables. Consider: 1) Create new table with FK, 2) Copy data, 3) Drop old, 4) Rename. Or just validate data manually.",
        is_silent_corruption=False
    ),
    
    MigrationScenario(
        id="medium_003_unique_conflict",
        difficulty=DifficultyLevel.MEDIUM,
        description="Adding UNIQUE constraint on column with duplicates",
        setup_sql="""
            CREATE TABLE inventory (
                id INTEGER PRIMARY KEY,
                sku TEXT
            );
            INSERT INTO inventory (sku) VALUES ('ABC123'), ('ABC123'), ('XYZ789');
        """,
        broken_migration="""
            -- SQLite doesn't directly support ADD CONSTRAINT UNIQUE (requires table rebuild)
            -- For this test, assume a CREATE UNIQUE INDEX or table copy approach
            CREATE UNIQUE INDEX uniq_sku ON inventory(sku);
        """,
        expected_schema=None,
        validation_queries=["SELECT * FROM inventory order by id"],
        expected_results=[[
            {"id": 1, "sku": "ABC123"},
            {"id": 2, "sku": "ABC123-dupe"},
            {"id": 3, "sku": "XYZ789"}
        ]],
        hint="SQLite: Cannot use ALTER TABLE for UNIQUE. Use CREATE UNIQUE INDEX uniq_sku ON inventory(sku) instead!",
        is_silent_corruption=False
    ),
    
    MigrationScenario(
        id="medium_004_type_mismatch",
        difficulty=DifficultyLevel.MEDIUM,
        description="Adding CHECK constraint that existing data violates",
        setup_sql="""
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY,
                amount REAL
            );
            INSERT INTO transactions (amount) VALUES (100.50), (-50.25), (200.00);
        """,
        broken_migration="""
            PRAGMA foreign_keys=off;
            BEGIN TRANSACTION;
            CREATE TABLE new_transactions (id INTEGER PRIMARY KEY, amount REAL CHECK (amount >= 0));
            INSERT INTO new_transactions SELECT * FROM transactions;
            DROP TABLE transactions;
            ALTER TABLE new_transactions RENAME TO transactions;
            COMMIT;
            PRAGMA foreign_keys=on;
        """,
        expected_schema=None,
        validation_queries=["SELECT * FROM transactions WHERE amount < 0"],
        expected_results=[[{"id": 2, "amount": -50.25}]],  # Needs to handle the negative
        hint="SQLite cannot add CHECK constraints to existing tables. Options: 1) Fix data first, 2) Create new table with CHECK, 3) Skip constraint and validate in application.",
        is_silent_corruption=False
    ),
    
    MigrationScenario(
        id="medium_005_multiple_alter_conflicts",
        difficulty=DifficultyLevel.MEDIUM,
        description="Multiple ALTER statements with dependency conflicts",
        setup_sql="""
            CREATE TABLE posts (
                id INTEGER PRIMARY KEY,
                title TEXT
            );
            INSERT INTO posts (title) VALUES ('Hello World');
        """,
        broken_migration="""
            ALTER TABLE posts ADD COLUMN user_id INTEGER NOT NULL;
            -- SQLite ALTER doesn't support ADD FOREIGN KEY directly, but we test the logic
            -- Instead, typically you'd rebuild the table. This is illustrative of a logic error.
            CREATE TABLE new_posts (id INTEGER PRIMARY KEY, title TEXT, user_id INTEGER NOT NULL REFERENCES users(id));
            INSERT INTO new_posts SELECT id, title, 1 FROM posts;
            DROP TABLE posts;
            ALTER TABLE new_posts RENAME TO posts;
        """,
        expected_schema=None,
        validation_queries=["SELECT * FROM posts"],
        expected_results=[[{"id": 1, "title": "Hello World", "user_id": 0}]],
        hint="SQLite requires each ALTER TABLE in separate statement. Also: REFERENCES table must exist, NOT NULL needs DEFAULT.",
        is_silent_corruption=False
    ),
]


# ============================================================================
# HARD SCENARIOS: Silent Data Corruption (5 cases) - THE KILLER FEATURE
# ============================================================================

HARD_SCENARIOS = [
    MigrationScenario(
        id="hard_001_update_no_where",
        difficulty=DifficultyLevel.HARD,
        description="UPDATE without WHERE clause silently overwrites all rows",
        setup_sql="""
            CREATE TABLE user_settings (
                user_id INTEGER PRIMARY KEY,
                theme TEXT DEFAULT 'light',
                notifications INTEGER DEFAULT 1
            );
            INSERT INTO user_settings (user_id, theme) VALUES 
                (1, 'dark'), 
                (2, 'light'), 
                (3, 'dark');
        """,
        broken_migration="""
            -- User wants to update user 1's settings
            UPDATE user_settings SET theme = 'auto', notifications = 0;
        """,
        expected_schema=None,
        validation_queries=["SELECT * FROM user_settings ORDER BY user_id"],
        expected_results=[[
            {"user_id": 1, "theme": "auto", "notifications": 0},  # Only this should change
            {"user_id": 2, "theme": "light", "notifications": 1},  # Preserved
            {"user_id": 3, "theme": "dark", "notifications": 1}    # Preserved
        ]],
        hint="MISSING WHERE CLAUSE! This updates ALL rows instead of just user 1.",
        is_silent_corruption=True  # THE KEY FLAG
    ),
    
    MigrationScenario(
        id="hard_002_column_misalignment",
        difficulty=DifficultyLevel.HARD,
        description="INSERT INTO ... SELECT with wrong column order",
        setup_sql="""
            CREATE TABLE old_products (
                id INTEGER PRIMARY KEY,
                name TEXT,
                price REAL,
                category TEXT
            );
            CREATE TABLE new_products (
                id INTEGER PRIMARY KEY,
                category TEXT,
                name TEXT,
                price REAL
            );
            INSERT INTO old_products VALUES 
                (1, 'Widget', 19.99, 'Gadgets'),
                (2, 'Gadget', 29.99, 'Electronics');
        """,
        broken_migration="""
            INSERT INTO new_products (id, name, price, category)
            SELECT id, name, price, category FROM old_products;
        """,
        expected_schema=None,
        validation_queries=["SELECT * FROM new_products ORDER BY id"],
        expected_results=[[
            {"id": 1, "category": "Gadgets", "name": "Widget", "price": 19.99},  # Correct mapping
            {"id": 2, "category": "Electronics", "name": "Gadget", "price": 29.99}
        ]],
        hint="Column order in INSERT doesn't match SELECT. Data is scrambled (category in name field!).",
        is_silent_corruption=True
    ),
    
    MigrationScenario(
        id="hard_003_precision_loss",
        difficulty=DifficultyLevel.HARD,
        description="Implicit type conversion loses decimal precision",
        setup_sql="""
            CREATE TABLE measurements (
                id INTEGER PRIMARY KEY,
                value REAL
            );
            INSERT INTO measurements (value) VALUES (3.14159), (2.71828), (1.41421);
        """,
        broken_migration="""
            ALTER TABLE measurements ADD COLUMN rounded_value INTEGER;
            UPDATE measurements SET rounded_value = value;
        """,
        expected_schema=None,
        validation_queries=["SELECT * FROM measurements ORDER BY id"],
        expected_results=[[
            {"id": 1, "value": 3.14159, "rounded_value": 3},  # Truncated, not rounded properly by default cast in SQLite
            {"id": 2, "value": 2.71828, "rounded_value": 3},  # Should round to 3
            {"id": 3, "value": 1.41421, "rounded_value": 1}   # Should round to 1
        ]],
        hint="INTEGER type truncates REAL values natively depending on SQLite cast rules. Use ROUND() to be strictly correct.",
        is_silent_corruption=True
    ),
    
    MigrationScenario(
        id="hard_004_wrong_default_timestamp",
        difficulty=DifficultyLevel.HARD,
        description="Wrong default timestamp updates all rows on ALTER",
        setup_sql="""
            CREATE TABLE events (
                id INTEGER PRIMARY KEY,
                name TEXT,
                created_at TEXT
            );
            INSERT INTO events VALUES 
                (1, 'Event A', '2024-01-15 10:00:00'),
                (2, 'Event B', '2024-02-20 14:30:00');
        """,
        broken_migration="""
            ALTER TABLE events ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP;
        """,
        expected_schema=None,
        validation_queries=["SELECT * FROM events ORDER BY id"],
        expected_results=[[
            {"id": 1, "name": "Event A", "created_at": "2024-01-15 10:00:00", "updated_at": None},
            {"id": 2, "name": "Event B", "created_at": "2024-02-20 14:30:00", "updated_at": None}
        ]], # Explicitly want NULL for past events, not the current time
        hint="CURRENT_TIMESTAMP on existing rows sets them all to NOW, losing historical context. Add nullable first, or update cautiously.",
        is_silent_corruption=True
    ),
    
    MigrationScenario(
        id="hard_005_drop_column_data_loss",
        difficulty=DifficultyLevel.HARD,
        description="Dropping column with data then trying to recover",
        setup_sql="""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                temp_email TEXT
            );
            INSERT INTO users VALUES 
                (1, 'alice', 'alice@example.com'),
                (2, 'bob', 'bob@example.com');
        """,
        broken_migration="""
            ALTER TABLE users DROP COLUMN temp_email;
            ALTER TABLE users ADD COLUMN email TEXT;
        """,
        expected_schema=None,
        validation_queries=["SELECT * FROM users ORDER BY id"],
        expected_results=[[
            {"id": 1, "username": "alice", "email": "alice@example.com"},  # Data needs retaining
            {"id": 2, "username": "bob", "email": "bob@example.com"}
        ]],
        hint="Column drop is irreversible. Data is permanently lost. Need to RENAME column instead.",
        is_silent_corruption=True
    ),
    
    # hard_006: Subquery corruption
    MigrationScenario(
        id="hard_006_subquery_corruption",
        difficulty=DifficultyLevel.HARD,
        description="DELETE with correlated subquery deletes wrong rows",
        setup_sql="""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                status TEXT,
                amount REAL
            );
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                status TEXT
            );
            INSERT INTO users VALUES (1, 'active'), (2, 'inactive'), (3, 'active');
            INSERT INTO orders VALUES 
                (1, 1, 'pending', 100.00),
                (2, 2, 'completed', 200.00),
                (3, 3, 'pending', 150.00),
                (4, 1, 'completed', 300.00);
        """,
        broken_migration="""
            -- Intention: Delete pending orders from inactive users
            -- Bug: Correlated subquery logic is inverted!
            DELETE FROM orders 
            WHERE status = 'pending' 
            AND user_id IN (
                SELECT id FROM users WHERE status = 'active'
            );
        """,
        validation_queries=[
            "SELECT * FROM orders WHERE status='pending' ORDER BY id",
            "SELECT COUNT(*) as count FROM orders"
        ],
        expected_results=[
            [{"id": 1, "user_id": 1, "status": "pending", "amount": 100.0}],  # Should remain
            [{"count": 4}]  # All 4 should remain (none deleted)
        ],
        hint="Subquery selects 'active' users but should select 'inactive'. This deletes pending orders from ACTIVE users instead!",
        is_silent_corruption=True
    ),
    
    # hard_007: Transaction partial commit
    MigrationScenario(
        id="hard_007_transaction_partial",
        difficulty=DifficultyLevel.HARD,
        description="Transaction fails mid-way but partial changes persist",
        setup_sql="""
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY,
                balance REAL,
                version INTEGER DEFAULT 1
            );
            INSERT INTO accounts VALUES (1, 1000.00, 1), (2, 500.00, 1);
        """,
        broken_migration="""
            -- Transfer $200 from account 1 to account 2
            -- Bug: No transaction wrapper! If second UPDATE fails, first persists!
            UPDATE accounts SET balance = balance - 200, version = version + 1 WHERE id = 1;
            UPDATE accounts SET balance = balance + 200, version = version + 1 WHERE id = 999; -- Doesn't exist!
        """,
        validation_queries=[
            "SELECT * FROM accounts ORDER BY id",
            "SELECT SUM(balance) as total FROM accounts"
        ],
        expected_results=[
            [
                {"id": 1, "balance": 1000.0, "version": 1},  # Should be unchanged
                {"id": 2, "balance": 500.0, "version": 1}
            ],
            [{"total": 1500.0}]  # Total should remain 1500
        ],
        hint="No TRANSACTION/BEGIN/COMMIT wrapper! First UPDATE persists even if second fails. Money disappears!",
        is_silent_corruption=True
    ),
    
    # hard_008: Cartesian product from implicit join
    MigrationScenario(
        id="hard_008_cartesian_join",
        difficulty=DifficultyLevel.HARD,
        description="UPDATE with implicit join creates cartesian product",
        setup_sql="""
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name TEXT,
                price REAL
            );
            CREATE TABLE discounts (
                product_name TEXT,
                discount_percent REAL
            );
            INSERT INTO products VALUES 
                (1, 'Widget', 100.00),
                (2, 'Gadget', 200.00),
                (3, 'Tool', 150.00);
            INSERT INTO discounts VALUES 
                ('Widget', 10.0),
                ('Widget', 20.0),  -- Duplicate!
                ('Gadget', 15.0);
        """,
        broken_migration="""
            -- Apply discounts to products
            -- Bug: Implicit join without proper WHERE creates cartesian product!
            UPDATE products 
            SET price = price * (1 - discount_percent / 100)
            FROM discounts 
            WHERE products.name = discounts.product_name;
        """,
        validation_queries=[
            "SELECT * FROM products ORDER BY id",
            "SELECT SUM(price) as total FROM products"
        ],
        expected_results=[
            [
                {"id": 1, "name": "Widget", "price": 90.0},   # 10% off
                {"id": 2, "name": "Gadget", "price": 170.0}, # 15% off  
                {"id": 3, "name": "Tool", "price": 150.0}    # No discount
            ],
            [{"total": 410.0}]
        ],
        hint="SQLite doesn't support UPDATE...FROM! This may apply multiple discounts or fail silently. Use subquery: UPDATE products SET price = price * (SELECT...) WHERE EXISTS(SELECT 1 FROM discounts...)",
        is_silent_corruption=True
    ),
]


# ============================================================================
# SCENARIO REGISTRY
# ============================================================================

ALL_SCENARIOS = {
    s.id: s for s in EASY_SCENARIOS + MEDIUM_SCENARIOS + HARD_SCENARIOS
}

def get_scenario(scenario_id: str) -> MigrationScenario:
    """Retrieve scenario by ID"""
    if scenario_id not in ALL_SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario_id}")
    return ALL_SCENARIOS[scenario_id]

def get_scenarios_by_difficulty(difficulty: DifficultyLevel) -> list[MigrationScenario]:
    """Get all scenarios of a specific difficulty"""
    return [s for s in ALL_SCENARIOS.values() if s.difficulty == difficulty]

def get_random_scenario(difficulty: DifficultyLevel | None = None) -> MigrationScenario:
    """Get random scenario, optionally filtered by difficulty"""
    import random
    candidates = list(ALL_SCENARIOS.values())
    if difficulty:
        candidates = [s for s in candidates if s.difficulty == difficulty]
    return random.choice(candidates)
