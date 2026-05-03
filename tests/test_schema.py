from loglens.schema import SchemaDiscovery

def test_schema_discovery():
    discovery = SchemaDiscovery()
    
    records = [
        {"level": "info", "message": "hello", "port": 80},
        {"level": "error", "message": "failed", "user_id": "123"},
        {"level": "warning", "message": "retrying", "port": "8080"}
    ]
    
    for r in records:
        discovery.process_record(r)
        
    schema = discovery.get_schema()
    
    assert "level" in schema
    assert "message" in schema
    assert "port" in schema
    assert "user_id" in schema
    
    # level and message appear in all 3 records (100%)
    assert schema["level"]["occurrence_rate"] == 1.0
    
    # port appears in 2 of 3 records
    assert abs(schema["port"]["occurrence_rate"] - (2/3)) < 0.001
    
    # port is both integer and string
    assert "integer" in schema["port"]["types"]
    assert "string" in schema["port"]["types"]
    
    # user_id appears in 1 of 3 records
    assert abs(schema["user_id"]["occurrence_rate"] - (1/3)) < 0.001
