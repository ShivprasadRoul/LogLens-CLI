"""Schema discovery for structured JSON logs."""

import json
from typing import Any, Dict, List, Optional, Set, Union
from pathlib import Path

class SchemaDiscovery:
    """Discovers and maintains schema for JSON logs using a flat dot-notation approach."""

    def __init__(self):
        """Initialize schema discovery.
        
        self.schema will map field names (dot-notated) to metadata:
        {
            "user.id": {"types": {"string"}, "count": 100},
            "response_time": {"types": {"int", "float"}, "count": 80}
        }
        """
        self.field_metadata: Dict[str, Dict[str, Any]] = {}
        self.total_records = 0

    def process_record(self, record: Dict[str, Any]) -> None:
        """Update schema metadata with a new record."""
        self.total_records += 1
        self._traverse(record, "")

    def _traverse(self, data: Any, prefix: str) -> None:
        """Recursively traverse the record to extract field metadata."""
        if isinstance(data, dict):
            for key, value in data.items():
                field_name = f"{prefix}.{key}" if prefix else key
                self._update_metadata(field_name, value)
                self._traverse(value, field_name)
        elif isinstance(data, list):
            # For lists, we track the field itself and potentially its elements
            # but we don't recurse into indices. We just sample the first few items
            # to see what types are inside.
            for item in data[:3]: # Sample first 3
                self._traverse(item, prefix)

    def _update_metadata(self, field_name: str, value: Any) -> None:
        """Update the type and count for a specific field."""
        if field_name not in self.field_metadata:
            self.field_metadata[field_name] = {"types": set(), "count": 0}
        
        val_type = self._get_type_name(value)
        self.field_metadata[field_name]["types"].add(val_type)
        self.field_metadata[field_name]["count"] += 1

    def _get_type_name(self, value: Any) -> str:
        """Map Python types to simple schema type names."""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return "unknown"

    def get_schema(self) -> Dict[str, Any]:
        """Return the discovered schema in a serializable format."""
        serializable_schema = {}
        for field, meta in self.field_metadata.items():
            serializable_schema[field] = {
                "types": sorted(list(meta["types"])),
                "occurrence_rate": round(meta["count"] / self.total_records, 4) if self.total_records > 0 else 0
            }
        return serializable_schema

    def save_schema(self, output_path: Path) -> None:
        """Save the discovered schema to a JSON file."""
        schema = {
            "total_records": self.total_records,
            "fields": self.get_schema()
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=4)

    def load_schema(self, schema_path: Path) -> Dict[str, Any]:
        """Load schema from file and update internal state."""
        if not schema_path.exists():
            return {}
        
        with open(schema_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self.total_records = data.get("total_records", 0)
        fields = data.get("fields", {})
        for field, meta in fields.items():
            self.field_metadata[field] = {
                "types": set(meta["types"]),
                "count": int(meta["occurrence_rate"] * self.total_records)
            }
        return fields

if __name__ == "__main__":
    # Quick test logic
    import sys
    if len(sys.argv) > 1:
        discovery = SchemaDiscovery()
        with open(sys.argv[1], "r") as f:
            records = json.load(f)
            for r in records:
                discovery.process_record(r)
        
        print(json.dumps(discovery.get_schema(), indent=2))
