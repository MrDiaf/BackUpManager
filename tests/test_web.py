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

    FORM = {"name": "t", "source": "/a", "dest": "/b", "mode": "mirror", "keep_daily": "7",
            "keep_weekly": "4", "run_time": "03:00", "enabled": "1", "action": "check"}

    def test_form_check_shows_result_and_saves_nothing(self):
        with mock.patch.object(web, "validate", lambda v: v), \
             mock.patch.object(web, "check_job", lambda job, log: (5, "Check OK. Would copy 1 file(s).")):
            r = self.client.post("/jobs/new", data=self.FORM, headers=basic("s3cret"))
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Check OK. Would copy 1 file(s).", r.data)
        self.assertEqual(db.jobs(), [])

    def test_form_check_failure_is_shown(self):
        def refuse(job, log):
            raise web.RunRefused("Destination drive is not mounted")
        with mock.patch.object(web, "validate", lambda v: v), mock.patch.object(web, "check_job", refuse):
            r = self.client.post("/jobs/new", data=self.FORM, headers=basic("s3cret"))
        self.assertIn(b"Check failed", r.data)
        self.assertIn(b"Destination drive is not mounted", r.data)
        self.assertEqual(db.jobs(), [])


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
