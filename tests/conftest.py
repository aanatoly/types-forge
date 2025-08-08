import pytest
from type_app import DynamicTypeApp
from webtest import TestApp


@pytest.fixture(scope="function")
def app():
    """Create a fresh DynamicTypeApp instance with in-memory database for each test."""
    app = DynamicTypeApp(database=":memory:", test_mode=True)
    yield app
    app.close()


@pytest.fixture(scope="function")
def test_client(app):
    """Provide a WebTest client for unit tests."""
    return TestApp(app)
