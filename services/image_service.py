import os
import re
import secrets
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 4 * 1024 * 1024
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def save_candidate_image(upload, destination):
    if upload is None or not upload.filename:
        return None
    extension = os.path.splitext(upload.filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS or upload.mimetype not in {
        "image/jpeg",
        "image/png",
    }:
        raise ValueError("Candidate images must be JPEG or PNG files.")
    raw = upload.stream.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Candidate images must be 4 MB or smaller.")
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in {"JPEG", "PNG"}:
                raise ValueError("Candidate image must be a JPEG or PNG file.")
            width, height = source.size
            if width < 32 or height < 32 or width * height > 16_000_000:
                raise ValueError("Candidate image dimensions must be at least 32x32 and at most 16 megapixels.")
            image = cv2.cvtColor(np.asarray(source.convert("RGB")), cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("The uploaded candidate image is not a safe, valid image.") from exc
    success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not success:
        raise ValueError("The candidate image could not be processed.")
    os.makedirs(destination, exist_ok=True)
    filename = f"{secrets.token_hex(16)}.jpg"
    path = os.path.join(destination, filename)
    with open(path, "xb") as image_file:
        image_file.write(encoded.tobytes())
    return filename


def delete_candidate_image(destination, filename):
    if not filename or not re.fullmatch(r"[a-f0-9]{32}\.jpg", filename):
        return
    path = os.path.join(destination, filename)
    if os.path.isfile(path):
        os.remove(path)
