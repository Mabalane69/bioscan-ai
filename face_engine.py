"""Local YuNet/SFace face detection and recognition."""

import hashlib
import os
from pathlib import Path
import tempfile
import threading
from urllib.request import Request, urlopen

import cv2
import numpy as np

MODEL_COMMIT = "47534e27c9851bb1128ccc0102f1145e27f23f98"
MODEL_FILES = {
    "face_detection_yunet_2023mar.onnx": {
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "size": 232589,
        "path": "face_detection_yunet",
    },
    "face_recognition_sface_2021dec.onnx": {
        "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        "size": 38696353,
        "path": "face_recognition_sface",
    },
}
MATCH_THRESHOLD = 0.363
MAX_IMAGE_BYTES = 4_000_000
_models = None
_models_lock = threading.Lock()


def _model_directory():
    configured = os.environ.get("BIOSCAN_MODEL_DIR")
    return Path(configured) if configured else Path(__file__).resolve().parent / "models"


def _download_model(filename, metadata):
    model_dir = _model_directory() / metadata["path"]
    model_dir.mkdir(parents=True, exist_ok=True)
    destination = model_dir / filename
    if destination.exists():
        if _file_sha256(destination) == metadata["sha256"]:
            return destination
        raise RuntimeError(f"Face model failed checksum verification: {destination}")

    url = (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
        f"{MODEL_COMMIT}/models/{metadata['path']}/{filename}"
    )
    digest = hashlib.sha256()
    total = 0
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=model_dir, prefix=f".{filename}.", delete=False
        ) as target:
            temporary_path = Path(target.name)
            request = Request(url, headers={"User-Agent": "BioScan-local-face-engine"})
            with urlopen(request, timeout=60) as response:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > metadata["size"]:
                        raise RuntimeError(f"Downloaded face model is too large: {filename}")
                    digest.update(chunk)
                    target.write(chunk)
        if total != metadata["size"] or digest.hexdigest() != metadata["sha256"]:
            raise RuntimeError(f"Downloaded face model failed checksum verification: {filename}")
        os.replace(temporary_path, destination)
        return destination
    except Exception as error:
        raise RuntimeError(
            f"Could not download the local face-recognition model {filename}: {error}"
        ) from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_models():
    global _models
    if _models is None:
        detector_path = _download_model(
            "face_detection_yunet_2023mar.onnx",
            MODEL_FILES["face_detection_yunet_2023mar.onnx"],
        )
        recognizer_path = _download_model(
            "face_recognition_sface_2021dec.onnx",
            MODEL_FILES["face_recognition_sface_2021dec.onnx"],
        )
        detector = cv2.FaceDetectorYN.create(
            str(detector_path),
            "",
            (320, 320),
            score_threshold=0.9,
            nms_threshold=0.3,
            top_k=5000,
        )
        recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), "")
        _models = detector, recognizer
    return _models


def extract_embedding(image_bytes):
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ValueError("Upload an image containing exactly one face.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("Image must be 4 MB or smaller.")
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The uploaded file is not a supported image.")
    height, width = image.shape[:2]
    if width * height > 16_000_000:
        raise ValueError("Image dimensions are too large to process.")

    with _models_lock:
        detector, recognizer = _load_models()
        detector.setInputSize((width, height))
        _, faces = detector.detect(image)
        if faces is None or len(faces) == 0:
            raise ValueError("No face was detected. Use a clear, front-facing photo.")
        if len(faces) != 1:
            raise ValueError("The image must contain only one visible face.")
        aligned = recognizer.alignCrop(image, faces[0])
        feature = recognizer.feature(aligned)
    vector = np.asarray(feature, dtype=np.float32).reshape(-1)
    if vector.size != 128 or not np.isfinite(vector).all():
        raise RuntimeError("The face-recognition model returned an invalid template.")
    return vector.tobytes()


def find_best_match(query_embedding, templates):
    query = np.frombuffer(query_embedding, dtype=np.float32)
    if query.size != 128 or not np.isfinite(query).all():
        raise ValueError("The stored face template has an invalid format.")
    query_norm = float(np.linalg.norm(query))
    if query_norm == 0:
        raise ValueError("The scanned face could not be recognized.")

    best_match = None
    best_score = MATCH_THRESHOLD
    for user_id, embedding in templates:
        reference = np.frombuffer(embedding, dtype=np.float32)
        if reference.size != 128 or not np.isfinite(reference).all():
            continue
        reference_norm = float(np.linalg.norm(reference))
        if reference_norm == 0:
            continue
        score = float(np.dot(query, reference) / (query_norm * reference_norm))
        if score > best_score:
            best_match = user_id
            best_score = score
    return (best_match, best_score) if best_match is not None else None
