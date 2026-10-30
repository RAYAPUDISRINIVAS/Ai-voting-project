import base64
import binascii
import re
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError


class FaceServiceError(ValueError):
    pass


def decode_image(image_data):
    if not isinstance(image_data, str):
        raise FaceServiceError("Provide a webcam capture or image upload.")
    match = re.fullmatch(r"data:image/(?:jpeg|jpg|png);base64,([A-Za-z0-9+/=]+)", image_data)
    if not match:
        raise FaceServiceError("Only JPEG and PNG image captures are accepted.")
    try:
        raw = base64.b64decode(match.group(1), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FaceServiceError("The submitted image could not be decoded.") from exc
    if len(raw) > 4 * 1024 * 1024:
        raise FaceServiceError("Image must be 4 MB or smaller.")
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in {"JPEG", "PNG"}:
                raise FaceServiceError("Only JPEG and PNG image captures are accepted.")
            width, height = source.size
            if width < 32 or height < 32 or width * height > 16_000_000:
                raise FaceServiceError("Image dimensions must be at least 32x32 and at most 16 megapixels.")
            return np.asarray(source.convert("RGB"))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise FaceServiceError("The submitted file is not a safe, valid image.") from exc


def encoding_from_image(image):
    try:
        import face_recognition
    except ImportError as exc:
        raise FaceServiceError(
            "Face recognition is unavailable. Install the optional face-recognition "
            "and dlib dependencies, or ask the administrator to configure them."
        ) from exc

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    detector = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    if detector.empty():
        raise FaceServiceError("OpenCV's face detector could not be loaded.")
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
    if len(faces) == 0:
        raise FaceServiceError("No face was detected. Improve lighting and try again.")
    if len(faces) != 1:
        raise FaceServiceError("Exactly one face must be visible.")
    encodings = face_recognition.face_encodings(image, num_jitters=1, model="small")
    if len(encodings) != 1:
        raise FaceServiceError("A clear face could not be encoded. Try another image.")
    return np.asarray(encodings[0], dtype=np.float64)


def encoding_from_capture(image_data):
    return encoding_from_image(decode_image(image_data))


def compare_encodings(registered, live, threshold):
    registered = np.asarray(registered, dtype=np.float64)
    live = np.asarray(live, dtype=np.float64)
    if registered.shape != live.shape or registered.size == 0:
        raise FaceServiceError("Facial profile data is invalid; contact the administrator.")
    distance = float(np.linalg.norm(registered - live))
    return distance <= threshold, distance


def capture_from_webcam():
    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        camera.release()
        raise FaceServiceError("Webcam is unavailable. Use the image-upload option instead.")
    try:
        ok, frame = camera.read()
        if not ok:
            raise FaceServiceError("Could not capture a webcam frame.")
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    finally:
        camera.release()
