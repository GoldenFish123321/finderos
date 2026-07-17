"""
face_auth.py — 人脸识别登录服务

使用 OpenCV 提供人脸检测与识别功能。
- 注册：检测人脸 → 提取人脸 ROI → 训练 LBPH 模型 → 人脸图像存入数据库 BLOB
- 登录：检测人脸 → LBPH 预测 → 返回匹配用户
- v1.9.0: 人脸图像从文件系统迁移到数据库存储，不再依赖 uploads/{username}.jpg
"""

import json
import logging
import os
import shutil
import tempfile

import cv2
import numpy as np

from app.models.db import get_db

logger = logging.getLogger(__name__)

# 当前目录
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# uploads 目录（与项目根目录平级）
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads"
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

_MODEL_PATH = os.path.join(UPLOAD_DIR, "face_model.yml")
_LABELS_PATH = os.path.join(UPLOAD_DIR, "face_labels.json")
_FACE_SIZE = (100, 100)
_FACE_MARGIN_RATIO = 0.20
_FACE_CONFIDENCE_THRESHOLD = float(os.environ.get("FACE_CONFIDENCE_THRESHOLD", "105"))

# Haar cascade 文件路径（本地预下载）
_CASCADE_PATH = os.path.join(_BASE_DIR, "haarcascades", "haarcascade_frontalface_default.xml")


# ── 全局单例（避免重复加载模型） ──
def _load_face_cascade():
    """加载 Haar cascade。

    OpenCV 在 Windows 上对包含中文的路径支持不稳定。项目目录位于中文路径时，
    直接传入 _CASCADE_PATH 可能加载失败；此时复制到系统临时目录中的 ASCII
    文件名再加载。
    """
    use_direct_path = True
    try:
        _CASCADE_PATH.encode("ascii")
    except UnicodeEncodeError:
        use_direct_path = False

    if use_direct_path:
        cascade = cv2.CascadeClassifier(_CASCADE_PATH)
        if not cascade.empty():
            return cascade
    else:
        cascade = cv2.CascadeClassifier()

    fallback_path = os.path.join(tempfile.gettempdir(), "finderos_haarcascade_frontalface_default.xml")
    try:
        shutil.copyfile(_CASCADE_PATH, fallback_path)
        cascade = cv2.CascadeClassifier(fallback_path)
        if not cascade.empty():
            logger.info("Face cascade loaded via temp fallback path: %s", fallback_path)
            return cascade
    except Exception as e:
        logger.error("Failed to load face cascade from %s: %s", _CASCADE_PATH, e)
    return cascade


_face_cascade = _load_face_cascade()
_cv2_face = getattr(cv2, "face", None)
_recognizer = None
if _cv2_face is not None and hasattr(_cv2_face, "LBPHFaceRecognizer_create"):
    try:
        _recognizer = _cv2_face.LBPHFaceRecognizer_create()
    except Exception as exc:
        logger.warning("OpenCV LBPH recognizer initialization failed: %s", exc)
_model_loaded = False


def is_face_detection_available() -> bool:
    """Return whether the Haar cascade required for face detection is usable."""
    return (
        _face_cascade is not None
        and not _face_cascade.empty()
        and hasattr(cv2, "imdecode")
    )


def is_face_recognition_available() -> bool:
    """Return whether detection and the LBPH recognizer are both usable."""
    return _recognizer is not None and is_face_detection_available()


def _normalize_face(face_gray):
    """Normalize a cropped grayscale face for LBPH training and prediction."""
    if face_gray is None or face_gray.size == 0:
        return None
    if len(face_gray.shape) == 3:
        face_gray = cv2.cvtColor(face_gray, cv2.COLOR_BGR2GRAY)
    face = cv2.resize(face_gray, _FACE_SIZE, interpolation=cv2.INTER_AREA)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    face = clahe.apply(face)
    face = cv2.GaussianBlur(face, (3, 3), 0)
    return face


def _crop_face_with_margin(gray, rect):
    """Crop the detected face with margin to reduce Haar box jitter."""
    x, y, w, h = [int(v) for v in rect]
    margin_x = int(w * _FACE_MARGIN_RATIO)
    margin_y = int(h * _FACE_MARGIN_RATIO)
    x1 = max(0, x - margin_x)
    y1 = max(0, y - margin_y)
    x2 = min(gray.shape[1], x + w + margin_x)
    y2 = min(gray.shape[0], y + h + margin_y)
    return gray[y1:y2, x1:x2]


def _detect_largest_face(gray):
    """Detect the largest likely face using a few conservative fallbacks."""
    if _face_cascade.empty():
        logger.error("Face cascade is empty; cannot detect faces")
        return None
    detect_gray = cv2.equalizeHist(gray)
    configs = (
        (1.1, 5, (80, 80)),
        (1.08, 4, (60, 60)),
        (1.05, 3, (50, 50)),
    )
    for scale, neighbors, min_size in configs:
        faces = _face_cascade.detectMultiScale(
            detect_gray,
            scaleFactor=scale,
            minNeighbors=neighbors,
            minSize=min_size,
        )
        if len(faces) > 0:
            return max(faces, key=lambda item: item[2] * item[3])
    return None


def _temp_ascii_path(filename: str) -> str:
    """Return an ASCII temp path for OpenCV APIs that dislike Unicode paths."""
    safe_name = "".join(ch if ch.isascii() and (ch.isalnum() or ch in "._-") else "_" for ch in filename)
    return os.path.join(tempfile.gettempdir(), f"finderos_{os.getpid()}_{safe_name}")


def _read_image_file(path: str, flags):
    """Unicode-safe image read for Windows paths containing non-ASCII chars."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, flags)
    except Exception as e:
        logger.warning("Failed to read image from %s: %s", path, e)
        return None


def _write_image_file(path: str, image) -> bool:
    """Unicode-safe image write; unlike cv2.imwrite, works under Chinese paths."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        ext = os.path.splitext(path)[1] or ".jpg"
        ok, encoded = cv2.imencode(ext, image)
        if not ok:
            logger.error("Failed to encode face image for %s", path)
            return False
        encoded.tofile(path)
        return os.path.exists(path) and os.path.getsize(path) > 0
    except Exception as e:
        logger.error("Failed to write face image to %s: %s", path, e)
        return False


def _write_recognizer_model(path: str) -> bool:
    """Unicode-safe LBPH model write via an ASCII temporary path."""
    tmp_path = _temp_ascii_path("face_model.yml")
    try:
        _recognizer.write(tmp_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copyfile(tmp_path, path)
        return os.path.exists(path) and os.path.getsize(path) > 0
    except Exception as e:
        logger.error("Failed to write face model to %s: %s", path, e)
        return False
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def _read_recognizer_model(path: str) -> bool:
    """Unicode-safe LBPH model read via an ASCII temporary path."""
    tmp_path = _temp_ascii_path("face_model_read.yml")
    try:
        shutil.copyfile(path, tmp_path)
        _recognizer.read(tmp_path)
        return True
    except Exception as e:
        logger.warning("Failed to read face model from %s: %s", path, e)
        return False
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def _ensure_model():
    """确保 LBPH 模型已加载。"""
    global _model_loaded
    if not is_face_recognition_available():
        return
    if not _model_loaded and not os.path.exists(_MODEL_PATH) and os.path.exists(_LABELS_PATH):
        _save_model()
        return
    if not _model_loaded and os.path.exists(_MODEL_PATH):
        if _read_recognizer_model(_MODEL_PATH):
            _model_loaded = True
            logger.info("Face recognition model loaded from %s", _MODEL_PATH)


def _save_model():
    """将所有已注册的人脸图像（从数据库 BLOB）重新训练并保存 LBPH 模型。

    v1.9.0: 优先从数据库 face_image 列加载；若为空则回退到文件系统。
    """
    global _model_loaded
    if not is_face_recognition_available():
        logger.warning("OpenCV contrib face module is unavailable; face model was not trained")
        return
    if not os.path.exists(_LABELS_PATH):
        return False

    with open(_LABELS_PATH, "r", encoding="utf-8") as f:
        label_map = json.load(f)

    faces = []
    labels = []
    lid = 0
    new_map = {}

    for username in label_map:
        face_img = _load_face_from_db(username)

        # 回退：如果数据库中无数据，尝试从文件系统加载（兼容旧数据）
        if face_img is None:
            face_path = os.path.join(UPLOAD_DIR, f"{username}.jpg")
            face_img = _read_image_file(face_path, cv2.IMREAD_GRAYSCALE)

        if face_img is not None:
            if face_img.shape[:2] != _FACE_SIZE:
                face_img = cv2.resize(face_img, _FACE_SIZE, interpolation=cv2.INTER_AREA)
            faces.append(face_img)
            labels.append(lid)
            new_map[username] = lid
            lid += 1

    if faces:
        _recognizer.train(faces, np.array(labels, dtype=np.int32))
        if not _write_recognizer_model(_MODEL_PATH):
            _model_loaded = False
            return False
        with open(_LABELS_PATH, "w", encoding="utf-8") as f:
            json.dump(new_map, f)
        _model_loaded = True
        logger.info("Face model retrained with %d samples (from DB)", len(faces))
        return True
    else:
        # 没有人脸数据时删除模型文件
        if os.path.exists(_MODEL_PATH):
            os.remove(_MODEL_PATH)
        _model_loaded = False
        with open(_LABELS_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return False


def _load_face_from_db(username: str):
    """从数据库加载用户的人脸图像（100×100 灰度图）。

    Returns:
        numpy.ndarray | None: 灰度人脸图像，或 None 表示无数据
    """
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT face_image FROM users WHERE username = ?", (username,)
            ).fetchone()
            if row and row.get("face_image") is not None:
                blob = row["face_image"]
                nparr = np.frombuffer(blob, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
                return img
    except Exception as e:
        logger.warning("Failed to load face from DB for %s: %s", username, e)
    return None


def detect_face(image_bytes: bytes):
    """从图片字节数据中检测一张人脸，返回归一化后的灰度 ROI (100×100) 或 None。

    Args:
        image_bytes: 原始图片字节数据（支持 jpg/png 等格式）

    Returns:
        numpy.ndarray | None: 100×100 的灰度人脸图
    """
    if not is_face_detection_available():
        return None
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    # 降低超大摄像头图像对 Haar 检测的抖动影响，同时保留足够细节。
    max_side = max(img.shape[:2])
    if max_side > 960:
        scale = 960.0 / max_side
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    rect = _detect_largest_face(gray)
    if rect is None:
        return None

    face = _crop_face_with_margin(gray, rect)
    return _normalize_face(face)


def register_face(username: str, image_bytes: bytes) -> bool:
    """注册用户人脸。

    检测人脸并保存归一化图像到数据库 BLOB，然后重新训练 LBPH 模型。

    Args:
        username: 用户名
        image_bytes: 上传的图片数据

    Returns:
        bool: 是否注册成功（检测到且只有一张人脸）
    """
    face = detect_face(image_bytes)
    if face is None:
        return False

    # 将归一化人脸图像编码为 JPEG 存入数据库 BLOB
    ok, encoded_face = cv2.imencode(".jpg", face)
    if not ok:
        logger.error("Failed to encode face image for %s", username)
        return False
    face_blob = encoded_face.tobytes()

    # 备份旧数据（用于回滚）
    previous_blob = None
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT face_image FROM users WHERE username = ?", (username,)
            ).fetchone()
            if row:
                previous_blob = row.get("face_image")
    except Exception:
        pass

    # 保存人脸图像到数据库
    try:
        with get_db() as conn:
            # 检查用户是否存在
            existing = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE users SET face_image = ? WHERE username = ?",
                    (face_blob, username),
                )
            else:
                # 用户不存在时创建一个最小记录（用于测试或边缘场景）
                conn.execute(
                    "INSERT INTO users (username, password_hash, salt, face_image) "
                    "VALUES (?, ?, ?, ?)",
                    (username, "", "", face_blob),
                )
    except Exception as e:
        logger.error("Failed to save face image to DB for %s: %s", username, e)
        return False

    # 更新标签映射
    label_map = {}
    if os.path.exists(_LABELS_PATH):
        with open(_LABELS_PATH, "r", encoding="utf-8") as f:
            label_map = json.load(f)
    original_label_map = dict(label_map)
    if username not in label_map:
        label_map[username] = 0  # 占位，_save_model 会重新分配

    with open(_LABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(label_map, f)

    # 重新训练模型
    if not _save_model():
        logger.error("Face model training failed after registering %s", username)
        # 回滚：恢复旧的人脸数据和标签
        try:
            with get_db() as conn:
                conn.execute(
                    "UPDATE users SET face_image = ? WHERE username = ?",
                    (previous_blob, username),
                )
            with open(_LABELS_PATH, "w", encoding="utf-8") as f:
                json.dump(original_label_map, f)
        except Exception as e:
            logger.warning("Failed to rollback face registration for %s: %s", username, e)
        return False
    return True


def recognize_face(image_bytes: bytes):
    """识别人脸，返回匹配的用户名和置信度。

    Args:
        image_bytes: 上传的图片字节数据

    Returns:
        tuple[str, float] | None: (用户名, 置信度)，置信度越低越匹配
    """
    if not is_face_recognition_available():
        return None
    _ensure_model()
    face = detect_face(image_bytes)
    if face is None:
        return None

    if not os.path.exists(_MODEL_PATH):
        return None

    try:
        label, confidence = _recognizer.predict(face)
        # LBPH：置信度越低表示匹配度越高。摄像头光照/距离变化较大，阈值允许通过环境变量调整。
        if confidence > _FACE_CONFIDENCE_THRESHOLD:
            logger.info(
                "Face recognition rejected by confidence: %.2f > %.2f",
                confidence,
                _FACE_CONFIDENCE_THRESHOLD,
            )
            return None

        if not os.path.exists(_LABELS_PATH):
            return None

        with open(_LABELS_PATH, "r", encoding="utf-8") as f:
            label_map = json.load(f)

        reverse_map = {v: k for k, v in label_map.items()}
        username = reverse_map.get(label)
        if username:
            return (username, float(confidence))
    except Exception as e:
        logger.error("Face recognition error: %s", e)

    return None


def has_face(username: str) -> bool:
    """检查用户是否已注册人脸（数据库中有 face_image BLOB）。"""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT face_image FROM users WHERE username = ?", (username,)
            ).fetchone()
            return bool(row and row.get("face_image") is not None)
    except Exception:
        # 回退到文件检查（兼容旧数据）
        return os.path.exists(os.path.join(UPLOAD_DIR, f"{username}.jpg"))


def delete_face(username: str):
    """删除用户注册的人脸数据。"""
    # 清除数据库中的 face_image
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE users SET face_image = NULL WHERE username = ?",
                (username,),
            )
    except Exception as e:
        logger.warning("Failed to clear face_image from DB for %s: %s", username, e)

    # 同时清理可能存在的旧文件
    face_path = os.path.join(UPLOAD_DIR, f"{username}.jpg")
    if os.path.exists(face_path):
        try:
            os.remove(face_path)
        except OSError:
            pass

    # 更新标签映射
    if os.path.exists(_LABELS_PATH):
        with open(_LABELS_PATH, "r", encoding="utf-8") as f:
            label_map = json.load(f)
        if username in label_map:
            del label_map[username]
            with open(_LABELS_PATH, "w", encoding="utf-8") as f:
                json.dump(label_map, f)

    # 重新训练模型（组件不可用时仍允许清理已保存的数据）
    if is_face_recognition_available():
        _save_model()
    elif os.path.exists(_MODEL_PATH):
        os.remove(_MODEL_PATH)


def get_face_count() -> int:
    """获取已注册人脸的用户数量。"""
    if not os.path.exists(_LABELS_PATH):
        return 0
    with open(_LABELS_PATH, "r", encoding="utf-8") as f:
        label_map = json.load(f)
    return len(label_map)
