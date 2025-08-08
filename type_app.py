from bottle import Bottle, request, response, HTTPError
from jsonschema import validate, ValidationError, Draft7Validator
from http import HTTPStatus
import sqlite3
import json
import re


class DynamicTypeApp(Bottle):
    def __init__(self, database="dynamic_tables.db", test_mode=False):
        super().__init__()
        self._test_mode = test_mode
        self._types = {}  # In-memory storage for types
        self._conn = sqlite3.connect(database, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row  # Set Dict row factory
        self._cursor = self._conn.cursor()

        # Initialize type_metadata table
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS type_metadata (
                type_id TEXT PRIMARY KEY,
                type_schema TEXT,
                table_name TEXT
            )
        """)
        self._conn.commit()

        # Define routes
        self.route("/types", method="POST", callback=self.add_type)
        self.route("/types", method="GET", callback=self.list_types)
        self.route("/types/<type_id>", method="GET", callback=self.get_type)
        self.route("/types/<type_id>", method="DELETE", callback=self.delete_type)

        self.route("/objects/<type_id>", method="POST", callback=self.add_object)
        self.route("/objects/<type_id>", method="GET", callback=self.list_objects)
        self.route(
            "/objects/<type_id>/<object_id:int>", method="GET", callback=self.get_object
        )
        self.route(
            "/objects/<type_id>/<object_id:int>",
            method="DELETE",
            callback=self.delete_object,
        )

        self.default_error_handler = self.custom_error_handler

    def custom_error_handler(self, error):
        print("=== error handler", type(error), error)
        response.content_type = "application/json"
        if isinstance(error, HTTPError) and isinstance(error.exception, sqlite3.Error):
            response.status = 500
            return json.dumps({"error": f"Database error: {str(error.exception)}"})
        elif isinstance(error, HTTPError) and isinstance(
            error.exception, json.JSONDecodeError
        ):
            response.status = 400
            return json.dumps({"error": f"JSON decode error: {str(error.exception)}"})
        elif isinstance(error, HTTPError):
            response.status = error.status_code
            return json.dumps({"error": error.body})
        elif isinstance(error.exception, json.JSONDecodeError):
            response.status = 400
            return json.dumps({"error": f"JSON decode error: {str(error.exception)}"})
        elif isinstance(error.exception, ValidationError):
            response.status = 400
            return json.dumps(
                {"error": f"Schema validation error: {str(error.exception)}"}
            )
        response.status = 400
        return json.dumps({"error": f"Unexpected error: {str(error.exception)}"})

    def json_prop_type_to_sql_type(self, json_type):
        """Map JSON schema types to SQLite types."""
        type_mapping = {
            "string": "TEXT",
            "integer": "INTEGER",
            "number": "REAL",
            "boolean": "INTEGER",  # SQLite uses 0/1 for booleans
            "null": "TEXT",  # Store null as TEXT
        }
        return type_mapping.get(json_type, "TEXT")  # Default to TEXT

    def create_sql_table(self, type_id, type_schema):
        """Create an SQLite table from a JSON schema."""
        # Sanitize type_id to create a valid table name
        table_name = re.sub(r"[^a-zA-Z0-9_]", "_", type_id)
        table_name = f"objects_{table_name}"

        # Extract properties from schema
        properties = type_schema.get("properties", {})
        if not properties:
            raise ValueError("Type schema must have properties")

        # Generate SQL columns
        columns = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
        for prop_name, prop_schema in properties.items():
            col_type = self.json_prop_type_to_sql_type(
                prop_schema.get("type", "string")
            )
            columns.append(f"{prop_name} {col_type}")
        columns.append("extra_properties TEXT")  # Add JSON column for extra properties

        # Create table
        create_table_sql = (
            f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)})"
        )
        self._cursor.execute(create_table_sql)
        self._conn.commit()
        return table_name

    def add_type(self):
        # Parse JSON type schema
        type_schema = request.json
        if not type_schema:
            raise HTTPError(HTTPStatus.BAD_REQUEST, "No JSON type schema provided")

        # Enforce valid SQL column names for properties
        type_schema["propertyNames"] = {"pattern": "^[a-zA-Z0-9_]+$"}

        # Enforce mandatory properties: title, icon, status
        properties = type_schema.get("properties", {})
        required = type_schema.get("required", [])

        # Check for mandatory properties
        mandatory_props = {
            "title": {"type": "string"},
            "icon": {"type": "string"},
            "status": {"type": "integer"},
        }
        missing_props = [prop for prop in mandatory_props if prop not in properties]
        if missing_props:
            raise HTTPError(
                HTTPStatus.BAD_REQUEST,
                f"Type schema must include properties: {', '.join(missing_props)}",
            )

        # Ensure properties match expected definitions
        for prop, prop_schema in mandatory_props.items():
            if properties.get(prop) != prop_schema:
                raise HTTPError(
                    HTTPStatus.BAD_REQUEST,
                    f"Property '{prop}' must match schema: {json.dumps(prop_schema)}",
                )

        # Ensure mandatory properties are in required list
        for prop in mandatory_props:
            if prop not in required:
                required.append(prop)
        type_schema["required"] = required

        # Validate JSON schema
        try:
            Draft7Validator.check_schema(type_schema)
        except ValidationError as e:
            raise HTTPError(HTTPStatus.BAD_REQUEST, f"Invalid JSON schema: {str(e)}")

        # Get type_id
        type_id = type_schema.get("title", f"type_{len(self._types) + 1}")
        if type_id in self._types:
            raise HTTPError(HTTPStatus.CONFLICT, f"Type '{type_id}' already exists")

        # Create SQLite table
        table_name = self.create_sql_table(type_id, type_schema)

        # Store type schema and table name
        self._types[type_id] = type_schema
        self._cursor.execute(
            "INSERT OR REPLACE INTO type_metadata (type_id, type_schema, table_name) VALUES (?, ?, ?)",
            (type_id, json.dumps(type_schema), table_name),
        )
        self._conn.commit()

        return {
            "status": "success",
            "type_id": type_id,
            "table_name": table_name,
            "message": f"Type '{type_id}' stored and table created",
        }

    def list_types(self):
        # Fetch all type metadata
        self._cursor.execute(
            "SELECT type_id, type_schema, table_name FROM type_metadata"
        )
        rows = self._cursor.fetchall()

        # Convert rows to list of dictionaries
        types_list = [
            {
                "type_id": row["type_id"],
                "type_schema": json.loads(row["type_schema"]),
                "table_name": row["table_name"],
            }
            for row in rows
        ]

        return {"status": "success", "types": types_list}

    def get_type(self, type_id):
        # Fetch type metadata
        self._cursor.execute(
            "SELECT type_id, type_schema, table_name FROM type_metadata WHERE type_id = ?",
            (type_id,),
        )
        row = self._cursor.fetchone()
        if not row:
            raise HTTPError(HTTPStatus.NOT_FOUND, f"Type '{type_id}' not found")

        # Convert row to dictionary
        type_data = {
            "type_id": row["type_id"],
            "type_schema": json.loads(row["type_schema"]),
            "table_name": row["table_name"],
        }

        return {"status": "success", "type": type_data}

    def delete_type(self, type_id):
        # Check if type exists
        self._cursor.execute(
            "SELECT table_name FROM type_metadata WHERE type_id = ?", (type_id,)
        )
        result = self._cursor.fetchone()
        if not result:
            raise HTTPError(HTTPStatus.NOT_FOUND, f"Type '{type_id}' not found")
        table_name = result["table_name"]

        # Drop the associated table
        self._cursor.execute(f"DROP TABLE IF EXISTS {table_name}")

        # Remove type from metadata and in-memory cache
        self._cursor.execute("DELETE FROM type_metadata WHERE type_id = ?", (type_id,))
        self._types.pop(type_id, None)

        self._conn.commit()

        return {
            "status": "success",
            "type_id": type_id,
            "message": f"Type '{type_id}' and its objects deleted successfully",
        }

    def add_object(self, type_id):
        # Parse object data
        data = request.json
        if not data:
            raise HTTPError(HTTPStatus.BAD_REQUEST, "No JSON data provided")

        # Retrieve type schema
        type_schema = self._types.get(type_id)
        if not type_schema:
            # Check database for type
            self._cursor.execute(
                "SELECT type_schema, table_name FROM type_metadata WHERE type_id = ?",
                (type_id,),
            )
            result = self._cursor.fetchone()
            if not result:
                raise HTTPError(HTTPStatus.NOT_FOUND, f"Type '{type_id}' not found")
            type_schema = json.loads(result["type_schema"])
            self._types[type_id] = type_schema  # Cache type schema
            table_name = result["table_name"]
        else:
            table_name = self._cursor.execute(
                "SELECT table_name FROM type_metadata WHERE type_id = ?", (type_id,)
            ).fetchone()["table_name"]

        # Validate object against type schema
        try:
            validate(instance=data, schema=type_schema)
        except ValidationError as e:
            print("=== object validation:", type(e), vars(e), e)
            response.status = HTTPStatus.BAD_REQUEST
            return {
                "error": "Validation failed",
                "details": {"path": f"{'/'.join(e.path)}", "message": e.message},
            }

        # Separate schema-defined properties and extra properties
        properties = type_schema.get("properties", {})
        defined_props = properties.keys()
        schema_props = {prop: data.get(prop) for prop in defined_props}
        extra_props = {k: v for k, v in data.items() if k not in defined_props}

        # Prepare SQL columns and values
        columns = list(
            defined_props
        )  # Use property names directly (validated as legal)
        columns.append("extra_properties")
        values = [schema_props.get(prop) for prop in defined_props]
        values.append(json.dumps(extra_props) if extra_props else None)

        # Insert object into table
        placeholders = ", ".join(["?" for _ in columns])
        insert_sql = (
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
        )
        self._cursor.execute(insert_sql, values)
        self._conn.commit()
        object_id = self._cursor.lastrowid

        return {
            "status": "success",
            "type_id": type_id,
            "object_id": object_id,
            "message": "Object inserted successfully",
        }

    def list_objects(self, type_id):
        # Retrieve table name
        self._cursor.execute(
            "SELECT table_name FROM type_metadata WHERE type_id = ?", (type_id,)
        )
        result = self._cursor.fetchone()
        if not result:
            raise HTTPError(HTTPStatus.NOT_FOUND, f"Type '{type_id}' not found")
        table_name = result["table_name"]

        # Fetch all objects
        limit = int(request.query.get("limit", 100))
        offset = int(request.query.get("offset", 0))
        self._cursor.execute(
            f"SELECT * FROM {table_name} LIMIT ? OFFSET ?", (limit, offset)
        )
        rows = self._cursor.fetchall()

        # Convert rows to list of dictionaries
        objects = []
        for row in rows:
            obj_data = dict(row)
            # Parse extra_properties from JSON
            if obj_data.get("extra_properties"):
                obj_data["extra_properties"] = json.loads(obj_data["extra_properties"])
            else:
                obj_data["extra_properties"] = {}
            objects.append(obj_data)

        return {"status": "success", "type_id": type_id, "objects": objects}

    def get_object(self, type_id, object_id):
        # Retrieve table name
        self._cursor.execute(
            "SELECT table_name FROM type_metadata WHERE type_id = ?", (type_id,)
        )
        result = self._cursor.fetchone()
        if not result:
            raise HTTPError(HTTPStatus.NOT_FOUND, f"Type '{type_id}' not found")
        table_name = result["table_name"]

        # Fetch object
        self._cursor.execute(f"SELECT * FROM {table_name} WHERE id = ?", (object_id,))
        row = self._cursor.fetchone()
        if not row:
            raise HTTPError(
                HTTPStatus.NOT_FOUND,
                f"Object {object_id} not found in type '{type_id}'",
            )

        # Convert row to dictionary (using Dict row factory)
        object_data = dict(row)

        # Parse extra_properties from JSON
        if object_data.get("extra_properties"):
            object_data["extra_properties"] = json.loads(
                object_data["extra_properties"]
            )
        else:
            object_data["extra_properties"] = {}

        return {
            "status": "success",
            "type_id": type_id,
            "object_id": object_id,
            "data": object_data,
        }

    def delete_object(self, type_id, object_id):
        # Retrieve table name
        self._cursor.execute(
            "SELECT table_name FROM type_metadata WHERE type_id = ?", (type_id,)
        )
        result = self._cursor.fetchone()
        if not result:
            raise HTTPError(HTTPStatus.NOT_FOUND, f"Type '{type_id}' not found")
        table_name = result["table_name"]

        # Check if object exists
        self._cursor.execute(f"SELECT id FROM {table_name} WHERE id = ?", (object_id,))
        if not self._cursor.fetchone():
            raise HTTPError(
                HTTPStatus.NOT_FOUND,
                f"Object {object_id} not found in type '{type_id}'",
            )

        # Delete object
        self._cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (object_id,))
        self._conn.commit()

        return {
            "status": "success",
            "type_id": type_id,
            "object_id": object_id,
            "message": "Object deleted successfully",
        }

    def close(self):
        """Close the database connection."""
        self._conn.close()
