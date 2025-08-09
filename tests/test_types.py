import sqlite3
from http import HTTPStatus
from unittest.mock import Mock


def test_types_get_empty(test_client):
    """Test GET /types with no types in the database."""
    response = test_client.get("/types")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data == {"status": "success", "types": []}


def test_types_get_single_type(test_client, valid_type_schema):
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


def test_types_get_multiple_types(test_client, valid_type_schema):
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


def test_types_get_database_error_on_all(test_client, app, mocker):
    """Test GET /types with a simulated database error."""
    mock_cursor = Mock()
    mock_cursor.execute.side_effect = sqlite3.Error("Database failure")
    mocker.patch.object(app, "_cursor", mock_cursor)
    response = test_client.get("/types", status="*", expect_errors=True)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    data = response.json
    assert data["error"] == "Database error: Database failure"


def test_types_get_database_error_on_single(
    test_client, app, mocker, valid_type_schema
):
    """Test GET /types/<type_id> with simulated database error."""
    post_response = test_client.post_json("/types", valid_type_schema)
    assert post_response.status_code == HTTPStatus.OK
    type_id = valid_type_schema["title"]
    mock_cursor = Mock()
    mock_cursor.execute.side_effect = sqlite3.Error("Database failure")
    mocker.patch.object(app, "_cursor", mock_cursor)
    response = test_client.get(f"/types/{type_id}", expect_errors=True)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    data = response.json
    assert data["error"].startswith("Database error: Database failure")


def test_types_get_malformed_schema(test_client, app):
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


def test_types_get_large_number(test_client, valid_type_schema):
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


def test_types_get_mandatory_properties(test_client, valid_type_schema):
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


def test_types_get_cache_consistency(test_client, app, valid_type_schema):
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


def test_types_get_existing(test_client, valid_type_schema):
    """Test GET /types/<type_id> for existing type."""
    post_response = test_client.post_json("/types", valid_type_schema)
    assert post_response.status_code == HTTPStatus.OK
    type_id = valid_type_schema["title"]
    response = test_client.get(f"/types/{type_id}")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert data["type"]["type_id"] == type_id
    assert data["type"]["type_schema"] == valid_type_schema
    assert data["type"]["table_name"].startswith("objects_")


def test_types_get_non_existent(test_client):
    """Test GET /types/<type_id> for non-existent type."""
    response = test_client.get("/types/non_existent", expect_errors=True)
    assert response.status_code == HTTPStatus.NOT_FOUND
    data = response.json
    assert data == {"error": "Type not found", "type": "non_existent"}


def test_types_post_valid(test_client, valid_type_schema):
    """Test POST /types with a valid schema."""
    response = test_client.post_json("/types", valid_type_schema)
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert data["type_id"] == valid_type_schema["title"]
    # Verify type is stored
    get_response = test_client.get("/types")
    assert get_response.status_code == HTTPStatus.OK
    assert len(get_response.json["types"]) == 1
    assert get_response.json["types"][0]["type_id"] == valid_type_schema["title"]


def test_types_post_additional_properties(test_client, valid_type_schema):
    """Test POST /types with additional properties."""
    schema = {
        **valid_type_schema,
        "properties": {
            **valid_type_schema["properties"],
            "extra_field2": {"type": "string"},
        },
    }
    response = test_client.post_json("/types", schema)
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert data["type_id"] == schema["title"]


def test_types_post_multiple_unique(test_client, valid_type_schema):
    """Test POST /types with multiple unique types."""
    schemas = [{**valid_type_schema, "title": f"type_{i}"} for i in range(3)]
    for schema in schemas:
        response = test_client.post_json("/types", schema)
        assert response.status_code == HTTPStatus.OK
        assert response.json["type_id"] == schema["title"]
    get_response = test_client.get("/types")
    assert len(get_response.json["types"]) == 3
    assert {t["type_id"] for t in get_response.json["types"]} == {
        "type_0",
        "type_1",
        "type_2",
    }


def test_types_post_minimal_schema(test_client):
    """Test POST /types with minimal schema."""
    schema = {
        "title": "minimal_type",
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "icon": {"type": "string"},
            "status": {"type": "integer"},
        },
        "required": ["title", "icon", "status"],
        "propertyNames": {"pattern": "^[a-zA-Z0-9_]+$"},
    }
    response = test_client.post_json("/types", schema)
    assert response.status_code == HTTPStatus.OK
    assert response.json["type_id"] == "minimal_type"


def test_types_post_missing_required_property(test_client, valid_type_schema):
    """Test POST /types with missing required property."""
    schema = {
        **valid_type_schema,
        "properties": {"title": {"type": "string"}, "icon": {"type": "string"}},
        "required": [],
        # "required": ["title", "icon"],
    }
    response = test_client.post_json("/types", schema, expect_errors=True)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json
    assert data == {
        "error": "Mandatory properties are missing",
        "missing_props": ["status"],
    }


def test_types_post_invalid_json(test_client):
    """Test POST /types with invalid JSON."""
    response = test_client.post(
        "/types", "{invalid", content_type="application/json", expect_errors=True
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json
    assert "error" in data
    assert "JSON decode error" in data["error"]


def test_types_post_duplicate_type_id(test_client, valid_type_schema):
    """Test POST /types with duplicate type_id."""
    test_client.post_json("/types", valid_type_schema)
    response = test_client.post_json("/types", valid_type_schema, expect_errors=True)
    assert response.status_code == HTTPStatus.CONFLICT
    data = response.json
    assert data == {"error": "Type already exists", "type": "test_type"}


def test_types_post_database_error(test_client, app, mocker, valid_type_schema):
    """Test POST /types with simulated database error."""
    mock_cursor = Mock()
    mock_cursor.execute.side_effect = sqlite3.Error("Database failure")
    mocker.patch.object(app, "_cursor", mock_cursor)
    response = test_client.post_json("/types", valid_type_schema, expect_errors=True)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    data = response.json
    assert data["error"].startswith("Database error: Database failure")


def test_types_delete_existing(test_client, valid_type_schema):
    """Test DELETE /types/<type_id> for existing type."""
    post_response = test_client.post_json("/types", valid_type_schema)
    assert post_response.status_code == HTTPStatus.OK
    type_id = valid_type_schema["title"]
    response = test_client.delete(f"/types/{type_id}")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    # Verify type is deleted
    get_response = test_client.get(f"/types/{type_id}", expect_errors=True)
    assert get_response.status_code == HTTPStatus.NOT_FOUND


def test_types_delete_non_existent(test_client):
    """Test DELETE /types/<type_id> for non-existent type."""
    response = test_client.delete("/types/non_existent", expect_errors=True)
    assert response.status_code == HTTPStatus.NOT_FOUND
    data = response.json
    print("=== data", data)
    assert data == {"error": "Type not found", "type": "non_existent"}


def test_types_delete_database_error(test_client, app, mocker, valid_type_schema):
    """Test DELETE /types/<type_id> with simulated database error."""
    post_response = test_client.post_json("/types", valid_type_schema)
    assert post_response.status_code == HTTPStatus.OK
    type_id = valid_type_schema["title"]
    mock_cursor = Mock()
    mock_cursor.execute.side_effect = sqlite3.Error("Database failure")
    mocker.patch.object(app, "_cursor", mock_cursor)
    response = test_client.delete(f"/types/{type_id}", expect_errors=True)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    data = response.json
    assert data["error"].startswith("Database error: Database failure")
