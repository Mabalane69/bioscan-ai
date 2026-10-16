"""SQLite-backed accounts, discoverable profiles, and emergency contacts."""

from contextlib import closing
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid

SESSION_SECONDS = 60 * 60 * 24 * 30
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ProfileAccessDenied(Exception):
    """Raised when a non-mutual follower requests private profile information."""


class UserStore:
    def __init__(self, database_path):
        self.database_path = database_path
        self.initialize()

    def connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self):
        with closing(self.connect()) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    phone TEXT NOT NULL DEFAULT '',
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    discoverable INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contacts (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    person_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    relationship TEXT NOT NULL,
                    priority INTEGER NOT NULL CHECK (priority > 0),
                    created_at INTEGER NOT NULL,
                    UNIQUE (owner_id, person_id),
                    UNIQUE (owner_id, priority),
                    CHECK (owner_id != person_id)
                );
                CREATE INDEX IF NOT EXISTS contacts_by_owner
                    ON contacts(owner_id, priority);
                CREATE INDEX IF NOT EXISTS sessions_by_expiry
                    ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS face_templates (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    embedding BLOB NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS follow_requests (
                    id TEXT PRIMARY KEY,
                    requester_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    target_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'rejected')),
                    created_at INTEGER NOT NULL,
                    responded_at INTEGER,
                    UNIQUE (requester_id, target_id),
                    CHECK (requester_id != target_id)
                );
                CREATE INDEX IF NOT EXISTS follow_requests_by_target
                    ON follow_requests(target_id, status);
                """
            )
            user_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(users)")
            }
            if "face_search_enabled" not in user_columns:
                db.execute(
                    "ALTER TABLE users ADD COLUMN face_search_enabled INTEGER NOT NULL DEFAULT 0"
                )
            db.commit()

    @staticmethod
    def _validate_name(full_name):
        if not isinstance(full_name, str):
            raise ValueError("Enter your full name.")
        full_name = " ".join(full_name.split())
        if not 2 <= len(full_name) <= 100:
            raise ValueError("Full name must be between 2 and 100 characters.")
        return full_name

    @staticmethod
    def _validate_phone(phone):
        if not isinstance(phone, str) or len(phone.strip()) > 40:
            raise ValueError("Phone number must be 40 characters or fewer.")
        return phone.strip()

    @staticmethod
    def _validate_email(email):
        if not isinstance(email, str):
            raise ValueError("Enter a valid email address.")
        email = email.strip().casefold()
        if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        return email

    @staticmethod
    def _public_profile(row):
        return {
            "id": row["id"],
            "full_name": row["full_name"],
            "email": row["email"],
            "phone": row["phone"],
            "discoverable": bool(row["discoverable"]),
            "face_search_enabled": bool(row["face_search_enabled"]),
        }

    @staticmethod
    def _new_session(db, user_id):
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        db.execute(
            "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, int(time.time()) + SESSION_SECONDS),
        )
        return token

    def register(self, full_name, email, password, phone="", discoverable=False):
        full_name = self._validate_name(full_name)
        email = self._validate_email(email)
        phone = self._validate_phone(phone)
        if not isinstance(password, str) or not 10 <= len(password) <= 256:
            raise ValueError("Password must be between 10 and 256 characters.")
        if not isinstance(discoverable, bool):
            raise ValueError("Choose whether other signed-in people can find you.")

        user_id = str(uuid.uuid4())
        salt = secrets.token_bytes(16)
        password_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, 310_000
        )
        try:
            with closing(self.connect()) as db:
                db.execute(
                    """
                    INSERT INTO users
                        (id, full_name, email, phone, password_salt,
                         password_hash, discoverable, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        full_name,
                        email,
                        phone,
                        salt,
                        password_hash,
                        int(discoverable),
                        int(time.time()),
                    ),
                )
                token = self._new_session(db, user_id)
                db.commit()
        except sqlite3.IntegrityError as error:
            if "users.email" in str(error).lower():
                raise ValueError("An account with that email already exists.") from None
            raise
        return {"token": token, "user": self.get_user(user_id)}

    def login(self, email, password):
        email = self._validate_email(email)
        if not isinstance(password, str) or not password:
            raise PermissionError("Email or password is incorrect.")
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if row is None:
                raise PermissionError("Email or password is incorrect.")
            candidate = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), row["password_salt"], 310_000
            )
            if not hmac.compare_digest(candidate, row["password_hash"]):
                raise PermissionError("Email or password is incorrect.")
            token = self._new_session(db, row["id"])
            db.commit()
            return {"token": token, "user": self._public_profile(row)}

    def user_for_token(self, token):
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with closing(self.connect()) as db:
            row = db.execute(
                """
                SELECT u.id FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ?
                """,
                (token_hash, int(time.time())),
            ).fetchone()
        return {"id": row["id"]} if row else None

    def logout(self, token):
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with closing(self.connect()) as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            db.commit()

    def get_user(self, user_id):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise LookupError("Account not found.")
        return self._public_profile(row)

    def update_profile(self, user_id, full_name, phone="", discoverable=None):
        full_name = self._validate_name(full_name)
        phone = self._validate_phone(phone)
        if not isinstance(discoverable, bool):
            raise ValueError("Choose whether other signed-in people can find you.")
        with closing(self.connect()) as db:
            db.execute(
                "UPDATE users SET full_name = ?, phone = ?, discoverable = ? WHERE id = ?",
                (full_name, phone, int(discoverable), user_id),
            )
            db.commit()
        return self.get_user(user_id)

    def set_face_template(self, user_id, embedding):
        if not isinstance(embedding, bytes) or len(embedding) != 512:
            raise ValueError("The face template has an invalid format.")
        with closing(self.connect()) as db:
            db.execute(
                """
                INSERT INTO face_templates(user_id, embedding, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    embedding = excluded.embedding,
                    created_at = excluded.created_at
                """,
                (user_id, sqlite3.Binary(embedding), int(time.time())),
            )
            db.execute(
                "UPDATE users SET face_search_enabled = 1 WHERE id = ?",
                (user_id,),
            )
            db.commit()
        return self.get_user(user_id)

    def remove_face_template(self, user_id):
        with closing(self.connect()) as db:
            db.execute("DELETE FROM face_templates WHERE user_id = ?", (user_id,))
            db.execute(
                "UPDATE users SET face_search_enabled = 0 WHERE id = ?",
                (user_id,),
            )
            db.commit()
        return self.get_user(user_id)

    def face_templates(self, exclude_user_id=None):
        with closing(self.connect()) as db:
            if exclude_user_id:
                rows = db.execute(
                    """
                    SELECT f.user_id, f.embedding
                    FROM face_templates f JOIN users u ON u.id = f.user_id
                    WHERE u.face_search_enabled = 1 AND f.user_id != ?
                    """,
                    (exclude_user_id,),
                ).fetchall()
            else:
                rows = db.execute(
                    """
                    SELECT f.user_id, f.embedding
                    FROM face_templates f JOIN users u ON u.id = f.user_id
                    WHERE u.face_search_enabled = 1
                    """
                ).fetchall()
        return [(row["user_id"], bytes(row["embedding"])) for row in rows]

    def match_result(self, viewer_id, matched_user_id, similarity):
        user = self.get_user(matched_user_id)
        if not user["face_search_enabled"]:
            raise LookupError("That person has withdrawn face-search consent.")
        if matched_user_id == viewer_id:
            return {
                "match": {
                    "id": user["id"],
                    "full_name": user["full_name"],
                    "similarity": round(float(similarity), 4),
                    "is_self": True,
                    "follow_status": "self",
                }
            }
        follow_status = self.follow_status(viewer_id, matched_user_id)
        return {
            "match": {
                "id": user["id"],
                "full_name": user["full_name"],
                "similarity": round(float(similarity), 4),
                "is_self": False,
                "follow_status": follow_status,
            }
        }

    def follow_status(self, first_user_id, second_user_id):
        with closing(self.connect()) as db:
            row = db.execute(
                """
                SELECT status FROM follow_requests
                WHERE (requester_id = ? AND target_id = ?)
                   OR (requester_id = ? AND target_id = ?)
                ORDER BY CASE status
                    WHEN 'accepted' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END
                LIMIT 1
                """,
                (first_user_id, second_user_id, second_user_id, first_user_id),
            ).fetchone()
        return row["status"] if row else "none"

    def request_follow(self, requester_id, target_id):
        if not isinstance(target_id, str) or not target_id:
            raise ValueError("Choose a registered profile.")
        if requester_id == target_id:
            raise ValueError("You cannot follow your own profile.")
        with closing(self.connect()) as db:
            target = db.execute(
                """
                SELECT id FROM users
                WHERE id = ? AND (discoverable = 1 OR face_search_enabled = 1)
                """,
                (target_id,),
            ).fetchone()
            if target is None:
                raise LookupError("That profile is not available.")
            accepted = db.execute(
                """
                SELECT id FROM follow_requests
                WHERE status = 'accepted'
                  AND ((requester_id = ? AND target_id = ?)
                       OR (requester_id = ? AND target_id = ?))
                """,
                (requester_id, target_id, target_id, requester_id),
            ).fetchone()
            if accepted:
                return {"id": accepted["id"], "status": "accepted"}
            inverse_pending = db.execute(
                """
                SELECT id FROM follow_requests
                WHERE requester_id = ? AND target_id = ? AND status = 'pending'
                """,
                (target_id, requester_id),
            ).fetchone()
            if inverse_pending:
                return {"id": inverse_pending["id"], "status": "pending"}
            row = db.execute(
                """
                SELECT id, status FROM follow_requests
                WHERE requester_id = ? AND target_id = ?
                """,
                (requester_id, target_id),
            ).fetchone()
            if row and row["status"] == "pending":
                raise ValueError("Your invitation is already waiting for a response.")
            if row and row["status"] == "accepted":
                return {"id": row["id"], "status": "accepted"}
            if row:
                request_id = row["id"]
                db.execute(
                    """
                    UPDATE follow_requests
                    SET status = 'pending', created_at = ?, responded_at = NULL
                    WHERE id = ?
                    """,
                    (int(time.time()), request_id),
                )
            else:
                request_id = str(uuid.uuid4())
                db.execute(
                    """
                    INSERT INTO follow_requests
                        (id, requester_id, target_id, status, created_at)
                    VALUES (?, ?, ?, 'pending', ?)
                    """,
                    (request_id, requester_id, target_id, int(time.time())),
                )
            db.commit()
        return {"id": request_id, "status": "pending"}

    def respond_to_follow_request(self, target_id, request_id, accept):
        if not isinstance(accept, bool):
            raise ValueError("Choose whether to accept or reject the invitation.")
        with closing(self.connect()) as db:
            row = db.execute(
                """
                SELECT id, status FROM follow_requests
                WHERE id = ? AND target_id = ?
                """,
                (request_id, target_id),
            ).fetchone()
            if row is None:
                raise LookupError("Invitation not found.")
            if row["status"] != "pending":
                raise ValueError("This invitation has already been answered.")
            status = "accepted" if accept else "rejected"
            db.execute(
                """
                UPDATE follow_requests SET status = ?, responded_at = ?
                WHERE id = ?
                """,
                (status, int(time.time()), request_id),
            )
            db.commit()
        return {"id": request_id, "status": status}

    def list_follow_requests(self, user_id):
        with closing(self.connect()) as db:
            incoming = db.execute(
                """
                SELECT r.id, r.status, r.created_at,
                       u.id AS person_id, u.full_name
                FROM follow_requests r JOIN users u ON u.id = r.requester_id
                WHERE r.target_id = ? AND r.status = 'pending'
                ORDER BY r.created_at
                """,
                (user_id,),
            ).fetchall()
            outgoing = db.execute(
                """
                SELECT r.id, r.status, r.created_at,
                       u.id AS person_id, u.full_name
                FROM follow_requests r
                JOIN users u ON u.id = r.target_id
                WHERE r.requester_id = ? AND r.status = 'pending'
                ORDER BY r.created_at DESC
                """,
                (user_id,),
            ).fetchall()
            connections = db.execute(
                """
                SELECT r.id,
                       CASE WHEN r.requester_id = ? THEN u.id ELSE other.id END
                           AS person_id,
                       CASE WHEN r.requester_id = ? THEN u.full_name
                            ELSE other.full_name END AS full_name
                FROM follow_requests r
                JOIN users u ON u.id = r.target_id
                JOIN users other ON other.id = r.requester_id
                WHERE r.status = 'accepted'
                  AND (r.requester_id = ? OR r.target_id = ?)
                ORDER BY full_name COLLATE NOCASE
                """,
                (user_id, user_id, user_id, user_id),
            ).fetchall()
        return {
            "incoming": [dict(row) for row in incoming],
            "outgoing": [dict(row) for row in outgoing],
            "connections": [dict(row) for row in connections],
        }

    def get_followed_profile(self, viewer_id, profile_id):
        if viewer_id != profile_id and self.follow_status(viewer_id, profile_id) != "accepted":
            raise ProfileAccessDenied(
                "Accept each other's follow invitation to view this profile."
            )
        with closing(self.connect()) as db:
            profile = db.execute(
                "SELECT id, full_name, email, phone FROM users WHERE id = ?",
                (profile_id,),
            ).fetchone()
            if profile is None:
                raise LookupError("Profile not found.")
            relatives = db.execute(
                """
                SELECT c.relationship, u.id AS person_id, u.full_name
                FROM contacts c JOIN users u ON u.id = c.person_id
                WHERE c.owner_id = ? AND u.discoverable = 1
                ORDER BY c.priority
                """,
                (profile_id,),
            ).fetchall()
        return {
            "profile": dict(profile),
            "related_people": [dict(row) for row in relatives],
        }

    def search_people(self, owner_id, query):
        if not isinstance(query, str):
            raise ValueError("Search text must be text.")
        query = query.strip()
        if len(query) < 2:
            return []
        if len(query) > 100:
            raise ValueError("Search text must be 100 characters or fewer.")
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        with closing(self.connect()) as db:
            rows = db.execute(
                """
                SELECT id, full_name, email FROM users
                WHERE id != ? AND discoverable = 1
                  AND (full_name LIKE ? ESCAPE '\\' COLLATE NOCASE
                       OR email LIKE ? ESCAPE '\\' COLLATE NOCASE)
                ORDER BY full_name COLLATE NOCASE LIMIT 20
                """,
                (owner_id, pattern, pattern),
            ).fetchall()
        return [
            {"id": row["id"], "full_name": row["full_name"], "email": row["email"]}
            for row in rows
        ]

    def add_contact(self, owner_id, person_id, relationship):
        if not isinstance(person_id, str):
            raise ValueError("Choose a registered person to add.")
        if not isinstance(relationship, str):
            raise ValueError("Describe how this person is related to you.")
        relationship = " ".join(relationship.split())
        if not 2 <= len(relationship) <= 120:
            raise ValueError("Relationship description must be between 2 and 120 characters.")
        with closing(self.connect()) as db:
            person = db.execute(
                "SELECT id FROM users WHERE id = ? AND discoverable = 1",
                (person_id,),
            ).fetchone()
            if person is None:
                raise LookupError("That profile is not available to add.")
            if person_id == owner_id:
                raise ValueError("You cannot add your own profile as a contact.")
            existing = db.execute(
                "SELECT 1 FROM contacts WHERE owner_id = ? AND person_id = ?",
                (owner_id, person_id),
            ).fetchone()
            if existing:
                raise ValueError("This person is already in your emergency list.")
            priority = db.execute(
                "SELECT COALESCE(MAX(priority), 0) + 1 FROM contacts WHERE owner_id = ?",
                (owner_id,),
            ).fetchone()[0]
            contact_id = str(uuid.uuid4())
            db.execute(
                """
                INSERT INTO contacts
                    (id, owner_id, person_id, relationship, priority, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (contact_id, owner_id, person_id, relationship, priority, int(time.time())),
            )
            db.commit()
        return self._contact_by_id(owner_id, contact_id)

    def _contact_by_id(self, owner_id, contact_id):
        with closing(self.connect()) as db:
            row = db.execute(
                """
                SELECT c.id, c.relationship, c.priority,
                       u.id AS person_id, u.full_name, u.email, u.phone
                FROM contacts c JOIN users u ON u.id = c.person_id
                WHERE c.owner_id = ? AND c.id = ?
                """,
                (owner_id, contact_id),
            ).fetchone()
        if row is None:
            raise LookupError("Emergency contact not found.")
        return dict(row)

    def list_contacts(self, owner_id):
        with closing(self.connect()) as db:
            rows = db.execute(
                """
                SELECT c.id, c.relationship, c.priority,
                       u.id AS person_id, u.full_name, u.email, u.phone
                FROM contacts c JOIN users u ON u.id = c.person_id
                WHERE c.owner_id = ? ORDER BY c.priority
                """,
                (owner_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def order_contacts(self, owner_id, contact_ids):
        if not isinstance(contact_ids, list) or any(
            not isinstance(contact_id, str) for contact_id in contact_ids
        ):
            raise ValueError("Provide the ordered list of contact IDs.")
        if len(contact_ids) != len(set(contact_ids)):
            raise ValueError("Each emergency contact can appear only once.")
        with closing(self.connect()) as db:
            existing = {
                row["id"]
                for row in db.execute(
                    "SELECT id FROM contacts WHERE owner_id = ?", (owner_id,)
                ).fetchall()
            }
            if set(contact_ids) != existing:
                raise ValueError("The order must include every current contact exactly once.")
            offset = len(existing) + 1
            db.execute(
                "UPDATE contacts SET priority = priority + ? WHERE owner_id = ?",
                (offset, owner_id),
            )
            db.executemany(
                "UPDATE contacts SET priority = ? WHERE owner_id = ? AND id = ?",
                [
                    (priority, owner_id, contact_id)
                    for priority, contact_id in enumerate(contact_ids, start=1)
                ],
            )
            db.commit()
        return self.list_contacts(owner_id)

    def remove_contact(self, owner_id, contact_id):
        with closing(self.connect()) as db:
            cursor = db.execute(
                "DELETE FROM contacts WHERE owner_id = ? AND id = ?",
                (owner_id, contact_id),
            )
            if cursor.rowcount == 0:
                raise LookupError("Emergency contact not found.")
            rows = db.execute(
                "SELECT id FROM contacts WHERE owner_id = ? ORDER BY priority",
                (owner_id,),
            ).fetchall()
            offset = len(rows) + 2
            db.execute(
                "UPDATE contacts SET priority = priority + ? WHERE owner_id = ?",
                (offset, owner_id),
            )
            db.executemany(
                "UPDATE contacts SET priority = ? WHERE owner_id = ? AND id = ?",
                [
                    (priority, owner_id, row["id"])
                    for priority, row in enumerate(rows, start=1)
                ],
            )
            db.commit()
