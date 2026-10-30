import pytest

from face_service import FaceServiceError, compare_encodings, decode_image


def test_invalid_face_capture_reports_clear_error():
    with pytest.raises(FaceServiceError, match="valid image"):
        decode_image("data:image/jpeg;base64,ZmFrZQ==")


def test_face_comparison_returns_distance_and_threshold_result():
    verified, distance = compare_encodings([0.0, 0.0], [0.3, 0.4], 0.6)
    assert verified
    assert distance == pytest.approx(0.5)


def test_face_comparison_rejects_mismatched_encoding_shapes():
    with pytest.raises(FaceServiceError, match="invalid"):
        compare_encodings([0.0], [0.0, 1.0], 0.5)
