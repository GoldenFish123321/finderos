import json

import cv2
import numpy as np

from app.services import face_auth


def test_register_face_persists_image_under_unicode_upload_dir(tmp_path, monkeypatch):
    """人脸录入应在中文路径下真实写出图片，避免页面刷新后仍显示未录入。"""
    upload_dir = tmp_path / "中文上传目录"
    labels_path = upload_dir / "face_labels.json"
    model_path = upload_dir / "face_model.yml"
    face = np.full(face_auth._FACE_SIZE, 127, dtype=np.uint8)

    monkeypatch.setattr(face_auth, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(face_auth, "_LABELS_PATH", str(labels_path))
    monkeypatch.setattr(face_auth, "_MODEL_PATH", str(model_path))
    monkeypatch.setattr(face_auth, "detect_face", lambda image_bytes: face)
    monkeypatch.setattr(face_auth, "_save_model", lambda: True)

    assert face_auth.register_face("alice", b"fake-image") is True
    assert face_auth.has_face("alice") is True

    stored = face_auth._read_image_file(str(upload_dir / "alice.jpg"), cv2.IMREAD_GRAYSCALE)
    assert stored is not None
    assert stored.shape == face_auth._FACE_SIZE

    with labels_path.open("r", encoding="utf-8") as f:
        labels = json.load(f)
    assert "alice" in labels


def test_register_face_fails_when_image_file_cannot_be_saved(tmp_path, monkeypatch):
    """若后端无法写入人脸文件，注册接口必须失败而不是假成功。"""
    upload_dir = tmp_path / "uploads"
    face = np.full(face_auth._FACE_SIZE, 127, dtype=np.uint8)

    monkeypatch.setattr(face_auth, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(face_auth, "_LABELS_PATH", str(upload_dir / "face_labels.json"))
    monkeypatch.setattr(face_auth, "detect_face", lambda image_bytes: face)
    monkeypatch.setattr(face_auth, "_write_image_file", lambda path, image: False)

    assert face_auth.register_face("bob", b"fake-image") is False
    assert not (upload_dir / "face_labels.json").exists()


def test_register_face_rolls_back_previous_template_when_retrain_fails(tmp_path, monkeypatch):
    """重复录入失败时不能破坏旧的人脸模板。"""
    upload_dir = tmp_path / "uploads"
    labels_path = upload_dir / "face_labels.json"
    old_face = np.full(face_auth._FACE_SIZE, 64, dtype=np.uint8)
    new_face = np.full(face_auth._FACE_SIZE, 180, dtype=np.uint8)

    monkeypatch.setattr(face_auth, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(face_auth, "_LABELS_PATH", str(labels_path))
    monkeypatch.setattr(face_auth, "detect_face", lambda image_bytes: old_face)
    monkeypatch.setattr(face_auth, "_save_model", lambda: True)
    assert face_auth.register_face("carol", b"old") is True

    monkeypatch.setattr(face_auth, "detect_face", lambda image_bytes: new_face)
    monkeypatch.setattr(face_auth, "_save_model", lambda: False)
    assert face_auth.register_face("carol", b"new") is False

    stored = face_auth._read_image_file(str(upload_dir / "carol.jpg"), cv2.IMREAD_GRAYSCALE)
    assert stored is not None
    assert abs(int(stored.mean()) - 64) <= 2
    with labels_path.open("r", encoding="utf-8") as f:
        assert "carol" in json.load(f)


def test_face_detection_uses_largest_candidate_and_normalizes(monkeypatch):
    """检测阶段取最大人脸并输出统一尺寸模板，减少检测框抖动影响。"""
    class FakeCascade:
        def empty(self):
            return False

        def detectMultiScale(self, *args, **kwargs):
            return np.array([[10, 10, 30, 30], [20, 20, 80, 80]])

    monkeypatch.setattr(face_auth, "_face_cascade", FakeCascade())
    image = np.zeros((180, 180, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok

    face = face_auth.detect_face(encoded.tobytes())
    assert face is not None
    assert face.shape == face_auth._FACE_SIZE
