"""프로젝트 루트 기준 API 설정 로딩과 민감정보 없는 상태 진단."""

from __future__ import annotations

import json
import os
import sys
from importlib import import_module
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, MutableMapping

try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:  # pragma: no cover - 최소 실행환경 호환
    _DOTENV_AVAILABLE = False
    def load_dotenv(*_args, **_kwargs):
        return False


PROJECT_ROOT = Path(__file__).resolve().parent

VERTEX_REQUIRED_IMPORTS = (
    ("google.auth", "google-auth"),
    ("google.genai", "google-genai"),
    ("google.oauth2.service_account", "google-auth"),
    ("google.auth.transport.requests", "google-auth requests transport"),
)


class APIConfigError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code


def _clean(value: object) -> str:
    return str(value or "").strip().strip('"').strip("'").strip()


def _load_project_env(path: Path, env: MutableMapping[str, str]) -> None:
    if _DOTENV_AVAILABLE:
        load_dotenv(dotenv_path=path, override=False)
        return
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for line in lines:
        candidate = line.strip()
        if not candidate or candidate.startswith("#") or "=" not in candidate:
            continue
        if candidate.startswith("export "):
            candidate = candidate[7:].lstrip()
        name, value = candidate.split("=", 1)
        name = name.strip()
        if not name or not name.replace("_", "a").isalnum() or name[0].isdigit():
            continue
        env.setdefault(name, _clean(value))


@dataclass(frozen=True)
class APISettings:
    project_root: Path
    env_file_found: bool
    novita_api_key: str
    deepseek_api_key: str
    openai_api_key: str
    vertex_credential_path: Path | None
    vertex_project: str
    vertex_location: str
    vertex_error_code: str
    kosha_service_key: str
    kosha_base_url: str

    def diagnostic_status(self) -> dict[str, str]:
        return {
            "NOVITA_API_KEY": "configured" if self.novita_api_key else "missing",
            "DEEPSEEK_API_KEY": "configured" if self.deepseek_api_key else "missing",
            "OPENAI_API_KEY": "configured" if self.openai_api_key else "missing",
            "VERTEX_CREDENTIAL_FILE": "found" if self.vertex_credential_path else "missing",
            "VERTEX_PROJECT": "configured" if self.vertex_project else "missing",
            "VERTEX_LOCATION": "configured" if self.vertex_location else "missing",
            "KOSHA_SERVICE_KEY": "configured" if self.kosha_service_key else "missing",
        }

    def require_vertex(self) -> tuple[Path, str, str]:
        if self.vertex_error_code:
            raise APIConfigError(self.vertex_error_code)
        if self.vertex_credential_path is None:
            raise APIConfigError("VERTEX_CREDENTIAL_FILE_MISSING")
        return self.vertex_credential_path, self.vertex_project, self.vertex_location


def load_api_settings(
    project_root: Path | str = PROJECT_ROOT,
    *,
    environ: MutableMapping[str, str] | None = None,
    load_env_file: bool = True,
) -> APISettings:
    """OS 환경을 우선하고 `.env`는 프로젝트 루트에서 빈 값만 보충한다."""
    root = Path(project_root).resolve()
    env = os.environ if environ is None else environ
    env_path = root / ".env"
    if load_env_file and environ is None and env_path.is_file():
        _load_project_env(env_path, env)

    raw_credential = _clean(env.get("GOOGLE_APPLICATION_CREDENTIALS"))
    credential_candidate = Path(raw_credential) if raw_credential else Path("vertex_key.json")
    if not credential_candidate.is_absolute():
        credential_candidate = root / credential_candidate
    credential_candidate = credential_candidate.resolve()

    vertex_error = ""
    credential_path: Path | None = credential_candidate if credential_candidate.is_file() else None
    json_project = ""
    if credential_path:
        try:
            payload = json.loads(credential_path.read_text(encoding="utf-8"))
            json_project = _clean(payload.get("project_id")) if isinstance(payload, Mapping) else ""
        except (OSError, ValueError, TypeError):
            vertex_error = "VERTEX_CREDENTIAL_INVALID"
            credential_path = None
    else:
        vertex_error = "VERTEX_CREDENTIAL_FILE_MISSING"

    explicit_project = _clean(env.get("GOOGLE_CLOUD_PROJECT"))
    if explicit_project and json_project and explicit_project != json_project:
        vertex_error = "VERTEX_PROJECT_ID_MISMATCH"
    vertex_project = explicit_project or json_project or "msds-engine-v6"
    vertex_location = _clean(env.get("GOOGLE_CLOUD_LOCATION")) or "us-central1"

    if credential_path is not None:
        env["GOOGLE_APPLICATION_CREDENTIALS"] = str(credential_path)

    return APISettings(
        project_root=root,
        env_file_found=env_path.is_file(),
        novita_api_key=_clean(env.get("NOVITA_API_KEY")),
        deepseek_api_key=_clean(env.get("DEEPSEEK_API_KEY")),
        openai_api_key=_clean(env.get("OPENAI_API_KEY")),
        vertex_credential_path=credential_path,
        vertex_project=vertex_project,
        vertex_location=vertex_location,
        vertex_error_code=vertex_error,
        kosha_service_key=_clean(env.get("SERVICE_KEY")),
        kosha_base_url=_clean(env.get("BASE_URL")),
    )


def api_status_lines(settings: APISettings) -> list[str]:
    """키·경로·JSON 원문 없이 활성화 상태만 반환한다."""
    return [f"{name}: {state}" for name, state in settings.diagnostic_status().items()]


def vertex_dependency_preflight(*, importer=import_module) -> tuple[str, ...]:
    """Vertex 유료 호출 전에 실제 런타임의 필수 import를 검증한다."""
    missing = []
    for module_name, package_name in VERTEX_REQUIRED_IMPORTS:
        try:
            importer(module_name)
        except (ImportError, ModuleNotFoundError):
            if package_name not in missing:
                missing.append(package_name)
    if missing:
        raise APIConfigError("VERTEX_DEPENDENCY_MISSING", ",".join(missing))
    return tuple(module_name for module_name, _package_name in VERTEX_REQUIRED_IMPORTS)


def python_runtime_metadata() -> dict[str, str]:
    """회귀 산출물에 기록할 실제 Python 실행기 정보."""
    return {
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version,
    }
