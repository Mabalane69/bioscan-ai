"""Unit tests for persisted accounts and emergency contact ordering."""

import tempfile
import unittest
from pathlib import Path

from database import ProfileAccessDenied, UserStore


class UserStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = UserStore(str(Path(self.temp_dir.name) / "test.sqlite3"))
        self.alice = self.store.register(
            "Alice Example", "ALICE@example.com", "correct horse battery", "+1 555 0100", True
        )
        self.bob = self.store.register(
            "Bob Example", "bob@example.com", "another strong password", "+1 555 0101", True
        )
        self.cara = self.store.register(
            "Cara Example", "cara@example.com", "third secure password", "+1 555 0102", True
        )
        self.hidden = self.store.register(
            "Hidden Example", "hidden@example.com", "fourth secure password", "", False
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_passwords_are_not_stored_as_plaintext_and_login_works(self):
        self.assertNotEqual(self.alice["token"], "correct horse battery")
        signed_in = self.store.login("alice@example.com", "correct horse battery")
        self.assertEqual(signed_in["user"]["id"], self.alice["user"]["id"])
        self.assertIsNotNone(self.store.user_for_token(signed_in["token"]))
        with self.assertRaises(PermissionError):
            self.store.login("alice@example.com", "wrong password")

    def test_search_respects_discovery_and_does_not_expose_phone(self):
        matches = self.store.search_people(self.alice["user"]["id"], "bob")
        self.assertEqual([person["id"] for person in matches], [self.bob["user"]["id"]])
        self.assertNotIn("phone", matches[0])
        self.assertEqual(
            self.store.search_people(self.alice["user"]["id"], "hidden"), []
        )
        self.assertEqual(
            self.store.search_people(self.alice["user"]["id"], "%"), []
        )

    def test_contacts_are_private_ranked_and_reordered(self):
        owner_id = self.alice["user"]["id"]
        first = self.store.add_contact(owner_id, self.bob["user"]["id"], "Older brother")
        second = self.store.add_contact(owner_id, self.cara["user"]["id"], "Close friend")
        self.assertEqual(first["priority"], 1)
        self.assertEqual(first["phone"], "+1 555 0101")
        with self.assertRaises(ValueError):
            self.store.add_contact(owner_id, self.bob["user"]["id"], "Brother")
        with self.assertRaises(LookupError):
            self.store.add_contact(owner_id, self.hidden["user"]["id"], "Cousin")
        with self.assertRaises(LookupError):
            self.store._contact_by_id(self.bob["user"]["id"], first["id"])

        reordered = self.store.order_contacts(owner_id, [second["id"], first["id"]])
        self.assertEqual([contact["id"] for contact in reordered], [second["id"], first["id"]])
        self.assertEqual([contact["priority"] for contact in reordered], [1, 2])
        with self.assertRaises(ValueError):
            self.store.order_contacts(owner_id, [second["id"]])

        self.store.remove_contact(owner_id, second["id"])
        remaining = self.store.list_contacts(owner_id)
        self.assertEqual([contact["id"] for contact in remaining], [first["id"]])
        self.assertEqual(remaining[0]["priority"], 1)

    def test_profile_update_changes_directory_visibility(self):
        profile = self.store.update_profile(
            self.bob["user"]["id"], "Robert Example", "+1 555 0199", False
        )
        self.assertEqual(profile["full_name"], "Robert Example")
        self.assertEqual(profile["phone"], "+1 555 0199")
        self.assertEqual(
            self.store.search_people(self.alice["user"]["id"], "Robert"), []
        )

    def test_rejects_invalid_registration_and_self_contact(self):
        with self.assertRaises(ValueError):
            self.store.register("Short", "alice@example.com", "valid password 123", "", True)
        with self.assertRaises(ValueError):
            self.store.add_contact(
                self.alice["user"]["id"], self.alice["user"]["id"], "Myself"
            )

    def test_follow_requires_acceptance_and_rejection_keeps_profile_private(self):
        alice_id = self.alice["user"]["id"]
        bob_id = self.bob["user"]["id"]
        invitation = self.store.request_follow(alice_id, bob_id)
        self.assertEqual(invitation["status"], "pending")
        with self.assertRaises(ProfileAccessDenied):
            self.store.get_followed_profile(alice_id, bob_id)

        self.assertEqual(
            self.store.respond_to_follow_request(bob_id, invitation["id"], False)[
                "status"
            ],
            "rejected",
        )
        self.assertEqual(self.store.follow_status(alice_id, bob_id), "rejected")
        with self.assertRaises(ProfileAccessDenied):
            self.store.get_followed_profile(alice_id, bob_id)

        invitation = self.store.request_follow(alice_id, bob_id)
        self.store.respond_to_follow_request(bob_id, invitation["id"], True)
        self.assertEqual(self.store.follow_status(alice_id, bob_id), "accepted")
        self.assertEqual(self.store.follow_status(bob_id, alice_id), "accepted")


if __name__ == "__main__":
    unittest.main()
