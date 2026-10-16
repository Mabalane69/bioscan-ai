# BioScan Face Match, Family & Emergency Contacts

BioScan lets members explicitly enroll a face-recognition template, scan a face to find a consenting registered member, and request a mutual follow before either person can see the other's full profile and discoverable family links. It also supports member search, relationship descriptions, and a ranked emergency-contact list. Profiles and contacts are stored in SQLite; there are no generated identities, sample users, or seeded family records.

## Run locally

Requires Python 3.9 or newer.

```powershell
python -m pip install -r requirements.txt
python server.py
```

Open <http://localhost:5050>. Accounts, face templates, and contact lists are saved in `bioscan.sqlite3` next to `server.py`. The first face enrollment or scan downloads about 37 MB of pinned, checksum-verified YuNet and SFace ONNX models from the OpenCV Zoo GitHub repository into the ignored `models/` folder. Face images are processed locally by the app server and discarded; only the 128-value face template is retained for opted-in members. Images are not sent to a face-recognition provider. Set `BIOSCAN_DATABASE` to use another database path, `BIOSCAN_MODEL_DIR` to choose a model cache folder, `PORT` to choose another port, or `HOST` to choose the bind address. The default host is `127.0.0.1`.

## Account and directory behavior

- Register with your name, email, and a password of at least 10 characters. A phone number is optional.
- Discovery is opt-in. People who enable it can be found by signed-in users by name or email. Turn it off from your profile at any time.
- Face matching is a separate, explicit opt-in. Members choose an image for enrollment and can delete their stored template and withdraw consent at any time. Only opted-in enrolled profiles are searched. Enrollment and scan images must contain exactly one face.
- A match shows the member's name and similarity score, not contact details. Signed-in members may request to follow matched people. Accepting an invitation establishes a mutual follow; only mutual follows can view each other's full profile and discoverable related people. Pending invitations can be accepted or rejected.
- Search results show names and email addresses. Phone numbers are returned only for profiles in the signed-in user's emergency-contact list.
- Add a registered person with a description such as “older sister” or “maternal uncle”. Each person's emergency list is private and ordered independently.
- Move contacts up and down to set priority. The first contact is priority 1.
- BioScan stores the list for reference; it does not place calls, alert contacts, or contact emergency services.

## API

Authenticated requests use `Authorization: Bearer <token>`. Registration and login return a token; the browser keeps it in session storage.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/register` | Create a profile and sign in |
| `POST` | `/api/login` | Sign in |
| `POST` | `/api/logout` | Revoke the current session |
| `GET` | `/api/me` | Read the signed-in profile |
| `PATCH` | `/api/me` | Update name, phone, and discovery setting |
| `GET` | `/api/people?q=...` | Search discoverable registered profiles |
| `POST` | `/api/face-template` | Enroll/update a face with explicit consent |
| `DELETE` | `/api/face-template` | Delete the face template and withdraw face-search consent |
| `POST` | `/api/face-match` | Match one face against enrolled, opted-in members |
| `GET` | `/api/follow-requests` | List pending invitations and mutual follows |
| `POST` | `/api/follow-requests` | Invite a matched member to follow |
| `POST` | `/api/follow-requests/{id}/accept` | Accept an invitation and establish a mutual follow |
| `POST` | `/api/follow-requests/{id}/reject` | Reject an invitation |
| `GET` | `/api/profiles/{id}` | View full profile/related people after mutual follow |
| `GET` | `/api/contacts` | List this user's ordered emergency contacts |
| `POST` | `/api/contacts` | Add a registered profile and relationship description |
| `PUT` | `/api/contacts/order` | Set the complete contact order |
| `DELETE` | `/api/contacts/{id}` | Remove a contact |

## Tests

```powershell
python -m unittest test_server test_api
```

The API tests use a temporary SQLite database and an ephemeral local HTTP server; they do not modify the app's database.

## Deployment and privacy

This is a local-development app, not yet a public production service. Face templates are sensitive biometric data and are currently stored in the SQLite database without application-level encryption. Before hosting it for real users, add encryption at rest and key management, HTTPS, email verification, password reset, login and scan throttling, audit/retention controls, database backups, and a reviewed consent/data-protection policy. Do not expose the development HTTP server directly to the public internet. Face matching can make false matches or miss matches; verify a person's identity before acting on a result. Never rely on the app to contact emergency services.

Face model licenses: [OpenCV Zoo YuNet](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet) and [OpenCV Zoo SFace (Apache-2.0)](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_recognition_sface).
