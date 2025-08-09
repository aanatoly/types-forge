import pytest
import sqlite3
from http import HTTPStatus
from unittest.mock import Mock


@pytest.fixture
def valid_object_data():
    """Provide valid object data matching valid_type_schema."""
    return {"title": "Test Object", "icon": "icon.png", "status": 1, "extra_field": 42}


def test_objects_post_valid(test_client, valid_type, valid_object_data):
    """Test POST /objects/<type_id> with valid object data."""
    type_id = valid_type["title"]
    response = test_client.post_json(f"/objects/{type_id}", valid_object_data)
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert "object_id" in data
    assert isinstance(data["object_id"], int)


def test_objects_post_minimal(test_client, valid_type):
    """Test POST /objects/<type_id> with minimal valid data."""
    type_id = valid_type["title"]
    minimal_data = {"title": "Minimal Object", "icon": "min.png", "status": 0}
    response = test_client.post_json(f"/objects/{type_id}", minimal_data)
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert "object_id" in data


def test_objects_post_invalid_schema(test_client, valid_type):
    """Test POST /objects/<type_id> with invalid schema data."""
    type_id = valid_type["title"]
    invalid_data = {
        "title": "Invalid Object",
        "icon": "invalid.png",
        "status": "invalid",  # Should be integer
    }
    response = test_client.post_json(
        f"/objects/{type_id}", invalid_data, expect_errors=True
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json
    assert data == {
        "error": "Validation failed",
        "path": "status",
        "message": "'invalid' is not of type 'integer'",
    }


def test_objects_post_missing_required(test_client, valid_type):
    """Test POST /objects/<type_id> with missing required property."""
    type_id = valid_type["title"]
    incomplete_data = {"title": "Incomplete Object", "icon": "incomplete.png"}
    response = test_client.post_json(
        f"/objects/{type_id}", incomplete_data, expect_errors=True
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json
    assert data == {
        "error": "Validation failed",
        "path": "",
        "message": "'status' is a required property",
    }


def test_objects_post_non_existent_type(test_client, valid_object_data):
    """Test POST /objects/<type_id> with non-existent type_id."""
    response = test_client.post_json(
        "/objects/non_existent", valid_object_data, expect_errors=True
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    data = response.json
    assert data == {"error": "Type not found", "type": "non_existent"}


def test_objects_post_database_error(
    test_client, app, mocker, valid_type_schema, valid_object_data
):
    """Test POST /objects/<type_id> with simulated database error."""
    type_id = valid_type_schema["title"]
    test_client.post_json("/types", valid_type_schema)
    mock_cursor = Mock()
    mock_cursor.execute.side_effect = sqlite3.Error("Database failure")
    mocker.patch.object(app, "_cursor", mock_cursor)
    response = test_client.post_json(
        f"/objects/{type_id}", valid_object_data, expect_errors=True
    )
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    data = response.json
    assert "error" in data
    assert "Database error" in data["error"]


def test_objects_get_empty(test_client, valid_type_schema):
    """Test GET /objects/<type_id> with no objects."""
    type_id = valid_type_schema["title"]
    test_client.post_json("/types", valid_type_schema)
    response = test_client.get(f"/objects/{type_id}")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert data["objects"] == []


def test_objects_get_single(test_client, valid_type, valid_object_data):
    """Test GET /objects/<type_id> with one object."""
    type_id = valid_type["title"]
    post_response = test_client.post_json(f"/objects/{type_id}", valid_object_data)
    assert post_response.status_code == HTTPStatus.OK
    response = test_client.get(f"/objects/{type_id}")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert len(data["objects"]) == 1
    assert data["objects"][0]["title"] == valid_object_data["title"]
    assert data["objects"][0]["icon"] == valid_object_data["icon"]
    assert data["objects"][0]["status"] == valid_object_data["status"]


def test_objects_get_non_existent_type(test_client):
    """Test GET /objects/<type_id> with non-existent type_id."""
    response = test_client.get("/objects/non_existent", expect_errors=True)
    assert response.status_code == HTTPStatus.NOT_FOUND
    data = response.json
    assert data == {"error": "Type not found", "type": "non_existent"}


def test_objects_get_database_error(test_client, app, mocker, valid_type_schema):
    """Test GET /objects/<type_id> with simulated database error."""
    type_id = valid_type_schema["title"]
    test_client.post_json("/types", valid_type_schema)
    mock_cursor = Mock()
    mock_cursor.execute.side_effect = sqlite3.Error("Database failure")
    mocker.patch.object(app, "_cursor", mock_cursor)
    response = test_client.get(f"/objects/{type_id}", expect_errors=True)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    data = response.json
    assert "error" in data
    assert "Database error" in data["error"]


def test_objects_get_specific(test_client, valid_type, valid_object_data):
    """Test GET /objects/<type_id>/<object_id> for existing object."""
    type_id = valid_type["title"]
    post_response = test_client.post_json(f"/objects/{type_id}", valid_object_data)
    assert post_response.status_code == HTTPStatus.OK
    object_id = post_response.json["object_id"]
    response = test_client.get(f"/objects/{type_id}/{object_id}")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    assert data["data"]["title"] == valid_object_data["title"]
    assert data["data"]["icon"] == valid_object_data["icon"]
    assert data["data"]["status"] == valid_object_data["status"]


def test_objects_get_non_existent(test_client, valid_type):
    """Test GET /objects/<type_id>/<object_id> with non-existent object."""
    type_id = valid_type["title"]
    response = test_client.get(f"/objects/{type_id}/non_existent", expect_errors=True)
    assert response.status_code == HTTPStatus.NOT_FOUND
    data = response.json
    print("=== data", data)
    assert data == {"error": "Not found: '/objects/test_type/non_existent'"}


def test_objects_delete_existing(test_client, valid_type, valid_object_data):
    """Test DELETE /objects/<type_id>/<object_id> for existing object."""
    type_id = valid_type["title"]
    post_response = test_client.post_json(f"/objects/{type_id}", valid_object_data)
    assert post_response.status_code == HTTPStatus.OK
    object_id = post_response.json["object_id"]
    response = test_client.delete(f"/objects/{type_id}/{object_id}")
    assert response.status_code == HTTPStatus.OK
    data = response.json
    assert data["status"] == "success"
    # Verify object is deleted
    get_response = test_client.get(
        f"/objects/{type_id}/{object_id}", expect_errors=True
    )
    assert get_response.status_code == HTTPStatus.NOT_FOUND


def test_objects_delete_non_existent(test_client, valid_type_schema):
    """Test DELETE /objects/<type_id>/<object_id> with non-existent object."""
    type_id = valid_type_schema["title"]
    test_client.post_json("/types", valid_type_schema)
    response = test_client.delete(
        f"/objects/{type_id}/non_existent", expect_errors=True
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    data = response.json
    assert data == {"error": "Not found: '/objects/test_type/non_existent'"}


def test_objects_delete_non_existent_type(test_client):
    """Test DELETE /objects/<type_id>/<object_id> with non-existent type."""
    response = test_client.delete("/objects/non_existent/1", expect_errors=True)
    assert response.status_code == HTTPStatus.NOT_FOUND
    data = response.json
    assert data == {"error": "Type not found", "type": "non_existent"}


def test_objects_delete_database_error(
    test_client, app, mocker, valid_type, valid_object_data
):
    """Test DELETE /objects/<type_id>/<object_id> with simulated database error."""
    type_id = valid_type["title"]
    post_response = test_client.post_json(f"/objects/{type_id}", valid_object_data)
    assert post_response.status_code == HTTPStatus.OK
    object_id = post_response.json["object_id"]
    mock_cursor = Mock()
    mock_cursor.execute.side_effect = sqlite3.Error("Database failure")
    mocker.patch.object(app, "_cursor", mock_cursor)
    response = test_client.delete(f"/objects/{type_id}/{object_id}", expect_errors=True)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    data = response.json
    assert data == {"error": "Database error: Database failure"}
