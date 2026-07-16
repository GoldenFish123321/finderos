import importlib.util
import json
import sys
from types import SimpleNamespace

from tornado.template import Loader


class _Cascade:
    def empty(self):
        return False


class _Cv2WithoutFace:
    def CascadeClassifier(self, path):
        return _Cascade()


def _load_face_auth(name):
    spec = importlib.util.spec_from_file_location(name, "app/services/face_auth.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_face_auth_imports_without_opencv_contrib(monkeypatch):
    monkeypatch.setitem(sys.modules, "cv2", _Cv2WithoutFace())
    monkeypatch.setitem(
        sys.modules,
        "numpy",
        SimpleNamespace(uint8=object(), int32=object()),
    )
    module = _load_face_auth("face_auth_without_contrib")

    assert module.is_face_recognition_available() is False
    assert module.register_face("admin", b"not-an-image") is False
    assert module.recognize_face(b"not-an-image") is None


def test_face_auth_degrades_when_lbph_factory_raises(monkeypatch):
    class _BrokenFace:
        @staticmethod
        def LBPHFaceRecognizer_create():
            raise RuntimeError("native ABI mismatch")

    cv2_module = _Cv2WithoutFace()
    cv2_module.face = _BrokenFace()
    monkeypatch.setitem(sys.modules, "cv2", cv2_module)
    monkeypatch.setitem(
        sys.modules,
        "numpy",
        SimpleNamespace(uint8=object(), int32=object()),
    )

    module = _load_face_auth("face_auth_broken_contrib")
    assert module.is_face_recognition_available() is False


def test_delete_face_removes_stale_model_when_contrib_is_unavailable(
    monkeypatch, tmp_path
):
    monkeypatch.setitem(sys.modules, "cv2", _Cv2WithoutFace())
    monkeypatch.setitem(
        sys.modules,
        "numpy",
        SimpleNamespace(uint8=object(), int32=object()),
    )
    module = _load_face_auth("face_auth_delete_without_contrib")
    module.UPLOAD_DIR = str(tmp_path)
    module._MODEL_PATH = str(tmp_path / "face_model.yml")
    module._LABELS_PATH = str(tmp_path / "face_labels.json")
    (tmp_path / "admin.jpg").write_bytes(b"face-data")
    (tmp_path / "face_model.yml").write_text("stale-biometric-model")
    (tmp_path / "face_labels.json").write_text(
        json.dumps({"admin": 0}), encoding="utf-8"
    )

    module.delete_face("admin")

    assert not (tmp_path / "admin.jpg").exists()
    assert not (tmp_path / "face_model.yml").exists()
    assert json.loads((tmp_path / "face_labels.json").read_text("utf-8")) == {}


def test_missing_model_is_rebuilt_when_contrib_becomes_available(
    monkeypatch, tmp_path
):
    class _Recognizer:
        def __init__(self):
            self.trained = False

        def train(self, faces, labels):
            self.trained = bool(faces) and list(labels) == [0]

        def write(self, path):
            assert self.trained
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("rebuilt")

        def read(self, path):
            pass

    recognizer = _Recognizer()
    cv2_module = _Cv2WithoutFace()
    cv2_module.face = SimpleNamespace(
        LBPHFaceRecognizer_create=lambda: recognizer
    )
    cv2_module.IMREAD_GRAYSCALE = 0
    cv2_module.imread = lambda path, mode: object()
    monkeypatch.setitem(sys.modules, "cv2", cv2_module)
    monkeypatch.setitem(
        sys.modules,
        "numpy",
        SimpleNamespace(
            uint8=object(),
            int32=object(),
            array=lambda values, dtype=None: values,
        ),
    )
    module = _load_face_auth("face_auth_rebuild_model")
    module.UPLOAD_DIR = str(tmp_path)
    module._MODEL_PATH = str(tmp_path / "face_model.yml")
    module._LABELS_PATH = str(tmp_path / "face_labels.json")
    (tmp_path / "remaining.jpg").write_bytes(b"face-data")
    (tmp_path / "face_labels.json").write_text(
        json.dumps({"remaining": 9}), encoding="utf-8"
    )

    module._ensure_model()

    assert recognizer.trained
    assert (tmp_path / "face_model.yml").read_text("utf-8") == "rebuilt"
    assert json.loads((tmp_path / "face_labels.json").read_text("utf-8")) == {
        "remaining": 0
    }
    assert module._model_loaded is True


def test_account_template_keeps_password_form_when_face_is_unavailable():
    html = Loader("app/templates").load("user_account.html").generate(
        title="账户设置",
        settings=SimpleNamespace(SYSTEM_NAME="FinderOS"),
        static_url=lambda path: "/static/" + path,
        app_version="test",
        username="admin",
        face_registered=False,
        face_enabled=False,
        face_available=False,
        message="",
        error="",
        xsrf_token="test-token",
        _tt_modules=SimpleNamespace(
            xsrf_form_html=lambda: '<input type="hidden" name="_xsrf" value="test-token">'
        ),
    ).decode("utf-8")

    assert 'name="old_password"' in html
    assert "人脸识别组件当前不可用" in html
    assert 'id="face-open-cam"' not in html
