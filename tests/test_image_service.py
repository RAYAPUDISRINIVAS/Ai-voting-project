from io import BytesIO

import cv2
import numpy as np
import pytest
from werkzeug.datastructures import FileStorage

from services.image_service import save_candidate_image


def test_candidate_image_is_reencoded_with_random_safe_name(tmp_path):
    source = np.full((80, 90, 3), 140, dtype=np.uint8)
    success, data = cv2.imencode(".png", source)
    assert success
    upload = FileStorage(
        stream=BytesIO(data.tobytes()),
        filename="portrait.png",
        content_type="image/png",
    )

    filename = save_candidate_image(upload, str(tmp_path))

    assert filename.endswith(".jpg")
    assert len(filename) == 36
    stored = cv2.imread(str(tmp_path / filename))
    assert stored.shape[:2] == (80, 90)


def test_candidate_image_rejects_mismatched_upload_type(tmp_path):
    upload = FileStorage(
        stream=BytesIO(b"not an image"),
        filename="payload.svg",
        content_type="image/svg+xml",
    )
    with pytest.raises(ValueError, match="JPEG or PNG"):
        save_candidate_image(upload, str(tmp_path))
