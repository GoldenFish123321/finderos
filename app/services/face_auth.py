"""
face_auth.py — 人脸识别登录服务

使用 OpenCV 提供人脸检测与识别功能。
- 注册：检测人脸 → 提取人脸 ROI → 训练 LBPH 模型
- 登录：检测人脸 → LBPH 预测 → 返回匹配用户
"""

import json
import logging
import os

import cv2
import numpy as np

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

# Haar cascade 文件路径（本地预下载）
_CASCADE_PATH = os.path.join(_BASE_DIR, "haarcascades", "haarcascade_frontalface_default.xml")


# ── 全局单例（避免重复加载模型） ──
_face_cascade = cv2.CascadeClassifier(_CASCADE_PATH)
_cv2_face = getattr(cv2, "face", None)
_recognizer = None
if _cv2_face is not None and hasattr(_cv2_face, "LBPHFaceRecognizer_create"):
    try:
        _recognizer = _cv2_face.LBPHFaceRecognizer_create()
    except Exception as exc:
        logger.warning("OpenCV LBPH recognizer initialization failed: %s", exc)
_model_loaded = False


def is_face_recognition_available() -> bool:
    """Return whether the installed OpenCV build provides usable LBPH support."""
    return (
        _recognizer is not None
        and _face_cascade is not None
        and not _face_cascade.empty()
    )


def _ensure_model():
    """确保 LBPH 模型已加载。"""
    global _model_loaded
    if not is_face_recognition_available():
        return
    if not _model_loaded and not os.path.exists(_MODEL_PATH) and os.path.exists(_LABELS_PATH):
        _save_model()
        return
    if not _model_loaded and os.path.exists(_MODEL_PATH):
        try:
            _recognizer.read(_MODEL_PATH)
            _model_loaded = True
            logger.info("Face recognition model loaded from %s", _MODEL_PATH)
        except Exception as e:
            logger.warning("Failed to load face model: %s", e)


def _save_model():
    """将所有已注册的人脸图像重新训练并保存模型。"""
    global _model_loaded
    if not is_face_recognition_available():
        logger.warning("OpenCV contrib face module is unavailable; face model was not trained")
        return
    if not os.path.exists(_LABELS_PATH):
        return

    with open(_LABELS_PATH, "r", encoding="utf-8") as f:
        label_map = json.load(f)

    faces = []
    labels = []
    lid = 0
    new_map = {}
    for username in label_map:
        face_path = os.path.join(UPLOAD_DIR, f"{username}.jpg")
        img = cv2.imread(face_path, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            faces.append(img)
            labels.append(lid)
            new_map[username] = lid
            lid += 1

    if faces:
        _recognizer.train(faces, np.array(labels, dtype=np.int32))
        _recognizer.write(_MODEL_PATH)
        with open(_LABELS_PATH, "w", encoding="utf-8") as f:
            json.dump(new_map, f)
        _model_loaded = True
        logger.info("Face model retrained with %d samples", len(faces))
    else:
        # 没有人脸数据时删除模型文件
        if os.path.exists(_MODEL_PATH):
            os.remove(_MODEL_PATH)
        _model_loaded = False
        with open(_LABELS_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)


def detect_face(image_bytes: bytes):
    """从图片字节数据中检测一张人脸，返回归一化后的灰度 ROI (100×100) 或 None。

    Args:
        image_bytes: 原始图片字节数据（支持 jpg/png 等格式）

    Returns:
        numpy.ndarray | None: 100×100 的灰度人脸图
    """
    if not is_face_recognition_available():
        return None
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = _face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))

    if len(faces) != 1:
        return None

    x, y, w, h = faces[0]
    face = gray[y : y + h, x : x + w]
    face = cv2.resize(face, (100, 100))
    face = cv2.equalizeHist(face)  # 直方图均衡化，改善光照影响
    return face


def register_face(username: str, image_bytes: bytes) -> bool:
    """注册用户人脸。

    检测人脸并保存到 uploads/{username}.jpg，然后重新训练 LBPH 模型。

    Args:
        username: 用户名
        image_bytes: 上传的图片数据

    Returns:
        bool: 是否注册成功（检测到且只有一张人脸）
    """
    if not is_face_recognition_available():
        return False
    face = detect_face(image_bytes)
    if face is None:
        return False

    # 保存人脸图像
    face_path = os.path.join(UPLOAD_DIR, f"{username}.jpg")
    cv2.imwrite(face_path, face)

    # 更新标签映射
    label_map = {}
    if os.path.exists(_LABELS_PATH):
        with open(_LABELS_PATH, "r", encoding="utf-8") as f:
            label_map = json.load(f)
    if username not in label_map:
        label_map[username] = 0  # 占位，_save_model 会重新分配

    with open(_LABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(label_map, f)

    # 重新训练模型
    _save_model()
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
        # LBPH：置信度越低表示匹配度越高，通常 < 80 为可靠匹配
        if confidence > 80:
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
    """检查用户是否已注册人脸。"""
    return os.path.exists(os.path.join(UPLOAD_DIR, f"{username}.jpg"))


def delete_face(username: str):
    """删除用户注册的人脸。"""
    face_path = os.path.join(UPLOAD_DIR, f"{username}.jpg")
    if os.path.exists(face_path):
        os.remove(face_path)

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
