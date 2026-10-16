"""
server.py - BioScan AI Application Backend Server
Provides REST APIs for:
1. /api/scan - Analyzes face image, extracts biometrics, generates profile dossier and close family network
2. /api/regenerate-family-member - Regenerates an individual family member
3. /api/samples - Lists curated sample portraits for instant testing
4. /api/test-key - Verifies Google Gemini API keys
Serves static web files (SPA frontend, styles, scripts, sample images).
"""

import os
import io
import json
import base64
import mimetypes
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

import ai_engine

PORT = 5050
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

class BioScanHandler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        # Concise logging
        print(f"[{self.log_date_time_string()}] {format % args}")

    def send_json(self, status_code: int, data: dict):
        response_bytes = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/samples":
            samples = [
                {
                    "id": "sample-1",
                    "name": "Elena Vance",
                    "thumbnail": "/samples/sample_1_elena.jpg",
                    "description": "Female, 32 • Emerald Eyes & Chestnut Curls"
                },
                {
                    "id": "sample-2",
                    "name": "Marcus Chen",
                    "thumbnail": "/samples/sample_2_marcus.jpg",
                    "description": "Male, 36 • Dark Eyes & Defined Jawline"
                },
                {
                    "id": "sample-3",
                    "name": "Amari Diallo",
                    "thumbnail": "/samples/sample_3_amari.jpg",
                    "description": "Male, 28 • Warm Cognac Gaze & Athletic Build"
                },
                {
                    "id": "sample-4",
                    "name": "Astrid Lindqvist",
                    "thumbnail": "/samples/sample_4_astrid.jpg",
                    "description": "Female, 30 • Blue Eyes & Nordic Phenotype"
                }
            ]
            self.send_json(200, {"status": "success", "samples": samples})
            return

        # Serve static files
        if path == "/" or path == "":
            filepath = os.path.join(STATIC_DIR, "index.html")
        else:
            rel_path = path.lstrip("/")
            filepath = os.path.join(STATIC_DIR, rel_path)

        # Security check: ensure path is within STATIC_DIR
        real_filepath = os.path.realpath(filepath)
        if not real_filepath.startswith(os.path.realpath(STATIC_DIR)):
            self.send_error(403, "Forbidden")
            return

        if not os.path.exists(real_filepath) or os.path.isdir(real_filepath):
            self.send_error(404, "File Not Found")
            return

        mime_type, _ = mimetypes.guess_type(real_filepath)
        if not mime_type:
            mime_type = "application/octet-stream"

        try:
            with open(real_filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Internal Error: {str(e)}")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            self.send_json(400, {"error": "Invalid JSON in request body"})
            return

        if path == "/api/scan":
            self.handle_scan(body)
        elif path == "/api/regenerate-family-member":
            self.handle_regenerate_member(body)
        elif path == "/api/test-key":
            self.handle_test_key(body)
        else:
            self.send_error(404, "Endpoint Not Found")

    def handle_scan(self, body: dict):
        image_data = body.get("image")
        if not image_data:
            self.send_json(400, {"error": "Missing 'image' parameter (base64 or data URL)"})
            return

        # Decode base64
        try:
            mime_type = "image/jpeg"
            if "," in image_data:
                header, base64_str = image_data.split(",", 1)
                if "image/png" in header:
                    mime_type = "image/png"
                elif "image/webp" in header:
                    mime_type = "image/webp"
            else:
                base64_str = image_data
            
            image_bytes = base64.b64decode(base64_str)
        except Exception as e:
            self.send_json(400, {"error": f"Failed to decode base64 image: {str(e)}"})
            return

        engine_choice = body.get("engine", "auto")
        user_key = body.get("api_key", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()

        # Extract image metrics using Pillow
        try:
            metrics = ai_engine.extract_image_metrics(image_bytes)
        except Exception as e:
            self.send_json(400, {"error": f"Failed to process image geometry: {str(e)}"})
            return

        result = None

        # If Gemini requested or available
        if (engine_choice in ["gemini", "auto"]) and user_key:
            print(f"[*] Attempting analysis with Gemini Vision API...")
            gemini_result = ai_engine.analyze_with_gemini(image_bytes, user_key, mime_type)
            if gemini_result:
                gemini_result["metrics"] = metrics
                result = gemini_result
            else:
                print("[!] Gemini Vision API attempt failed, falling back to Biogenetic Neural Synthesizer")

        # Fallback or default: Offline Biogenetic Neural Synthesizer
        if not result:
            result = ai_engine.generate_biogenetic_profile_offline(metrics)

        self.send_json(200, {
            "status": "success",
            "data": result
        })

    def handle_regenerate_member(self, body: dict):
        member_id = body.get("id", "rel-sibling")
        profile = body.get("profile", {})
        metrics = body.get("metrics", {})
        seed_salt = f"-regen-{member_id}-{os.urandom(4).hex()}"
        
        # Synthesize fresh family members and find matching relation
        fresh_data = ai_engine.generate_biogenetic_profile_offline(metrics, seed_salt=seed_salt)
        matching = [m for m in fresh_data["family"] if m["id"] == member_id or m["relation"].lower() in member_id.lower()]
        
        if matching:
            new_member = matching[0]
            new_member["id"] = member_id
            self.send_json(200, {"status": "success", "member": new_member})
        else:
            self.send_json(200, {"status": "success", "member": fresh_data["family"][0]})

    def handle_test_key(self, body: dict):
        api_key = body.get("api_key", "").strip()
        if not api_key:
            self.send_json(400, {"valid": False, "message": "API Key is empty"})
            return

        # Simple test call
        import urllib.request
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    self.send_json(200, {"valid": True, "message": "Google Gemini API Key is valid and active!"})
                    return
        except Exception as e:
            self.send_json(200, {"valid": False, "message": f"Validation failed: {str(e)}"})


def run_server():
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, BioScanHandler)
    print(f"============================================================")
    print(f"  BioScan AI Server running at http://localhost:{PORT}")
    print(f"  Webcam scanner, AI Profiler & Kinship Synthesizer ready.")
    print(f"============================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down BioScan AI Server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
