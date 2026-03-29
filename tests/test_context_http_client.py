from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from clients.context_http import ContextHttpClient, FileUpdateRequest
from server.context_server import create_app


class ContextHttpClientTests(unittest.TestCase):
    def test_client_round_trip_against_server(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "app").mkdir()
            (root / "app" / "main.py").write_text(
                "def cli() -> None:\n"
                "    helper()\n\n"
                "def helper() -> None:\n"
                "    return None\n",
                encoding="utf-8",
            )

            app = create_app(root)
            with TestClient(app) as test_client:
                client = ContextHttpClient(base_url="http://testserver")
                client._get_json = lambda path, params=None: test_client.get(path, params=params).json()
                client._post_json = lambda path, json: test_client.post(path, json=json).json()

                health = client.health()
                self.assertEqual(health["status"], "ok")

                symbols = client.symbols_in_file("app/main.py")
                self.assertEqual([item.symbol for item in symbols], ["app.main.cli", "app.main.helper"])

                update = FileUpdateRequest(
                    path="app/main.py",
                    before="def cli() -> None:\n    helper()\n\n"
                    "def helper() -> None:\n    return None\n",
                    after="def cli(flag: bool) -> None:\n    helper()\n\n"
                    "def helper() -> None:\n    return None\n",
                )
                result = client.apply_file_updates([update])
                self.assertIn("app.main.cli", result["changed_symbols"])
                self.assertEqual(result["edits"][0]["kind"], "contract")

                reset = client.reset()
                self.assertEqual(reset["status"], "ok")


if __name__ == "__main__":
    unittest.main()
