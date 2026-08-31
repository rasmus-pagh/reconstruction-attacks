import importlib
import os
from pathlib import Path
import tempfile
import unittest


class QueryServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = cls.temp_dir.name
        cls.server = importlib.import_module("linear_query_server")
        cls.client = cls.server.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def post_query(self, query, challenge_id="test123", submit=False):
        return self.client.post(
            "/query",
            data={
                "challengeid": challenge_id,
                "query": query,
                "submit": str(submit),
            },
        )

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_classroom_sized_query(self):
        payload = str([[1, -1] * 128] * 512)

        response = self.post_query(payload, challenge_id="classroom")

        self.assertEqual(response.status_code, 200)
        self.assertIn("result", response.get_json())

    def test_query_is_stable_across_reload(self):
        payload = "[[1, -1, 1, -1]]"
        first = self.post_query(payload).get_json()["result"]

        self.server = importlib.reload(self.server)
        self.client = self.server.app.test_client()
        second = self.post_query(payload).get_json()["result"]

        self.assertEqual(first, second)

    def test_query_rejects_code(self):
        marker = Path(self.temp_dir.name) / "executed"
        payload = f"__import__('pathlib').Path({str(marker)!r}).touch()"

        response = self.post_query(payload)

        self.assertIn("JSON array", response.get_json()["error"])
        self.assertFalse(marker.exists())

    def test_secret_distribution(self):
        secret = self.server.secrets("distribution", 30_000)

        plus_one_fraction = (secret == 1).mean()
        self.assertAlmostEqual(plus_one_fraction, 2 / 3, delta=0.02)

    def test_leaderboard_uses_persistent_log(self):
        self.post_query("[[1, -1, 1, -1]]", challenge_id="student1")
        self.post_query("[[1, -1, 1, -1]]", challenge_id="student1", submit=True)

        response = self.client.get("/leaderboard/?n=4")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"student1", response.data)


if __name__ == "__main__":
    unittest.main()
