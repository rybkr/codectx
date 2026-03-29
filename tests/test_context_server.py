from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from server.context_server import create_app


class ContextServerTests(unittest.TestCase):
    def test_file_update_recomputes_graph_and_returns_impacted_symbols(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app_dir = root / "app"
            app_dir.mkdir()
            (app_dir / "models.py").write_text(
                "class UserStore:\n"
                "    def __init__(self, url: str):\n"
                "        self.url = url\n",
                encoding="utf-8",
            )
            (app_dir / "service.py").write_text(
                "from app.models import UserStore\n\n"
                "def build_store(url: str) -> UserStore:\n"
                "    return UserStore(url)\n",
                encoding="utf-8",
            )

            client = TestClient(create_app(root))

            response = client.post(
                "/updates/files",
                json={
                    "updates": [
                        {
                            "path": "app/models.py",
                            "before": "class UserStore:\n    def __init__(self, url: str):\n        self.url = url\n",
                            "after": "class UserStore:\n    def __init__(self, url: str, timeout: int):\n        self.url = url\n        self.timeout = timeout\n",
                        }
                    ]
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("app.models.UserStore.__init__", payload["changed_symbols"])
            self.assertIn("app.service.build_store", payload["impacted_symbols"])
            self.assertEqual(payload["edits"][0]["kind"], "contract")

            symbol_response = client.get("/symbols/app.models.UserStore.__init__")
            self.assertEqual(symbol_response.status_code, 200)
            self.assertEqual(
                symbol_response.json()["record"]["symbol"],
                "app.models.UserStore.__init__",
            )

    def test_reset_restores_graph_from_disk(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "main.py").write_text(
                "def live_symbol() -> None:\n"
                "    return None\n",
                encoding="utf-8",
            )
            client = TestClient(create_app(root))

            update_response = client.post(
                "/updates/files",
                json={
                    "updates": [
                        {
                            "path": "main.py",
                            "before": "def live_symbol() -> None:\n    return None\n",
                            "after": (
                                "def live_symbol() -> None:\n    return None\n\n"
                                "def synthetic_symbol() -> None:\n    return None\n"
                            ),
                        }
                    ]
                },
            )
            self.assertEqual(update_response.status_code, 200)
            self.assertEqual(client.get("/symbols/main.synthetic_symbol").status_code, 200)

            reset_response = client.post("/reset")
            self.assertEqual(reset_response.status_code, 200)
            self.assertEqual(reset_response.json()["status"], "ok")
            self.assertEqual(client.get("/symbols/main.synthetic_symbol").status_code, 404)
            self.assertEqual(client.get("/symbols/main.live_symbol").status_code, 200)


if __name__ == "__main__":
    unittest.main()
