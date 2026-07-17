"""Optional client for the remote OCR accelerator.

The remote path is deliberately disabled by default.  Keeping all HTTP details
in this module lets the extraction engine bypass the network path completely
when the feature flag is off.
"""

import json
import os
import threading


USE_REMOTE_OCR = False
REMOTE_OCR_URL = "https://gates-parade-floppy-eva.trycloudflare.com/ocr_process"
REMOTE_OCR_TIMEOUT_SECONDS = 30.0

_DISABLED_LOG_LOCK = threading.Lock()
_DISABLED_LOGGED = False


class RemoteOCRError(RuntimeError):
    """Raised when an enabled remote OCR request cannot produce text."""


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def load_remote_ocr_enabled(config_path=None):
    """Resolve the flag without performing any network operation."""
    env_value = os.getenv("USE_REMOTE_OCR")
    if env_value is not None:
        return _as_bool(env_value, USE_REMOTE_OCR)

    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
        return _as_bool(config.get("USE_REMOTE_OCR"), USE_REMOTE_OCR)
    except (OSError, ValueError, TypeError):
        return USE_REMOTE_OCR


def log_remote_ocr_disabled_once(log_func):
    """Emit the disabled notice once per process, even with many input files."""
    global _DISABLED_LOGGED
    if not log_func or _DISABLED_LOGGED:
        return
    with _DISABLED_LOG_LOCK:
        if _DISABLED_LOGGED:
            return
        log_func("ℹ️ [원격 OCR 비활성] USE_REMOTE_OCR=False | 로컬 최적화/멀티모달 AI 경로를 사용합니다.")
        _DISABLED_LOGGED = True


def _reset_disabled_log_for_tests():
    global _DISABLED_LOGGED
    with _DISABLED_LOG_LOCK:
        _DISABLED_LOGGED = False


class RemoteOCRClient:
    """HTTP boundary for the optional remote OCR service."""

    def __init__(self, enabled=None, url=REMOTE_OCR_URL, timeout=REMOTE_OCR_TIMEOUT_SECONDS):
        self.enabled = load_remote_ocr_enabled() if enabled is None else bool(enabled)
        self.url = url
        self.timeout = timeout

    def extract_png(self, image_bytes):
        if not self.enabled:
            raise RemoteOCRError("remote OCR is disabled")

        # Import and timeout handling live exclusively in the enabled path.
        import requests

        try:
            response = requests.post(
                self.url,
                files={"image_file": ("cropped.png", image_bytes, "image/png")},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise RemoteOCRError(str(exc)) from exc

        if response.status_code != 200:
            raise RemoteOCRError(f"네트워크 포트 통신 불능 (에이치티티피 상태 코드 {response.status_code})")

        try:
            payload = response.json()
        except ValueError as exc:
            raise RemoteOCRError("원격 OCR 응답이 JSON 형식이 아닙니다.") from exc
        if payload.get("status") != "SUCCESS":
            raise RemoteOCRError(f"원격 비전 코어 조업 거부: {payload.get('reason')}")
        return payload.get("raw_data", "")
