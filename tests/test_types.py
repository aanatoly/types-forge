import pytest
import sqlite3
from http import HTTPStatus
from unittest.mock import Mock


@pytest.fixture
def valid_type_schema():
    """Provide a valid type schema with mandatory properties."""
    return {
        "title": "test_type",
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "icon": {"type": "string"},
            "status": {"type": "integer"},
            "extra_field": {"type": "integer"},
        },
        "propertyNames": {"pattern": "^[a-zA-Z0-9_]+$"},
        "required": ["title", "icon", "status"],
    }


def test_get_types_empty(test_client):
    """Test GET /types with no types in the database."""
    response = test_client.get("/types")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data == {"status": "success", "types": []}


def test_get_types_single_type(test_client, valid_type_schema):
    """Test GET /types with a single type."""
    # Create a type
    post_response = test_client.post_json("/types", valid_type_schema)
    assert post_response.status_code == HTTPStatus.OK

    # Get types
    response = test_client.get("/types")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert len(data["types"]) == 1
    type_data = data["types"][0]
    assert type_data["type_id"] == valid_type_schema["title"]
    assert type_data["type_schema"] == valid_type_schema
    assert type_data["table_name"].startswith("objects_")
    assert "test_type" in type_data["table_name"]


def test_get_types_multiple_types(test_client, valid_type_schema):
    """Test GET /types with multiple types."""
    # Create multiple types
    type_schemas = [{**valid_type_schema, "title": f"type_{i}"} for i in range(3)]
    for schema in type_schemas:
        post_response = test_client.post_json("/types", schema)
        assert post_response.status_code == HTTPStatus.OK

    # Get types
    response = test_client.get("/types")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert len(data["types"]) == 3
    type_ids = {t["type_id"] for t in data["types"]}
    assert type_ids == {"type_0", "type_1", "type_2"}
    for type_data, schema in zip(data["types"], type_schemas):
        assert type_data["type_schema"] == schema
        assert type_data["table_name"] == f"objects_type_{type_data['type_id'][-1]}"


def test_get_types_database_error(test_client, app, mocker):
    """Test GET /types with a simulated database error."""
    mock_cursor = Mock()
    mock_cursor.execute.side_effect = sqlite3.Error("Database failure")
    mocker.patch.object(app, "_cursor", mock_cursor)
    response = test_client.get("/types", status="*", expect_errors=True)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    data = response.json
    assert data["error"].startswith("Database error: Database failure")


def test_get_types_malformed_schema(test_client, app):
    """Test GET /types with a malformed type_schema in the database."""
    app._cursor.execute(
        "INSERT INTO type_metadata (type_id, type_schema, table_name) VALUES (?, ?, ?)",
        ("bad_type", "invalid_json", "objects_bad_type"),
    )
    app._conn.commit()
    response = test_client.get("/types", status="*", expect_errors=True)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json
    assert "error" in data
    assert "JSON decode error" in data["error"]


def test_get_types_large_number(test_client, valid_type_schema):
    """Test GET /types with a large number of types."""
    # Create 100 types
    for i in range(100):
        schema = {**valid_type_schema, "title": f"type_{i}"}
        post_response = test_client.post_json("/types", schema)
        assert post_response.status_code == HTTPStatus.OK

    response = test_client.get("/types")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert len(data["types"]) == 100
    type_ids = {t["type_id"] for t in data["types"]}
    assert type_ids == {f"type_{i}" for i in range(100)}


def test_get_types_mandatory_properties(test_client, valid_type_schema):
    """Test GET /types returns types with mandatory properties."""
    post_response = test_client.post_json("/types", valid_type_schema)
    assert post_response.status_code == HTTPStatus.OK

    response = test_client.get("/types")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert len(data["types"]) == 1
    schema = data["types"][0]["type_schema"]
    assert schema["properties"]["title"] == {"type": "string"}
    assert schema["properties"]["icon"] == {"type": "string"}
    assert schema["properties"]["status"] == {"type": "integer"}
    assert set(schema["required"]) >= {"title", "icon", "status"}


def test_get_types_cache_consistency(test_client, app, valid_type_schema):
    """Test GET /types uses database, not cache."""
    # Create a type
    post_response = test_client.post_json("/types", valid_type_schema)
    assert post_response.status_code == HTTPStatus.OK

    # Clear in-memory cache
    app._types.clear()

    response = test_client.get("/types")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert len(data["types"]) == 1
    assert data["types"][0]["type_id"] == valid_type_schema["title"]
