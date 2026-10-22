"""Простые тесты для бэкенда.

Запуск:
    python -m unittest backend.tests.test_health -v
"""
import unittest

from fastapi.testclient import TestClient

from app.main import app


class TestDocsHealth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_docs_returns_200(self):
        resp = self.client.get("/docs")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
