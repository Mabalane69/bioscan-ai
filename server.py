"""HTTP API and static-file server for the BioScan family emergency registry."""

import json
import base64
import binascii
import mimetypes
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from database import ProfileAccessDenied, UserStore
import face_engine

PORT = int(os.environ.get("PORT", "5050"))
HOST = os.environ.get("HOST", "127.0.0.1")
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT_DIR, "static")
DATABASE_PATH = os.environ.get(
    "BIOSCAN_DATABASE", os.path.join(ROOT_DIR, "bioscan.sqlite3")
)
MAX_BODY_BYTES = 5_500_000


class BioScanHandler(BaseHTTPRequestHandler):
    store = None

    def get_store(self):
        if self.store is None:
            self.store = UserStore(DATABASE_PATH)
        return self.store

    def log_request(self, code="-", size="-"):
        path = urllib.parse.urlparse(self.path).path
        self.log_message(
            '"%s %s" %s %s',
            self.command,
            path,
            str(code),
            str(size),
        )

    def send_json(self, status_code, data):
        response = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(response)

    def read_json(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid Content-Length header.") from None
        if content_length < 0 or content_length > MAX_BODY_BYTES:
            raise ValueError("Request body is too large.")
        try:
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("Invalid JSON in request body.") from None
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")
        return body

    def authenticated_user(self):
        authorization = self.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        return self.get_store().user_for_token(token)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/health":
            self.send_json(200, {"status": "ok"})
            return

        if path.startswith("/api/"):
            user = self.authenticated_user()
            if user is None:
                self.send_json(401, {"error": "Please sign in to continue."})
                return
            if path == "/api/me":
                self.send_json(200, {"user": self.get_store().get_user(user["id"])})
                return
            if path == "/api/contacts":
                self.send_json(
                    200, {"contacts": self.get_store().list_contacts(user["id"])}
                )
                return
            if path == "/api/people":
                query = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query
                ).get("q", [""])[0]
                self.send_json(
                    200, {"people": self.get_store().search_people(user["id"], query)}
                )
                return
            if path == "/api/follow-requests":
                self.send_json(
                    200, self.get_store().list_follow_requests(user["id"])
                )
                return
            if path.startswith("/api/profiles/"):
                profile_id = urllib.parse.unquote(path.rsplit("/", 1)[-1])
                try:
                    profile = self.get_store().get_followed_profile(
                        user["id"], profile_id
                    )
                except ProfileAccessDenied as error:
                    self.send_json(403, {"error": str(error)})
                    return
                self.send_json(200, profile)
                return
            self.send_json(404, {"error": "Endpoint not found."})
            return

        self.serve_static(path)

    def serve_static(self, path):
        rel_path = "index.html" if path in ("", "/") else path.lstrip("/")
        filepath = os.path.realpath(os.path.join(STATIC_DIR, rel_path))
        if os.path.commonpath((os.path.realpath(STATIC_DIR), filepath)) != os.path.realpath(
            STATIC_DIR
        ):
            self.send_error(403, "Forbidden")
            return
        if not os.path.isfile(filepath):
            self.send_error(404, "File Not Found")
            return
        content_type, _ = mimetypes.guess_type(filepath)
        try:
            with open(filepath, "rb") as source:
                content = source.read()
        except OSError:
            self.send_error(500, "Could not read requested file.")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        self.handle_write_request("POST")

    def do_PUT(self):
        self.handle_write_request("PUT")

    def do_PATCH(self):
        self.handle_write_request("PATCH")

    def do_DELETE(self):
        self.handle_write_request("DELETE")

    def handle_write_request(self, method):
        try:
            body = self.read_json() if method != "DELETE" else {}
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return

        path = urllib.parse.urlparse(self.path).path
        try:
            if method == "POST" and path == "/api/register":
                result = self.get_store().register(
                    body.get("full_name"),
                    body.get("email"),
                    body.get("password"),
                    body.get("phone", ""),
                    body.get("discoverable", False),
                )
                self.send_json(201, result)
                return
            if method == "POST" and path == "/api/login":
                self.send_json(
                    200,
                    self.get_store().login(body.get("email"), body.get("password")),
                )
                return

            user = self.authenticated_user()
            if user is None:
                self.send_json(401, {"error": "Please sign in to continue."})
                return
            user_id = user["id"]

            if method == "POST" and path == "/api/logout":
                self.get_store().logout(
                    self.headers.get("Authorization", "").partition(" ")[2]
                )
                self.send_json(200, {"status": "signed_out"})
            elif method == "PATCH" and path == "/api/me":
                profile = self.get_store().update_profile(
                    user_id,
                    body.get("full_name"),
                    body.get("phone", ""),
                    body.get("discoverable"),
                )
                self.send_json(200, {"user": profile})
            elif method == "POST" and path == "/api/contacts":
                contact = self.get_store().add_contact(
                    user_id,
                    body.get("person_id"),
                    body.get("relationship"),
                )
                self.send_json(201, {"contact": contact})
            elif method == "POST" and path == "/api/face-template":
                if body.get("consent") is not True:
                    raise ValueError(
                        "Explicit consent is required before face enrollment."
                    )
                image_bytes = self.decode_face_image(body.get("image"))
                embedding = face_engine.extract_embedding(image_bytes)
                profile = self.get_store().set_face_template(user_id, embedding)
                self.send_json(200, {"user": profile})
            elif method == "DELETE" and path == "/api/face-template":
                profile = self.get_store().remove_face_template(user_id)
                self.send_json(200, {"user": profile})
            elif method == "POST" and path == "/api/face-match":
                image_bytes = self.decode_face_image(body.get("image"))
                embedding = face_engine.extract_embedding(image_bytes)
                match = face_engine.find_best_match(
                    embedding, self.get_store().face_templates()
                )
                if match is None:
                    self.send_json(200, {"match": None})
                    return
                person_id, similarity = match
                self.send_json(
                    200,
                    self.get_store().match_result(
                        user_id, person_id, similarity
                    ),
                )
            elif method == "POST" and path == "/api/follow-requests":
                result = self.get_store().request_follow(
                    user_id, body.get("target_id")
                )
                self.send_json(201, {"request": result})
            elif method == "POST" and path.startswith("/api/follow-requests/"):
                parts = path.strip("/").split("/")
                if len(parts) != 4 or parts[3] not in ("accept", "reject"):
                    self.send_json(404, {"error": "Endpoint not found."})
                    return
                request_id = urllib.parse.unquote(parts[2])
                result = self.get_store().respond_to_follow_request(
                    user_id, request_id, parts[3] == "accept"
                )
                self.send_json(200, {"request": result})
            elif method == "PUT" and path == "/api/contacts/order":
                contacts = self.get_store().order_contacts(
                    user_id, body.get("contact_ids")
                )
                self.send_json(200, {"contacts": contacts})
            elif method == "DELETE" and path.startswith("/api/contacts/"):
                contact_id = urllib.parse.unquote(path.rsplit("/", 1)[-1])
                self.get_store().remove_contact(user_id, contact_id)
                self.send_json(200, {"status": "removed"})
            else:
                self.send_json(404, {"error": "Endpoint not found."})
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except ProfileAccessDenied as error:
            self.send_json(403, {"error": str(error)})
        except PermissionError as error:
            self.send_json(401, {"error": str(error)})
        except LookupError as error:
            self.send_json(404, {"error": str(error)})
        except RuntimeError as error:
            self.send_json(503, {"error": str(error)})
        except Exception:
            self.log_error("Request failed while processing %s %s", method, path)
            self.send_json(500, {"error": "The request could not be completed."})

    @staticmethod
    def decode_face_image(image_data):
        if not isinstance(image_data, str) or not image_data:
            raise ValueError("Select a face image to continue.")
        encoded = image_data
        if image_data.startswith("data:"):
            header, separator, encoded = image_data.partition(",")
            if (
                not separator
                or header not in (
                    "data:image/jpeg;base64",
                    "data:image/png;base64",
                    "data:image/webp;base64",
                )
            ):
                raise ValueError("Use a JPEG, PNG, or WEBP image.")
        if len(encoded) > 5_400_000:
            raise ValueError("Image must be 4 MB or smaller.")
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("The uploaded image is not valid base64 data.") from None
        if not image_bytes or len(image_bytes) > face_engine.MAX_IMAGE_BYTES:
            raise ValueError("Image must be 4 MB or smaller.")
        return image_bytes


def run_server():
    BioScanHandler.store = UserStore(DATABASE_PATH)
    server = ThreadingHTTPServer((HOST, PORT), BioScanHandler)
    print(f"BioScan family emergency registry running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down BioScan...")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
