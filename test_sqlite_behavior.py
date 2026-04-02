
import sqlite3

def test_sqlite_behavior():
    # Use isolation_level=None to mimic sandbox_db()
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.row_factory = sqlite3.Row
    
    db.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_tier TEXT DEFAULT 'standard',
            total_amount REAL NOT NULL
        );
    """)
    db.execute("INSERT INTO orders(customer_tier, total_amount) VALUES ('premium', 100.0), ('premium', 200.0), ('standard', 50.0);")
    
    # The "broken" migration using executescript (like DatabaseSandbox)
    broken_migration = """
        BEGIN TRANSACTION;
        ALTER TABLE orders ADD COLUMN discount_pct REAL DEFAULT 0.0;
        UPDATE orders
            SET discount_pct = total_amount * 0.10
            WHERE customer_tier = 'premium';
        ALTER TABLE orders ADD COLUMN final_amount REAL DEFAULT 0.0;
        UPDATE orders
            SET final_amount = total_amount * (1.0 - discount_pct);
        COMMIT;
    """
    
    try:
        db.executescript(broken_migration)
    except Exception as e:
        print(f"Error: {e}")

    rows = db.execute("SELECT * FROM orders").fetchall()
    print("Results (id, tier, total, discount, final):")
    for row in rows:
        print(f"{row['id']}, {row['customer_tier']}, {row['total_amount']}, {row['discount_pct']}, {row['final_amount']}")

if __name__ == "__main__":
    test_sqlite_behavior()
