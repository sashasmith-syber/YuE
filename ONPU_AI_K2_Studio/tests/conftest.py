# Pytest configuration. Enables pytest-asyncio for async tests.
import pytest

pytest_plugins = ("pytest_asyncio",)


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as async (pytest-asyncio)")
