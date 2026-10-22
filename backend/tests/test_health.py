"""Простые тесты для бэкенда.

Запуск:
    python -m unittest backend.tests.test_health -v
"""
import os
import sys
import unittest

#project root = 3 уровня выше от тестового файла (чтобы import backend.app не
#зависеть от CWD и не зашёл «хуйня» из соседнего проекта
#work/vpn-telegram-bot, у которого тоже есть app/main.py).
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi.testclient import TestClient

from backend.app.main import app


class TestDocsHealth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_docs_returns_200(self):
        resp = self.client.get("/docs")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
