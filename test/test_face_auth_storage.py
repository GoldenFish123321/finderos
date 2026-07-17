import json

import cv2
import numpy as np

from app.services import face_auth
from app.models.db import get_db


def test_register_face_persists_to_database(tmp_path, monkeypatch):
    """v1.9.0: 人脸录入应将归一化图像存入数据库 BLOB 而非文件系统。"""
    upload_dir = tmp_path / "中文上传目录"
    upload_dir.mkdir(parents=True, exist_ok=True)
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

    # 验证图像已存入数据库 BLOB
    stored = face_auth._load_face_from_db("alice")
    assert stored is not None
    assert stored.shape == face_auth._FACE_SIZE

    # 标签映射应正常写入
    with labels_path.open("r", encoding="utf-8") as f:
        labels = json.load(f)
    assert "alice" in labels


def test_register_face_fails_when_db_write_fails(tmp_path, monkeypatch):
    """若数据库写入失败，注册接口必须返回 False 而不是假成功。"""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    face = np.full(face_auth._FACE_SIZE, 127, dtype=np.uint8)

    monkeypatch.setattr(face_auth, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(face_auth, "_LABELS_PATH", str(upload_dir / "face_labels.json"))

    # 模拟 detect_face 成功但 DB 写入失败
    call_count = [0]

    def mock_detect(image_bytes):
        call_count[0] += 1
        if call_count[0] == 1:
            return face  # 第一次调用（detect_face）成功
        return None  # 后续调用返回 None

    original_get_db = face_auth.get_db
    def mock_get_db():
        raise RuntimeError("Simulated DB failure")

    monkeypatch.setattr(face_auth, "detect_face", mock_detect)
    monkeypatch.setattr(face_auth, "get_db", mock_get_db)

    assert face_auth.register_face("bob", b"fake-image") is False
    assert not (upload_dir / "face_labels.json").exists()


def test_register_face_rolls_back_previous_template_when_retrain_fails(tmp_path, monkeypatch):
    """重复录入失败时不能破坏旧的人脸模板（DB 中应保留旧数据）。"""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    labels_path = upload_dir / "face_labels.json"
    old_face = np.full(face_auth._FACE_SIZE, 64, dtype=np.uint8)
    new_face = np.full(face_auth._FACE_SIZE, 180, dtype=np.uint8)

    monkeypatch.setattr(face_auth, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(face_auth, "_LABELS_PATH", str(labels_path))
    monkeypatch.setattr(face_auth, "detect_face", lambda image_bytes: old_face)
    monkeypatch.setattr(face_auth, "_save_model", lambda: True)
    assert face_auth.register_face("carol", b"old") is True

    # 第二次注册：detect_face 返回新图像，但 _save_model 失败
    monkeypatch.setattr(face_auth, "detect_face", lambda image_bytes: new_face)
    monkeypatch.setattr(face_auth, "_save_model", lambda: False)
    assert face_auth.register_face("carol", b"new") is False

    # 回滚后 DB 中应保留旧的人脸图像（均值约 64）
    stored = face_auth._load_face_from_db("carol")
    assert stored is not None
    assert abs(int(stored.mean()) - 64) <= 2
    # 标签映射应保留
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
