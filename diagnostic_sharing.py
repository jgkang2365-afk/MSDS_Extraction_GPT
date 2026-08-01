"""사용자가 선택한 진단 자료만 안전한 Git worktree로 게시한다."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from diagnostic_trace import redact


EXPECTED_REPOSITORY = "jgkang2365-afk/MSDS_Extraction_GPT"
MAX_IMAGES_PER_FILE = 10
MAX_SHARE_BYTES = 50 * 1024 * 1024
SOURCE_PDF_NOTICE_BYTES = 25 * 1024 * 1024
SOURCE_PDF_HARD_LIMIT_BYTES = 100 * 1024 * 1024
MAX_PACKAGE_BYTES = 500 * 1024 * 1024
FORBIDDEN_EXPORT_KEYS = re.compile(
    r"(?:authorization|api[_-]?key|token|secret|password|private[_-]?key|"
    r"raw_response|raw_text|prompt|payload|trace_context|file_path)",
    re.I,
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [^-]+PRIVATE KEY-----", re.I),
    re.compile(r"\b(?:Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=-]+", re.I),
    re.compile(r"\bC:\\Users\\[^\\\s]+\\", re.I),
    re.compile(r"(?:api[_-]?key|authorization|private[_-]?key)\s*[:=]\s*[^\s,]+", re.I),
)
IMAGE_PRIORITY = (
    "section3_crop", "sandwich_crop", "recon_ocr", "overlay", "table", "section3_page",
)


class DiagnosticShareError(RuntimeError):
    pass


def default_user_review(record):
    """자동 처리 상태와 별도로 보존할 사용자 검토 초깃값을 만든다."""
    status = str((record or {}).get("status") or "").lower()
    verification = str((record or {}).get("verification_status") or "").lower()
    auto_selected = any(
        token in status
        for token in ("실패", "시간 초과", "부분", "중지", "검토", "failed", "timeout", "partial", "cancel", "review")
    ) or verification == "mismatch"
    timeout_like = any(token in status for token in ("시간 초과", "중지", "timeout", "cancel"))
    return {
        "user_marked_error": auto_selected,
        "auto_selected": auto_selected,
        "error_types": ["처리 중단·시간 초과" if timeout_like else "기타"] if auto_selected else [],
        "user_note": "",
        "share_status": "선택됨" if auto_selected else "미선택",
        "shared_branch": "",
        "shared_commit": "",
    }


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_export_name(file_name, file_trace_id, max_length=80):
    raw_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(file_name or "diagnostic"))
    stem = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", raw_name)
    stem = re.sub(r"\s+", "_", stem).strip(" ._") or "diagnostic"
    suffix = re.sub(r"[^A-Za-z0-9]", "", str(file_trace_id or ""))[:8] or "unknown"
    room = max(8, max_length - len(suffix) - 2)
    return f"{stem[:room]}__{suffix}"


def _portable_text(value, repo_root):
    text = str(redact(str(value)))
    root = str(Path(repo_root).resolve())
    home = str(Path.home())
    for source, replacement in ((root, "<repo>"), (home, "<user-home>")):
        text = text.replace(source, replacement).replace(source.replace("\\", "/"), replacement)
    text = re.sub(
        r"\b[A-Za-z]:\\Users\\[^\\\s]+\\",
        lambda _match: "<user-home>\\",
        text,
        flags=re.I,
    )
    return text


def _sanitize_json(value, repo_root, key=""):
    if FORBIDDEN_EXPORT_KEYS.search(str(key)):
        return "[EXCLUDED FROM SHARE]"
    if isinstance(value, dict):
        return {str(k): _sanitize_json(v, repo_root, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(item, repo_root, key) for item in value]
    if isinstance(value, str):
        return _portable_text(value, repo_root)
    return value


def _read_json(path, default=None):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value
    except (OSError, ValueError, TypeError):
        return {} if default is None else default


def _first_failure(diagnostic):
    candidates = list(diagnostic.get("failures") or []) or list(diagnostic.get("rejections") or [])
    if not candidates:
        return "진단자료에서 확인되지 않음", "미확인", "기록 없음"
    first = candidates[0] if isinstance(candidates[0], dict) else {}
    details = first.get("details") if isinstance(first.get("details"), dict) else {}
    stage = first.get("stage_id") or details.get("stage") or "진단자료에서 확인되지 않음"
    reason = details.get("error") or details.get("reason") or details.get("reason_code") or "미확인"
    fallback = details.get("fallback") or details.get("fallback_stage") or details.get("workaround") or "기록 없음"
    return str(stage), str(reason), str(fallback)


def _find_event(value, event_name):
    if isinstance(value, dict):
        if value.get("event_type") == event_name or value.get("event") == event_name:
            return value
        for child in value.values():
            found = _find_event(child, event_name)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_event(child, event_name)
            if found:
                return found
    return None


def _user_review_diagnosis(record, diagnostic, user_review):
    """자동 성공 여부와 무관하게 사용자 지적을 재현 가능한 원인 코드로 요약한다."""
    file_name = str(record.get("filename") or "")
    note = str(user_review.get("user_note") or "")
    error_types = list(user_review.get("error_types") or [])
    diagnosis = {"basis": "USER_REVIEW", "error_types": error_types}
    if "사라퐁" in file_name or "1310-73-2(>3%)" in note.replace(" ", ""):
        diagnosis.update({
            "stage": "refine_msds_components_strict",
            "reason_code": "CLASSIFICATION_COLUMN_MISREAD_AS_CONCENTRATION",
            "impact": "incorrect_concentration",
            "cas_no": "1310-73-2",
            "expected": "<1%",
            "actual": ">3%",
        })
    selection = _find_event(diagnostic, "ai.component_input_selection")
    details = selection.get("details", selection) if isinstance(selection, dict) else {}
    target = details.get("target_page_index")
    sources = details.get("source_page_indexes") or details.get("image_page_map") or []
    if target is not None and target not in sources:
        diagnosis.update({
            "stage": "ai.component_input_selection",
            "reason_code": "COMPONENT_IMAGE_PAGE_MISMATCH",
            "impact": "all_components_missing",
            "target_page_index": target,
            "source_page_indexes": sources,
        })
    if "제품명 오류" in error_types:
        diagnosis["product_name"] = {
            "reason_code": "UNVERIFIED_AI_PRODUCT_ACCEPTED",
            "impact": "incorrect_product_name",
        }
    if len(diagnosis) == 2:
        diagnosis.update({
            "stage": "user_review",
            "reason_code": "USER_REPORTED_RESULT_MISMATCH",
            "impact": "manual_review_required",
        })
    return diagnosis


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_source_pdf(record, target_dir, package_dir):
    source = Path(str(record.get("full_path") or ""))
    result = {
        "status": "PARTIAL_SOURCE_PDF_MISSING",
        "original_name": source.name or str(record.get("filename") or ""),
        "relative_path": "",
        "size": 0,
        "sha256": "",
        "large_file_notice": False,
        "error": "SOURCE_PDF_NOT_FOUND",
    }
    if not source.is_file() or source.suffix.lower() != ".pdf":
        return result
    try:
        size = source.stat().st_size
        result["size"] = size
        if size > SOURCE_PDF_HARD_LIMIT_BYTES:
            result.update(status="TOO_LARGE", error="SOURCE_PDF_EXCEEDS_100_MIB")
            return result
        source_dir = target_dir / "source"
        source_dir.mkdir(exist_ok=True)
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", source.name).strip(" .") or "source.pdf"
        destination = source_dir / safe_name
        shutil.copyfile(source, destination)
        source_hash = _sha256_file(source)
        destination_hash = _sha256_file(destination)
        if source_hash != destination_hash or destination.stat().st_size != size:
            destination.unlink(missing_ok=True)
            raise OSError("복사본 바이트 검증 실패")
        result.update(
            status="FULL",
            relative_path=destination.relative_to(package_dir).as_posix(),
            sha256=destination_hash,
            large_file_notice=size > SOURCE_PDF_NOTICE_BYTES,
            error="",
        )
    except OSError as exc:
        result.update(status="COPY_FAILED", relative_path="", sha256="", error=str(exc))
    return result


def _metric_counts(diagnostic):
    result = diagnostic.get("result") if isinstance(diagnostic.get("result"), dict) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    ai = int(metrics.get("ai_text_calls", 0) or 0) + int(metrics.get("ai_image_calls", 0) or 0)
    ocr = int(metrics.get("recon_ocr_calls", 0) or 0) + int(metrics.get("precision_ocr_calls", 0) or 0)
    if not ai:
        ai = sum(1 for event in diagnostic.get("engine_results", []) if str(event.get("event_type", "")).startswith("ai.call.start"))
    if not ocr:
        ocr = sum(1 for event in diagnostic.get("engine_results", []) if str(event.get("event_type", "")).startswith("ocr.") and str(event.get("event_type", "")).endswith("start"))
    return ai, ocr


def _selected_image_paths(diagnostic, images_dir, limit):
    root = Path(images_dir).resolve()
    if not root.is_dir():
        return []
    declared = []
    for item in diagnostic.get("images", []) if isinstance(diagnostic.get("images"), list) else []:
        relative = item.get("path") if isinstance(item, dict) else ""
        if relative:
            declared.append(Path(relative).name)
    names = declared or [item.name for item in root.iterdir() if item.is_file()]
    unique = []
    for name in names:
        lower = name.lower()
        if name in unique or "ai_input" in lower or "product_ai" in lower:
            continue
        if Path(name).suffix.lower() not in {".png", ".webp", ".jpg", ".jpeg"}:
            continue
        unique.append(name)
    unique.sort(key=lambda name: (next((i for i, token in enumerate(IMAGE_PRIORITY) if token in name.lower()), 99), name.lower()))
    selected = []
    for name in unique:
        candidate = (root / name).resolve()
        if candidate.parent != root or not candidate.is_file() or candidate.is_symlink():
            continue
        selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _manifest_entries(package_dir, trace_by_relative):
    entries = []
    for path in sorted(Path(package_dir).rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        relative = path.relative_to(package_dir).as_posix()
        payload = path.read_bytes()
        entries.append({
            "relative_path": relative,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "kind": "image" if path.suffix.lower() in {".png", ".webp", ".jpg", ".jpeg"} else path.suffix.lower().lstrip(".") or "file",
            "file_trace_id": trace_by_relative.get(relative, ""),
        })
    return entries


def build_share_package(records, repo_root, output_root=None, max_images_per_file=MAX_IMAGES_PER_FILE,
                        max_total_bytes=MAX_SHARE_BYTES):
    selected = [record for record in records if (record.get("user_review") or {}).get("user_marked_error")]
    if not selected:
        raise DiagnosticShareError("공유할 오류 파일을 선택해 주세요.")
    run_ids = {str((record.get("diagnostics") or {}).get("run_id") or "") for record in selected}
    run_ids.discard("")
    if len(run_ids) != 1:
        raise DiagnosticShareError("한 번에 동일한 실행(run_id)의 파일만 공유할 수 있습니다.")
    run_id = next(iter(run_ids))
    root = Path(repo_root).resolve()
    export_root = Path(output_root or (root / "diagnostic_exports")).resolve()
    export_root.mkdir(parents=True, exist_ok=True)
    package_dir = export_root / run_id
    version = 2
    while package_dir.exists():
        package_dir = export_root / f"{run_id}-v{version}"
        version += 1
    package_dir.mkdir(parents=True)
    files_dir = package_dir / "files"
    files_dir.mkdir()

    total_bytes = 0
    summary_files = []
    trace_by_relative = {}
    first_diagnostics = selected[0].get("diagnostics") if isinstance(selected[0].get("diagnostics"), dict) else {}
    source_commit = str(selected[0].get("source_commit") or first_diagnostics.get("source_commit") or "")
    source_branch = str(selected[0].get("source_branch") or first_diagnostics.get("source_branch") or "")
    diagnostic_mode = str((selected[0].get("diagnostics") or {}).get("trace_context", {}).get("mode") or "SUMMARY")

    for record in selected:
        diagnostics = record.get("diagnostics") if isinstance(record.get("diagnostics"), dict) else {}
        trace_id = str(diagnostics.get("file_trace_id") or "")
        diagnostic_json_path = Path(str(diagnostics.get("diagnostic_json") or ""))
        diagnostic_md_path = Path(str(diagnostics.get("diagnostic_markdown") or ""))
        if not trace_id or not diagnostic_json_path.is_file() or not diagnostic_md_path.is_file():
            raise DiagnosticShareError(f"진단 파일이 없어 공유할 수 없습니다: {record.get('filename', trace_id)}")
        diagnostic = _read_json(diagnostic_json_path)
        portable_diagnostic = _sanitize_json(diagnostic, root)
        target_name = safe_export_name(record.get("filename"), trace_id)
        target_dir = files_dir / target_name
        target_dir.mkdir()
        target_json = target_dir / "diagnostic.json"
        target_md = target_dir / "diagnostic.md"
        _write_json(target_json, portable_diagnostic)
        target_md.write_text(_portable_text(diagnostic_md_path.read_text(encoding="utf-8", errors="replace"), root), encoding="utf-8")

        user_review = {
            "file_name": str(record.get("filename") or ""),
            "file_trace_id": trace_id,
            "system_status": str(record.get("status") or ""),
            "user_marked_error": True,
            "auto_selected": bool((record.get("user_review") or {}).get("auto_selected")),
            "error_types": list((record.get("user_review") or {}).get("error_types") or []),
            "user_note": str((record.get("user_review") or {}).get("user_note") or ""),
            "shared_at": _utc_now(),
        }
        diagnosis = _user_review_diagnosis(record, diagnostic, user_review)
        user_review["diagnosis"] = diagnosis
        _write_json(target_dir / "user_review.json", _sanitize_json(user_review, root))

        source_pdf = _copy_source_pdf(record, target_dir, package_dir)

        image_relatives = []
        images_target = target_dir / "images"
        for source_image in _selected_image_paths(diagnostic, diagnostics.get("diagnostic_images_dir", ""), max_images_per_file):
            size = source_image.stat().st_size
            if total_bytes + size > max_total_bytes:
                break
            images_target.mkdir(exist_ok=True)
            destination = images_target / source_image.name
            shutil.copy2(source_image, destination)
            total_bytes += size
            image_relatives.append(destination.relative_to(package_dir).as_posix())

        stage, reason, fallback = _first_failure(diagnostic)
        ai_calls, ocr_calls = _metric_counts(diagnostic)
        final_result = diagnostic.get("result") if isinstance(diagnostic.get("result"), dict) else {}
        components = str(record.get("raw_content") or final_result.get("구성성분") or "")
        summary_files.append({
            "file_name": str(record.get("filename") or ""),
            "file_trace_id": trace_id,
            "system_status": str(final_result.get("status") or record.get("status") or ""),
            "user_marked_error": True,
            "error_types": user_review["error_types"],
            "user_note": user_review["user_note"],
            "product_name": str(record.get("product_name") or final_result.get("제품명") or ""),
            "component_count": len([part for part in components.split(";") if part.strip()]),
            "diagnostic_path": target_md.relative_to(package_dir).as_posix(),
            "image_paths": image_relatives,
            "first_failure_stage": stage,
            "direct_failure_reason": reason,
            "fallback_path": fallback,
            "ai_calls": ai_calls,
            "ocr_calls": ocr_calls,
            "diagnosis": diagnosis,
            "source_pdf": source_pdf,
        })
        for path in target_dir.rglob("*"):
            if path.is_file():
                trace_by_relative[path.relative_to(package_dir).as_posix()] = trace_id

    run_summary_path = root / "logs" / "runs" / run_id / "summary.json"
    run_summary_source = _read_json(run_summary_path, {})
    total_files = int(run_summary_source.get("total_pdf", len(selected)) or len(selected))
    automatic_failures = sum(int(run_summary_source.get(key, 0) or 0) for key in ("failed_count", "timeout_count", "partial_count", "cancelled_count"))
    summary = {
        "run_id": run_id,
        "source_branch": source_branch,
        "source_commit": source_commit,
        "diagnostic_mode": diagnostic_mode,
        "total_files": total_files,
        "normal_files": max(0, total_files - automatic_failures),
        "automatic_failure_files": automatic_failures,
        "selected_error_files": len(summary_files),
        "started_at": run_summary_source.get("started_at"),
        "finished_at": run_summary_source.get("finished_at"),
        "files": summary_files,
        "images_excluded_by_policy": True,
        "original_pdfs_included": any(item["source_pdf"]["status"] == "FULL" for item in summary_files),
        "source_pdf_counts": {
            status: sum(item["source_pdf"]["status"] == status for item in summary_files)
            for status in ("FULL", "PARTIAL_SOURCE_PDF_MISSING", "TOO_LARGE", "COPY_FAILED")
        },
        "large_source_pdf_count": sum(bool(item["source_pdf"]["large_file_notice"]) for item in summary_files),
    }
    _write_json(package_dir / "run_summary.json", _sanitize_json(summary, root))

    lines = ["# MSDS Diagnostic Run Summary", "", "## 실행 정보", "",
             f"- Run ID: `{run_id}`", f"- 실행 시각: {_utc_now()}",
             f"- 소스 브랜치: `{source_branch or '확인되지 않음'}`",
             f"- 소스 커밋: `{source_commit or '확인되지 않음'}`",
             f"- 진단 모드: `{diagnostic_mode}`", f"- 전체 처리 파일: {total_files}",
             f"- 사용자 선택 오류 파일: {len(summary_files)}", f"- 자동 실패 파일: {automatic_failures}",
             "", "## 사용자 선택 오류", ""]
    for index, item in enumerate(summary_files, 1):
        lines.extend([
            f"### {index}. {item['file_name']}", "",
            f"- 사용자 오류 유형: {', '.join(item['error_types']) or '기타'}",
            f"- 사용자 메모: {item['user_note'] or '없음'}",
            f"- 자동 처리 상태: {item['system_status'] or '확인되지 않음'}",
            f"- 제품명: {item['product_name'] or '미추출'}",
            f"- 최종 성분 수: {item['component_count']}",
            f"- 최초 실패 지점: {item['first_failure_stage']}",
            f"- 직접 실패 원인: {item['direct_failure_reason']}",
            f"- 사용자 검토 원인 코드: {item['diagnosis'].get('reason_code', '미확인')}",
            f"- 후속 우회 경로: {item['fallback_path']}",
            f"- AI 호출 수: {item['ai_calls']}", f"- OCR 호출 수: {item['ocr_calls']}",
            f"- 상세 진단: [{item['diagnostic_path']}]({item['diagnostic_path']})",
            f"- 이미지 폴더: `{Path(item['diagnostic_path']).parent.as_posix()}/images/`",
            f"- 원본 PDF 상태: `{item['source_pdf']['status']}`",
            f"- 원본 PDF 경로: `{item['source_pdf']['relative_path'] or '제외됨'}`",
            f"- 원본 PDF 제외/실패 사유: {item['source_pdf']['error'] or '없음'}",
            "",
        ])
    (package_dir / "run_summary.md").write_text(_portable_text("\n".join(lines), root) + "\n", encoding="utf-8")
    trace_by_relative["run_summary.md"] = ""
    trace_by_relative["run_summary.json"] = ""
    _write_json(package_dir / "manifest.json", {
        "run_id": run_id,
        "files": _manifest_entries(package_dir, trace_by_relative),
        "source_pdfs": [dict(item["source_pdf"], file_trace_id=item["file_trace_id"]) for item in summary_files],
    })
    assert_share_is_safe(package_dir)
    return package_dir, summary


def assert_share_is_safe(package_dir):
    root = Path(package_dir).resolve()
    total = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in {"config.json", "smu_cache.json", "msds_cache_registry.json"}:
            raise DiagnosticShareError(f"공유 금지 파일이 포함되었습니다: {path.name}")
        if path.suffix.lower() == ".pdf":
            relative = path.relative_to(root)
            if len(relative.parts) < 4 or relative.parts[-2] != "source" or path.stat().st_size > SOURCE_PDF_HARD_LIMIT_BYTES:
                raise DiagnosticShareError(f"허용되지 않은 PDF가 포함되었습니다: {path.name}")
        total += path.stat().st_size
        if path.suffix.lower() in {".json", ".md", ".jsonl", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(pattern.search(text) for pattern in SECRET_PATTERNS):
                raise DiagnosticShareError(f"민감정보 패턴이 발견되어 공유를 중단했습니다: {path.name}")
    if total > MAX_PACKAGE_BYTES:
        raise DiagnosticShareError("공유 패키지가 안전 한도 500MiB를 초과했습니다.")
    return total


def _git(repo_root, *args, check=True, timeout=60):
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    completed = subprocess.run(
        ["git", *args], cwd=str(repo_root), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, env=environment,
    )
    if check and completed.returncode:
        raise DiagnosticShareError((completed.stderr or completed.stdout or "Git 명령 실패").strip())
    return completed


def _branch_exists(repo_root, branch, remote="origin"):
    local = _git(repo_root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
    if local.returncode == 0:
        return True
    remote_result = _git(repo_root, "ls-remote", "--heads", remote, branch, check=False, timeout=30)
    if remote_result.returncode != 0:
        raise DiagnosticShareError((remote_result.stderr or "원격 브랜치 확인 실패").strip())
    return bool(remote_result.stdout.strip())


def publish_share_package(repo_root, package_dir, source_commit, run_id, remote="origin"):
    repo = Path(repo_root).resolve()
    package = Path(package_dir).resolve()
    if not (repo / ".git").exists():
        raise DiagnosticShareError("현재 폴더가 예상 Git 저장소가 아닙니다.")
    remote_url = _git(repo, "remote", "get-url", remote).stdout.strip()
    if EXPECTED_REPOSITORY.lower() not in remote_url.replace(".git", "").lower():
        raise DiagnosticShareError(f"예상 저장소가 아니므로 푸시하지 않습니다: {remote_url}")
    source_commit = str(source_commit or "").strip()
    if not source_commit:
        raise DiagnosticShareError("실행 소스 커밋을 확인할 수 없습니다.")
    _git(repo, "cat-file", "-e", f"{source_commit}^{{commit}}")
    before_status = _git(repo, "status", "--porcelain=v1", "-z").stdout
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    short_run = re.sub(r"[^A-Za-z0-9]", "", run_id)[-8:] or hashlib.sha256(run_id.encode()).hexdigest()[:8]
    base_branch = f"diagnostics/run-{stamp}-{short_run}"
    branch = base_branch
    version = 2
    while _branch_exists(repo, branch, remote):
        branch = f"{base_branch}-{version}"
        version += 1

    worktree = Path(tempfile.mkdtemp(prefix="msds-diagnostic-share-"))
    worktree_added = False
    try:
        _git(repo, "worktree", "add", "-b", branch, str(worktree), source_commit, timeout=120)
        worktree_added = True
        relative_target = Path("diagnostic_exports") / package.name
        target = worktree / relative_target
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(package, target)
        _git(worktree, "add", "-f", "--", relative_target.as_posix())
        _git(worktree, "commit", "-m", f"diagnostics: add selected MSDS run {run_id}")
        commit_sha = _git(worktree, "rev-parse", "HEAD").stdout.strip()
        _git(worktree, "push", remote, f"HEAD:refs/heads/{branch}", timeout=180)
        after_status = _git(repo, "status", "--porcelain=v1", "-z").stdout
        if before_status != after_status:
            raise DiagnosticShareError("Git 공유 후 원래 작업 트리 상태가 달라져 안전 검증에 실패했습니다.")
        return {"branch_name": branch, "commit_sha": commit_sha, "remote_url": remote_url}
    finally:
        if worktree_added:
            _git(repo, "worktree", "remove", "--force", str(worktree), check=False, timeout=120)
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)


def append_share_history(repo_root, entry):
    history_path = Path(repo_root) / "logs" / "diagnostic_share_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"created_at": _utc_now(), **entry}
    with history_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return history_path


def duplicate_share_exists(repo_root, run_id, trace_ids):
    history_path = Path(repo_root) / "logs" / "diagnostic_share_history.jsonl"
    wanted = sorted(str(item) for item in trace_ids)
    try:
        for line in history_path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item.get("run_id") == run_id and sorted(item.get("selected_file_trace_ids") or []) == wanted and item.get("push_status") == "success":
                return True
    except (OSError, ValueError, TypeError):
        return False
    return False


def latest_successful_share(repo_root):
    history_path = Path(repo_root) / "logs" / "diagnostic_share_history.jsonl"
    try:
        entries = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError, TypeError):
        return {}
    return next((item for item in reversed(entries) if item.get("push_status") == "success"), {})
