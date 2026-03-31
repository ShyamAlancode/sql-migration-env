from app.models import Action, Observation, DifficultyLevel, MigrationScenario
from app.database import sandbox_db
import json

def test_models():
    action = Action(
        fixed_sql="SELECT 1",
        explanation="Test",
        confidence=0.9
    )
    assert action.confidence == 0.9
    
    # Test serialization
    data = action.model_dump_json()
    assert '"fixed_sql":"SELECT 1"' in data
    
    print("OK: Models work")

def test_database():
    with sandbox_db() as db:
        # Test setup
        success, err = db.execute_script("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT);")
        if not success:
            print(f"FAILED setup: {err}")
            return
        assert success
        
        # Test query
        success, rows, err = db.execute_query("SELECT * FROM test")
        assert success
        assert rows == []
        
        # Test hash
        hash1 = db.compute_hash()
        db.execute_script("INSERT INTO test (id, name) VALUES (1, 'Testing');")
        hash2 = db.compute_hash()
        assert hash1 != hash2
        
        # Test schema info
        info = db.get_schema_info("test")
        assert info["table_name"] == "test"
        assert len(info["columns"]) == 2
        
        print("OK: Database sandbox works")

if __name__ == "__main__":
    try:
        test_models()
        test_database()
        print("Phase 1 complete!")
    except Exception as e:
        print(f"Phase 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
