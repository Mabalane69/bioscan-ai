"""HTTP integration tests for account and family-directory workflows."""

from http.server import ThreadingHTTPServer
import json
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from database import UserStore
from server import BioScanHandler


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_store = BioScanHandler.store
        BioScanHandler.store = UserStore(str(Path(self.temp_dir.name) / "api.sqlite3"))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), BioScanHandler)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        BioScanHandler.store = self.previous_store
        self.temp_dir.cleanup()

    def call_api(self, path, method="GET", body=None, token=None):
        headers = {}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=5) as response:
                content = response.read()
                if path.startswith("/api/"):
                    return response.status, json.loads(content.decode("utf-8"))
                return response.status, content
        except HTTPError as error:
            with error:
                return error.code, json.loads(error.read().decode("utf-8"))

    def test_registration_search_contact_order_and_sign_out(self):
        status, page = self.call_api("/")
        self.assertEqual(status, 200)
        self.assertIn("Add close family", page.decode("utf-8"))
        self.assertNotIn("Sample Faces", page.decode("utf-8"))

        status, error = self.call_api("/api/contacts")
        self.assertEqual(status, 401)
        self.assertIn("sign in", error["error"].lower())

        status, owner = self.call_api(
            "/api/register",
            "POST",
            {
                "full_name": "Alex Owner",
                "email": "alex@example.com",
                "phone": "+1 555 0130",
                "password": "owner strong password",
                "discoverable": True,
            },
        )
        self.assertEqual(status, 201)

        status, person = self.call_api(
            "/api/register",
            "POST",
            {
                "full_name": "Jamie Family",
                "email": "jamie@example.com",
                "phone": "+1 555 0131",
                "password": "family strong password",
                "discoverable": True,
            },
        )
        self.assertEqual(status, 201)

        status, second_person = self.call_api(
            "/api/register",
            "POST",
            {
                "full_name": "Morgan Family",
                "email": "morgan@example.com",
                "phone": "+1 555 0132",
                "password": "another family password",
                "discoverable": True,
            },
        )
        self.assertEqual(status, 201)

        status, matches = self.call_api(
            "/api/people?q=Jamie", token=owner["token"]
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(matches["people"]), 1)
        self.assertNotIn("phone", matches["people"][0])

        status, added = self.call_api(
            "/api/contacts",
            "POST",
            {"person_id": person["user"]["id"], "relationship": "Younger sister"},
            owner["token"],
        )
        self.assertEqual(status, 201)
        self.assertEqual(added["contact"]["phone"], "+1 555 0131")
        self.assertEqual(added["contact"]["priority"], 1)

        status, second_contact = self.call_api(
            "/api/contacts",
            "POST",
            {
                "person_id": second_person["user"]["id"],
                "relationship": "Cousin",
            },
            owner["token"],
        )
        self.assertEqual(status, 201)
        status, reordered = self.call_api(
            "/api/contacts/order",
            "PUT",
            {
                "contact_ids": [
                    second_contact["contact"]["id"],
                    added["contact"]["id"],
                ]
            },
            owner["token"],
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            [c["id"] for c in reordered["contacts"]],
            [second_contact["contact"]["id"], added["contact"]["id"]],
        )

        status, contacts = self.call_api("/api/contacts", token=owner["token"])
        self.assertEqual(status, 200)
        self.assertEqual(
            [c["id"] for c in contacts["contacts"]],
            [second_contact["contact"]["id"], added["contact"]["id"]],
        )

        status, _ = self.call_api(
            "/api/logout", "POST", {}, owner["token"]
        )
        self.assertEqual(status, 200)
        status, _ = self.call_api("/api/contacts", token=owner["token"])
        self.assertEqual(status, 401)

    def test_registration_validation_and_login(self):
        status, error = self.call_api(
            "/api/register",
            "POST",
            {
                "full_name": "Taylor",
                "email": "bad",
                "password": "short",
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("email", error["error"].lower())

        self.call_api(
            "/api/register",
            "POST",
            {
                "full_name": "Taylor Example",
                "email": "taylor@example.com",
                "password": "taylor strong password",
                "discoverable": False,
            },
        )
        status, session = self.call_api(
            "/api/login",
            "POST",
            {"email": "taylor@example.com", "password": "taylor strong password"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(session["user"]["email"], "taylor@example.com")
        status, results = self.call_api(
            "/api/people?q=Tay", token=session["token"]
        )
        self.assertEqual(status, 200)
        self.assertEqual(results["people"], [])

    def register(self, name, email, discoverable=True):
        status, response = self.call_api(
            "/api/register",
            "POST",
            {
                "full_name": name,
                "email": email,
                "password": "valid secure password",
                "discoverable": discoverable,
            },
        )
        self.assertEqual(status, 201)
        return response

    def test_face_match_needs_enrollment_consent_and_mutual_follow(self):
        scanner = self.register("Alex Scanner", "scanner@example.com")
        member = self.register(
            "Jamie Member", "member@example.com", discoverable=False
        )
        embedding = struct.pack("<128f", *([1.0] * 128))
        template_body = {
            "image": "data:image/jpeg;base64,ZmFrZQ==",
            "consent": False,
        }
        status, error = self.call_api(
            "/api/face-template",
            "POST",
            template_body,
            member["token"],
        )
        self.assertEqual(status, 400)
        self.assertIn("consent", error["error"].lower())
        self.assertFalse(
            BioScanHandler.store.get_user(member["user"]["id"])["face_search_enabled"]
        )

        with patch("server.face_engine.extract_embedding", return_value=embedding):
            status, enrolled = self.call_api(
                "/api/face-template",
                "POST",
                {**template_body, "consent": True},
                member["token"],
            )
            self.assertEqual(status, 200)
            self.assertTrue(enrolled["user"]["face_search_enabled"])

            status, found = self.call_api(
                "/api/face-match",
                "POST",
                {"image": template_body["image"]},
                scanner["token"],
            )
            self.assertEqual(status, 200)
            self.assertEqual(found["match"]["id"], member["user"]["id"])
            self.assertEqual(found["match"]["full_name"], "Jamie Member")
            self.assertNotIn("email", found["match"])
            self.assertEqual(found["match"]["follow_status"], "none")

            status, denied = self.call_api(
                f"/api/profiles/{member['user']['id']}", token=scanner["token"]
            )
            self.assertEqual(status, 403)
            self.assertIn("follow invitation", denied["error"])

        BioScanHandler.store.add_contact(
            member["user"]["id"], scanner["user"]["id"], "Older sibling"
        )
        status, request_result = self.call_api(
            "/api/follow-requests",
            "POST",
            {"target_id": member["user"]["id"]},
            scanner["token"],
        )
        self.assertEqual(status, 201)
        self.assertEqual(request_result["request"]["status"], "pending")

        status, invitations = self.call_api(
            "/api/follow-requests", token=member["token"]
        )
        self.assertEqual(status, 200)
        invitation = invitations["incoming"][0]
        self.assertEqual(invitation["full_name"], "Alex Scanner")
        status, _ = self.call_api(
            f"/api/follow-requests/{invitation['id']}/accept",
            "POST",
            {},
            member["token"],
        )
        self.assertEqual(status, 200)

        status, profile = self.call_api(
            f"/api/profiles/{member['user']['id']}", token=scanner["token"]
        )
        self.assertEqual(status, 200)
        self.assertEqual(profile["profile"]["email"], "member@example.com")
        self.assertEqual(profile["related_people"][0]["full_name"], "Alex Scanner")
        self.assertEqual(profile["related_people"][0]["relationship"], "Older sibling")

        status, connections = self.call_api(
            "/api/follow-requests", token=member["token"]
        )
        self.assertEqual(status, 200)
        self.assertEqual(connections["connections"][0]["full_name"], "Alex Scanner")

        status, removed = self.call_api(
            "/api/face-template",
            "DELETE",
            token=member["token"],
        )
        self.assertEqual(status, 200)
        self.assertFalse(removed["user"]["face_search_enabled"])
        self.assertEqual(BioScanHandler.store.face_templates(), [])


if __name__ == "__main__":
    unittest.main()
