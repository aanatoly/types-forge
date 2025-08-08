from type_app import DynamicTypeApp

if __name__ == "__main__":
    app = DynamicTypeApp()
    try:
        app.run(host="localhost", port=8080, debug=True)
    finally:
        # Ensure database connection is closed
        app.close()
