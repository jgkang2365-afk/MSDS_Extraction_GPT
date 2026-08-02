import copy
import json
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from datetime import date
from threading import RLock

import requests
from api_config import load_api_settings

try:
    from diagnostic_trace import get_tracer
except Exception:  # 관측성 배포 전에도 API 동작을 보존한다.
    def get_tracer():
        return None


_API_SETTINGS = load_api_settings()
SERVICE_KEY = _API_SETTINGS.kosha_service_key
BASE_URL = _API_SETTINGS.kosha_base_url
_CACHE_MISS = object()


def _trace_kosha(name, **details):
    """URL 파라미터·서비스 키를 남기지 않는 fail-soft KOSHA 계측 경계."""
    try:
        tracer = get_tracer()
        if tracer:
            tracer.event(name, stage_id="kosha", **details)
    except Exception:
        pass


def _env_float(name, default):
    try:
        return max(0.0, float(os.getenv(name, default)))
    except (TypeError, ValueError):
        return float(default)


def _env_int(name, default):
    try:
        return max(0, int(os.getenv(name, default)))
    except (TypeError, ValueError):
        return int(default)


class KoshaRequestBudgetExceeded(RuntimeError):
    """로컬 안전 예산을 모두 사용해 추가 공단 요청을 중단한 상태."""


class _TransientKoshaError(RuntimeError):
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


class KoshaAPIClient:
    CACHE_VERSION = 1

    def __init__(
        self,
        cache_path=None,
        session=None,
        request_interval=None,
        cache_ttl=None,
        negative_cache_ttl=None,
        daily_request_budget=None,
    ):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_path = cache_path or os.getenv(
            "KOSHA_CACHE_PATH",
            os.path.join(base_dir, "kosha_api_cache.json"),
        )
        self.usage_path = f"{self.cache_path}.usage"
        self.session = session or requests.Session()
        self.lock = RLock()
        self.cache = {}
        self.detail_cache = {}
        self.request_interval = (
            _env_float("KOSHA_REQUEST_INTERVAL_SECONDS", 0.5)
            if request_interval is None
            else max(0.0, float(request_interval))
        )
        self.cache_ttl = (
            _env_float("KOSHA_CACHE_TTL_SECONDS", 86400)
            if cache_ttl is None
            else max(0.0, float(cache_ttl))
        )
        self.negative_cache_ttl = (
            _env_float("KOSHA_NEGATIVE_CACHE_TTL_SECONDS", 3600)
            if negative_cache_ttl is None
            else max(0.0, float(negative_cache_ttl))
        )
        self.daily_request_budget = (
            _env_int("KOSHA_DAILY_REQUEST_BUDGET", 800)
            if daily_request_budget is None
            else max(0, int(daily_request_budget))
        )
        self._last_request_started = 0.0
        self._persistent_entries = {}
        self._usage_date = date.today().isoformat()
        self._usage_count = 0
        self._metrics = {
            "network_requests": 0,
            "persistent_cache_hits": 0,
            "negative_cache_hits": 0,
            "memory_cache_hits": 0,
            "retries": 0,
        }
        self._load_persistent_cache()
        self._load_usage()

    def _atomic_write_json(self, path, payload):
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        temp_path = f"{path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _load_persistent_cache(self):
        if not os.path.exists(self.cache_path):
            return
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("version") == self.CACHE_VERSION:
                entries = payload.get("entries", {})
                if isinstance(entries, dict):
                    self._persistent_entries = entries
        except (OSError, ValueError, TypeError):
            self._persistent_entries = {}

    def _save_persistent_cache(self):
        self._atomic_write_json(
            self.cache_path,
            {
                "version": self.CACHE_VERSION,
                "saved_at": time.time(),
                "entries": self._persistent_entries,
            },
        )

    def _load_usage(self):
        if not os.path.exists(self.usage_path):
            return
        try:
            with open(self.usage_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("date") == self._usage_date:
                self._usage_count = max(0, int(payload.get("requests", 0)))
        except (OSError, ValueError, TypeError):
            self._usage_count = 0

    def _save_usage(self):
        self._atomic_write_json(
            self.usage_path,
            {"date": self._usage_date, "requests": self._usage_count},
        )

    def _refresh_usage_day(self):
        today = date.today().isoformat()
        if today != self._usage_date:
            self._usage_date = today
            self._usage_count = 0
            self._save_usage()

    def _reserve_request(self):
        self._refresh_usage_day()
        if self.daily_request_budget and self._usage_count >= self.daily_request_budget:
            _trace_kosha(
                "kosha_budget_exhausted",
                level="warning",
                daily_budget=self.daily_request_budget,
                daily_requests=self._usage_count,
            )
            raise KoshaRequestBudgetExceeded(
                f"KOSHA 일일 안전 호출 예산({self.daily_request_budget}회)을 모두 사용했습니다."
            )
        self._usage_count += 1
        self._metrics["network_requests"] += 1
        self._save_usage()
        _trace_kosha(
            "kosha_request_reserved",
            daily_budget=self.daily_request_budget,
            daily_requests=self._usage_count,
        )

    def _paced_get(self, url, params):
        with self.lock:
            elapsed = time.monotonic() - self._last_request_started
            remaining = self.request_interval - elapsed
            if remaining > 0:
                jitter = min(0.1, self.request_interval * 0.2)
                time.sleep(remaining + random.uniform(0.0, jitter))
            self._reserve_request()
            self._last_request_started = time.monotonic()
            _trace_kosha("kosha_network_request", operation=url.rsplit("/", 1)[-1])
            return self.session.get(url, params=params, timeout=10)

    @staticmethod
    def _retry_after_seconds(response):
        value = response.headers.get("Retry-After") if getattr(response, "headers", None) else None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return None

    def _request_xml(self, operation, params):
        if not BASE_URL:
            raise RuntimeError("KOSHA BASE_URL이 설정되지 않았습니다.")

        url = f"{BASE_URL.rstrip('/')}/{operation}"
        for attempt in range(3):
            try:
                response = self._paced_get(url, params)
                status_code = int(getattr(response, "status_code", 200))
                if status_code == 429 or 500 <= status_code < 600:
                    raise _TransientKoshaError(
                        f"KOSHA 일시 장애 HTTP {status_code}",
                        retry_after=self._retry_after_seconds(response),
                    )
                response.raise_for_status()
                return ET.fromstring(response.content)
            except KoshaRequestBudgetExceeded:
                raise
            except _TransientKoshaError as exc:
                if attempt >= 2:
                    _trace_kosha("kosha_request_failed", level="warning", operation=operation, attempt=attempt + 1)
                    return None
                self._metrics["retries"] += 1
                delay = exc.retry_after if exc.retry_after is not None else 2 ** attempt
                _trace_kosha("kosha_retry", level="warning", operation=operation, attempt=attempt + 1, retry_delay=delay)
                time.sleep(max(0.5, delay))
            except (requests.Timeout, requests.ConnectionError, ET.ParseError):
                if attempt >= 2:
                    _trace_kosha("kosha_request_failed", level="warning", operation=operation, attempt=attempt + 1)
                    return None
                self._metrics["retries"] += 1
                _trace_kosha("kosha_retry", level="warning", operation=operation, attempt=attempt + 1, retry_delay=2 ** attempt)
                time.sleep(2 ** attempt)
            except requests.RequestException:
                # 인증 실패·잘못된 요청 등 일반 4xx는 반복해도 회복되지 않는다.
                _trace_kosha("kosha_request_rejected", level="warning", operation=operation)
                return None
        return None

    def _get_cached_result(self, key):
        entry = self._persistent_entries.get(key)
        if not isinstance(entry, dict):
            _trace_kosha("kosha_cache_miss", cache="persistent")
            return _CACHE_MISS
        cached_at = entry.get("cached_at")
        try:
            age = max(0.0, time.time() - float(cached_at))
        except (TypeError, ValueError):
            return _CACHE_MISS
        value = entry.get("value")
        ttl = self.negative_cache_ttl if value is None else self.cache_ttl
        if ttl <= 0 or age > ttl:
            self._persistent_entries.pop(key, None)
            _trace_kosha("kosha_cache_miss", cache="persistent", reason="expired")
            return _CACHE_MISS
        self._metrics["persistent_cache_hits"] += 1
        if value is None:
            self._metrics["negative_cache_hits"] += 1
            _trace_kosha("kosha_cache_hit", cache="negative")
        else:
            _trace_kosha("kosha_cache_hit", cache="persistent")
        return copy.deepcopy(value)

    def _set_cached_result(self, key, value):
        self._persistent_entries[key] = {
            "cached_at": time.time(),
            "value": copy.deepcopy(value),
        }
        self._save_persistent_cache()

    def get_metrics(self):
        return {
            **self._metrics,
            "daily_requests": self._usage_count,
            "daily_budget": self.daily_request_budget,
            "budget_remaining": max(0, self.daily_request_budget - self._usage_count),
        }

    def get_chem_id(self, cas_no: str):
        """CAS 번호로 chemId 및 국문 화학물질명을 조회한다."""
        if not cas_no:
            return None, None
        if cas_no in self.cache:
            self._metrics["memory_cache_hits"] += 1
            _trace_kosha("kosha_cache_hit", cache="memory")
            return self.cache[cas_no]

        root = self._request_xml(
            "chemlist",
            {"serviceKey": SERVICE_KEY, "searchWrd": cas_no, "searchCnd": 1},
        )
        if root is None or root.findtext("./header/resultCode") != "00":
            return None, None

        item = root.find("./body/items/item")
        if item is None:
            return None, None

        result = (item.findtext("chemId"), item.findtext("chemNameKor"))
        self.cache[cas_no] = result
        return result

    def _get_detail_items(self, chem_id: str, operation: str):
        cache_key = (chem_id, operation)
        if cache_key in self.detail_cache:
            self._metrics["memory_cache_hits"] += 1
            _trace_kosha("kosha_cache_hit", cache="memory")
            return self.detail_cache[cache_key]

        root = self._request_xml(
            operation,
            {"serviceKey": SERVICE_KEY, "chemId": chem_id},
        )
        if root is None or root.findtext("./header/resultCode") != "00":
            return {}

        details = {}
        for item in root.findall("./body/items/item"):
            name = item.findtext("msdsItemNameKor")
            if name:
                details[name] = item.findtext("itemDetail")
        self.detail_cache[cache_key] = details
        return details

    def get_item_detail(self, chem_id: str, operation: str, target_item_name: str):
        """상세 정보 API 응답에서 특정 항목을 추출한다."""
        for name, detail in self._get_detail_items(chem_id, operation).items():
            if target_item_name in name:
                return detail
        return None

    def get_full_substance_info(self, cas_no: str, full=True):
        """제품명, 노출기준, 산안법·화관법 정보를 반환한다."""
        cache_key = f"{'full' if full else 'summary'}:{cas_no}"
        cached = self._get_cached_result(cache_key)
        if cached is not _CACHE_MISS:
            return cached

        chem_id, chem_name_kor = self.get_chem_id(cas_no)
        if not chem_id:
            self._set_cached_result(cache_key, None)
            return None

        # 가로형 검증은 물질목록의 국문명으로 충분하다. 상세 1항 호출은 full=True만 수행한다.
        product_name = chem_name_kor or "제품명 확인 불가"
        if full:
            product_name = (
                self.get_item_detail(chem_id, "chemdetail01", "제품명")
                or product_name
            )

        if product_name and re.search(r"[가-힣]", product_name):
            product_name = product_name.replace(" ", "")

        exposure = {"twa_ppm": "-", "twa_mg": "-", "stel_ppm": "-", "stel_mg": "-"}
        if full:
            exp_text = self.get_item_detail(chem_id, "chemdetail08", "국내규정") or ""
            twa_ppm = re.search(r"TWA\s*[:：]?\s*(\d+(?:\.\d+)?)\s*ppm", exp_text, re.I)
            twa_mg = re.search(r"TWA\s*[:：]?\s*(\d+(?:\.\d+)?)\s*㎎/㎥", exp_text, re.I)
            stel_ppm = re.search(r"STEL\s*[:：]?\s*(\d+(?:\.\d+)?)\s*ppm", exp_text, re.I)
            stel_mg = re.search(r"STEL\s*[:：]?\s*(\d+(?:\.\d+)?)\s*㎎/㎥", exp_text, re.I)
            exposure = {
                "twa_ppm": twa_ppm.group(1) if twa_ppm else "-",
                "twa_mg": twa_mg.group(1) if twa_mg else "-",
                "stel_ppm": stel_ppm.group(1) if stel_ppm else "-",
                "stel_mg": stel_mg.group(1) if stel_mg else "-",
            }

        osh_info = {
            k: False
            for k in [
                "is_measured",
                "is_special",
                "is_managed",
                "is_special_mgmt",
                "is_permit",
                "is_prohibited",
            ]
        }
        osh_info["raw_text"] = ""
        cca_info = {
            k: False
            for k in ["acute", "chronic", "ecology", "accident", "prohibited", "restricted"]
        }

        # chemdetail15는 한 번만 받고 산안법·화관법 항목을 같은 응답에서 분리한다.
        regulation_items = self._get_detail_items(chem_id, "chemdetail15")
        osh_text = next(
            (
                detail
                for name, detail in regulation_items.items()
                if "산업안전보건법에 의한 규제" in name
            ),
            None,
        )
        if osh_text:
            osh_info = {
                "is_measured": "작업환경측정대상물질" in osh_text,
                "is_special": "특수건강진단대상물질" in osh_text,
                "is_managed": "관리대상유해물질" in osh_text,
                "is_special_mgmt": "특별관리물질" in osh_text,
                "is_permit": "허가대상물질" in osh_text,
                "is_prohibited": "금지물질" in osh_text,
                "raw_text": osh_text,
            }

        if full:
            cca_text = next(
                (
                    detail
                    for name, detail in regulation_items.items()
                    if "화학물질관리법에 의한 규제" in name
                ),
                None,
            )
            if cca_text:
                cca_info = {
                    "acute": "유독물질" in cca_text,
                    "chronic": "관찰물질" in cca_text,
                    "ecology": "",
                    "accident": "사고대비물질" in cca_text,
                    "prohibited": "금지물질" in cca_text,
                    "restricted": "제한물질" in cca_text,
                }

        result = {
            "chem_id": chem_id,
            "product_name": product_name,
            "cas_no": cas_no,
            "exposure": exposure,
            "osh": osh_info,
            "cca": cca_info,
        }
        self._set_cached_result(cache_key, result)
        return copy.deepcopy(result)

    def get_regulation_info(self, cas_no: str, full=False):
        info = self.get_full_substance_info(cas_no, full=full)
        if not info:
            return None, cas_no, False, False, False, False
        return (
            info["product_name"],
            info["cas_no"],
            info["osh"]["is_measured"],
            info["osh"]["is_special"],
            info["osh"]["is_special_mgmt"],
            info["osh"]["is_permit"],
        )

    def fetch_msds_info(self, cas_no: str):
        info = self.get_full_substance_info(cas_no, full=False)
        if not info:
            return None
        product_name = info["product_name"]
        is_work_env = info["osh"]["is_measured"]
        is_special_health = info["osh"]["is_special"]
        if is_special_health and not is_work_env:
            return f"[특검]{product_name}({cas_no})"
        if is_work_env or is_special_health:
            return f"{product_name}({cas_no})"
        return None


if __name__ == "__main__":
    client = KoshaAPIClient()
    test_cas = "64-17-5"
    print(f"CAS {test_cas} 결과: {client.fetch_msds_info(test_cas)}")
