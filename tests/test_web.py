import base64
import os
import tempfile
import unittest
from unittest import mock

import db
import web


def basic(password):
    return {"Authorization": "Basic " + base64.b64encode(f"any:{password}".encode()).decode()}


class Auth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [mock.patch.object(db, "DB_PATH", os.path.join(self.tmp.name, "t.db")),
                        mock.patch.object(db, "LOG_DIR", os.path.join(self.tmp.name, "logs")),
                        mock.patch.dict(web.app.config, {"PASSWORD": "s3cret"})]
        for p in self.patches:
            p.start()
        db.init()
        self.client = web.app.test_client()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_pages_need_password(self):
        self.assertEqual(self.client.get("/").status_code, 401)
        self.assertEqual(self.client.get("/", headers=basic("wrong")).status_code, 401)
        self.assertEqual(self.client.get("/", headers=basic("s3cret")).status_code, 200)

    def test_health_is_open(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_cross_site_post_refused_even_when_logged_in(self):
        headers = {**basic("s3cret"), "Origin": "http://evil.example"}
        self.assertEqual(self.client.post("/jobs/new", headers=headers).status_code, 403)

    def test_same_origin_post_allowed(self):
        headers = {**basic("s3cret"), "Origin": "http://localhost"}
        self.assertEqual(self.client.post("/jobs/new", headers=headers, data={"name": ""}).status_code, 400)


class PasswordFile(unittest.TestCase):
    def test_generated_once_and_reused(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(web, "PASSWORD_FILE", os.path.join(tmp, "pw")), \
             mock.patch.dict(os.environ, {"UI_PASSWORD": ""}):
            first = web.load_password()
            self.assertGreaterEqual(len(first), 20)
            self.assertEqual(web.load_password(), first)
            self.assertEqual(os.stat(os.path.join(tmp, "pw")).st_mode & 0o777, 0o600)

    def test_env_wins(self):
        with mock.patch.dict(os.environ, {"UI_PASSWORD": "from-env"}):
            self.assertEqual(web.load_password(), "from-env")


if __name__ == "__main__":
    unittest.main()
