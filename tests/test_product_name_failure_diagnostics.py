import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import msds_engine_v6 as engine_module
import run_production_race as race
from product_name_diagnostics import (
    AIProviderCallError,
    PRODUCT_NAME_FAILURE_CODES,
    classify_product_failure,
    classify_product_response,
    provider_failure_reason,
    sanitize_diagnostic_message,
)


def response(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def metric(reason="", stage="primary", **extra):
    return {
        "purpose": "product_name", "stage": stage, "reason_code": reason,
        "provider": extra.pop("provider", "novita"), **extra,
    }


class ProductResponseClassificationTests(unittest.TestCase):
    def test_empty_response(self):
        self.assertEqual(classify_product_response("", None)[1], "PRODUCT_NAME_EMPTY_RESPONSE")

    def test_plain_product_name(self):
        self.assertEqual(classify_product_response("Clean Product", None), ("Clean Product", ""))

    def test_json_product_name(self):
        self.assertEqual(classify_product_response("{}", {"product_name": "P"}), ("P", ""))

    def test_korean_json_product_name(self):
        self.assertEqual(classify_product_response("{}", {"제품명": "제품"}), ("제품", ""))

    def test_json_empty_product_name(self):
        self.assertEqual(classify_product_response("{}", {"product_name": ""})[1], "PRODUCT_NAME_RESULT_EMPTY")

    def test_schema_mismatch(self):
        self.assertEqual(classify_product_response("{}", {"name": "P"})[1], "PRODUCT_NAME_RESPONSE_SCHEMA_MISMATCH")

    def test_non_dict_schema_mismatch(self):
        self.assertEqual(classify_product_response("[]", ["P"])[1], "PRODUCT_NAME_RESPONSE_SCHEMA_MISMATCH")

    def test_long_unparsed_response(self):
        self.assertEqual(classify_product_response("x" * 100, None)[1], "PRODUCT_NAME_RESPONSE_PARSE_FAILED")

    def test_cas_like_plain_response_is_not_product(self):
        self.assertEqual(classify_product_response("64-17-5", None)[1], "PRODUCT_NAME_RESPONSE_PARSE_FAILED")


class ProductFailureClassificationTests(unittest.TestCase):
    def test_rate_limit(self):
        self.assertEqual(provider_failure_reason(AIProviderCallError("rate_limited", http_status=429)), "PRODUCT_NAME_RATE_LIMITED")

    def test_timeout(self):
        self.assertEqual(provider_failure_reason(AIProviderCallError("timeout")), "PRODUCT_NAME_TIMEOUT")

    def test_blocked(self):
        self.assertEqual(provider_failure_reason(AIProviderCallError("call_blocked")), "PRODUCT_NAME_CALL_BLOCKED")

    def test_provider_error(self):
        self.assertEqual(provider_failure_reason(RuntimeError("offline")), "PRODUCT_NAME_PROVIDER_ERROR")

    def test_evidence_absent_is_rejected(self):
        result = classify_product_failure([], evidence_present=False)
        self.assertEqual(result["reason_code"], "PRODUCT_NAME_EVIDENCE_REJECTED")

    def test_no_provider_metric_is_blocked(self):
        result = classify_product_failure([], evidence_present=True)
        self.assertEqual(result["reason_code"], "PRODUCT_NAME_CALL_BLOCKED")

    def test_last_provider_reason_is_decisive(self):
        result = classify_product_failure([
            metric("PRODUCT_NAME_PROVIDER_ERROR"),
            metric("PRODUCT_NAME_TIMEOUT", stage="fallback"),
        ], evidence_present=True)
        self.assertEqual(result["reason_code"], "PRODUCT_NAME_TIMEOUT")

    def test_all_failed_aggregate(self):
        result = classify_product_failure([metric("PRODUCT_NAME_PROVIDER_ERROR")], evidence_present=True)
        self.assertEqual(result["aggregate_reason_code"], "PRODUCT_NAME_ALL_PROVIDERS_FAILED")

    def test_failure_codes_are_closed_set(self):
        self.assertIn("PRODUCT_NAME_RESULT_BLACKLISTED", PRODUCT_NAME_FAILURE_CODES)
        self.assertNotIn("CASE_SPECIFIC_FAILURE", PRODUCT_NAME_FAILURE_CODES)


class ProductDiagnosticSanitizationTests(unittest.TestCase):
    def test_bearer_token_redacted(self):
        self.assertNotIn("abc123", sanitize_diagnostic_message("Authorization: Bearer abc123"))

    def test_api_key_redacted(self):
        self.assertNotIn("secret-value", sanitize_diagnostic_message("api_key=secret-value"))

    def test_google_key_redacted(self):
        value = "AIza" + "A" * 24
        self.assertNotIn(value, sanitize_diagnostic_message(value))

    def test_message_is_bounded(self):
        self.assertEqual(len(sanitize_diagnostic_message("x" * 500)), 300)


class ProductProviderRoutingTests(unittest.TestCase):
    def setUp(self):
        self.engine = engine_module.MSDSEngineV6()

    @staticmethod
    def _settings(*, novita=True, vertex=True):
        return SimpleNamespace(
            novita_api_key="test" if novita else "",
            vertex_credential_path=Path("vertex.json") if vertex else None,
            vertex_error_code="",
            require_vertex=lambda: (Path("vertex.json"), "test-project", "us-central1"),
        )

    def test_primary_success_has_no_fallback(self):
        with patch.object(
            engine_module, "load_api_settings", return_value=self._settings()
        ), patch.object(self.engine, "call_deepseek_with_retry", return_value=response("Primary")), patch.object(
            self.engine, "call_vertex_gemini_with_retry"
        ) as fallback:
            self.engine.call_llm_router({}, purpose="product_name")
        fallback.assert_not_called()
        self.assertEqual(len(self.engine._ai_call_metrics), 1)

    def test_vertex_dependency_missing_is_not_authentication_failure(self):
        missing = engine_module.APIConfigError("VERTEX_DEPENDENCY_MISSING", "google-genai")
        with patch.object(
            engine_module, "load_api_settings", return_value=self._settings(novita=False)
        ), patch.object(engine_module, "vertex_dependency_preflight", side_effect=missing):
            with self.assertRaises(AIProviderCallError) as raised:
                self.engine.call_vertex_gemini_with_retry({}, diagnostic_fail_fast=True)
        self.assertEqual(raised.exception.error_code, "VERTEX_DEPENDENCY_MISSING")

    def test_primary_provider_failure_uses_one_fallback(self):
        with patch.object(
            engine_module, "load_api_settings", return_value=self._settings()
        ), patch.object(self.engine, "call_deepseek_with_retry", side_effect=RuntimeError("offline")), patch.object(
            self.engine, "call_vertex_gemini_with_retry", return_value=response("Fallback")
        ) as fallback:
            self.engine.call_llm_router({}, purpose="product_name")
        fallback.assert_called_once()
        self.assertEqual(len(self.engine._ai_call_metrics), 2)

    def test_parse_failure_uses_fallback(self):
        with patch.object(
            engine_module, "load_api_settings", return_value=self._settings()
        ), patch.object(self.engine, "call_deepseek_with_retry", return_value=response("x" * 100)), patch.object(
            self.engine, "call_vertex_gemini_with_retry", return_value=response("Fallback")
        ) as fallback:
            self.engine.call_llm_router({}, purpose="product_name")
        fallback.assert_called_once()
        self.assertEqual(self.engine._ai_call_metrics[0]["reason_code"], "PRODUCT_NAME_RESPONSE_PARSE_FAILED")

    def test_validation_failure_uses_fallback(self):
        validator = lambda name: "PRODUCT_NAME_EVIDENCE_REJECTED" if name == "Bad" else ""
        with patch.object(
            engine_module, "load_api_settings", return_value=self._settings()
        ), patch.object(self.engine, "call_deepseek_with_retry", return_value=response("Bad")), patch.object(
            self.engine, "call_vertex_gemini_with_retry", return_value=response("Good")
        ) as fallback:
            self.engine.call_llm_router({}, purpose="product_name", product_name_validator=validator)
        fallback.assert_called_once()
        self.assertEqual(self.engine._ai_call_metrics[-1]["parsed_product_name"], "Good")

    def test_missing_deepseek_uses_vertex_as_primary(self):
        with patch.object(
            engine_module, "load_api_settings", return_value=self._settings(novita=False)
        ), patch.object(self.engine, "call_deepseek_with_retry") as unavailable, patch.object(
            self.engine, "call_vertex_gemini_with_retry", return_value=response("Vertex")
        ):
            self.engine.call_llm_router({}, purpose="product_name")
        unavailable.assert_not_called()
        self.assertEqual(self.engine._ai_call_metrics[0]["stage"], "primary")

    def test_no_credentials_records_blocked_without_call(self):
        with patch.object(
            engine_module, "load_api_settings", return_value=self._settings(novita=False, vertex=False)
        ):
            self.assertIsNone(self.engine.call_llm_router({}, purpose="product_name"))
        self.assertEqual(self.engine._ai_call_metrics, [])
        self.assertEqual(self.engine._product_name_events[-1]["reason_code"], "PRODUCT_NAME_CALL_BLOCKED")

    def test_rate_limit_is_not_immediately_retried_for_product_name(self):
        limited = SimpleNamespace(status_code=429, json=lambda: {}, text="rate limited")
        with patch.object(
            engine_module, "load_api_settings", return_value=self._settings(vertex=False)
        ), patch.object(engine_module.requests, "post", return_value=limited
        ) as post:
            with self.assertRaises(AIProviderCallError) as raised:
                self.engine.call_deepseek_with_retry(
                    {}, max_retries=3, diagnostic_fail_fast=True,
                )
        self.assertEqual(raised.exception.kind, "rate_limited")
        post.assert_called_once()

    def test_novita_truncated_output_retries_once_with_larger_limit(self):
        truncated = SimpleNamespace(
            status_code=200,
            json=lambda: {"choices": [{
                "finish_reason": "length",
                "message": {"content": "", "reasoning_content": "internal"},
            }]},
        )
        success = SimpleNamespace(
            status_code=200,
            json=lambda: {"choices": [{
                "finish_reason": "stop", "message": {"content": "Product"},
            }]},
        )
        seen_limits = []
        responses = iter([truncated, success])

        def fake_post(*_args, **kwargs):
            seen_limits.append(kwargs["json"]["max_tokens"])
            return next(responses)

        with patch.object(
            engine_module, "load_api_settings", return_value=self._settings(vertex=False)
        ), patch.object(engine_module.requests, "post", side_effect=fake_post) as post:
            result = self.engine.call_deepseek_with_retry(
                {}, max_retries=1, diagnostic_fail_fast=True,
            )
        self.assertEqual(post.call_count, 2)
        self.assertEqual(seen_limits, [256, 512])
        self.assertEqual(result["_output_retry_count"], 1)

    def test_novita_repeated_truncation_is_classified(self):
        truncated = SimpleNamespace(
            status_code=200,
            json=lambda: {"choices": [{
                "finish_reason": "length", "message": {"content": ""},
            }]},
        )
        with patch.object(
            engine_module, "load_api_settings", return_value=self._settings(vertex=False)
        ), patch.object(engine_module.requests, "post", return_value=truncated) as post:
            with self.assertRaises(AIProviderCallError) as raised:
                self.engine.call_deepseek_with_retry(
                    {}, max_retries=1, diagnostic_fail_fast=True,
                )
        self.assertEqual(raised.exception.kind, "output_truncated")
        self.assertEqual(raised.exception.error_code, "NOVITA_OUTPUT_TRUNCATED")
        self.assertEqual(post.call_count, 2)

    def test_component_route_keeps_existing_two_provider_plan(self):
        with patch.object(
            engine_module, "load_api_settings", return_value=self._settings(novita=False, vertex=False)
        ), patch.object(self.engine, "call_deepseek_with_retry", side_effect=RuntimeError("offline")) as primary, patch.object(
            self.engine, "call_vertex_gemini_with_retry", side_effect=RuntimeError("offline")
        ) as fallback:
            self.engine.call_llm_router({}, purpose="component_extraction")
        primary.assert_called_once()
        fallback.assert_called_once()


class ProductFailureArtifactTests(unittest.TestCase):
    def test_cli_dependency_preflight_stops_before_paid_case(self):
        settings = SimpleNamespace(
            novita_api_key="configured",
            vertex_credential_path=Path("vertex.json"),
            vertex_error_code="",
        )
        inventory = {
            "golden_pdf_missing_count": 0,
        }
        with patch.object(race, "build_inventory", return_value=([{"id": "001"}], [], inventory)), patch.object(
            race, "load_api_settings", return_value=settings,
        ), patch.object(
            race, "vertex_dependency_preflight",
            side_effect=race.APIConfigError("VERTEX_DEPENDENCY_MISSING", "google-genai"),
        ), patch.object(race, "run_case", side_effect=AssertionError("paid call started")) as run_case:
            self.assertEqual(race.main(["--all", "--with-product-ai"]), 1)
        run_case.assert_not_called()

    def test_regression_report_records_python_runtime(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            race, "REGRESSION_OUTPUT_DIR", Path(tmp),
        ):
            path = race.write_regression_report(
                mode="test", inventory={}, warnings=[], selected=[], results=[], counts=race.Counter(),
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["python_executable"], str(Path(os.sys.executable).resolve()))
        self.assertTrue(payload["python_version"])

    def test_unverified_section_one_context_is_evidence_rejected_without_call(self):
        case = {"id": "X", "_pdf_path": "x.pdf", "product_name": {"expected": "P"}, "components": []}
        class RuntimeResult(dict):
            pass

        result_type = RuntimeResult({"제품명": "", "구성성분": "", "metrics": {"ai": []}})
        result_type.runtime_shadow_context = {
            "product_name_evidence_text": "Section 1 context without a product label",
            "product_name_evidence_page": 0,
            "product_name_evidence_verified": False,
        }
        run = race.run_case(
            case, with_product_ai=True, product_name_only=True,
            process_pdf_func=lambda *_args, **_kwargs: result_type,
        )
        self.assertEqual(run["product_name_failure"]["reason_code"], "PRODUCT_NAME_EVIDENCE_REJECTED")
        self.assertEqual(run["ai_product_name_calls"], 0)

    def test_failure_record_contains_call_counts(self):
        item = race._failure_record({"id": "X", "file": "x.pdf"}, {
            "product_name_status": "product_name_ai_failed",
            "product_name_failure": {"reason_code": "PRODUCT_NAME_TIMEOUT"},
            "ai_product_name_calls": 1, "recheck_product_name_calls": 0,
        })
        self.assertEqual(item["provider_call_count"], 1)
        self.assertEqual(item["recheck_call_count"], 0)

    def test_failure_record_redacts_provider_message(self):
        item = race._failure_record({"id": "X"}, {
            "product_name_status": "product_name_ai_failed",
            "product_name_failure": {"reason_code": "PRODUCT_NAME_PROVIDER_ERROR"},
            "product_name_provider_metrics": [metric("PRODUCT_NAME_PROVIDER_ERROR", message="token=secret-value")],
        })
        self.assertNotIn("secret-value", item["message"])

    def test_failure_report_writes_json_and_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(race, "BASELINE_OUTPUT_DIR", Path(temp_dir)):
            paths = race.write_product_name_failure_analysis(
                [{"id": "X", "file": "x.pdf"}],
                [{"product_name_status": "product_name_ai_failed", "product_name_failure": {"reason_code": "PRODUCT_NAME_TIMEOUT"}}],
            )
            self.assertTrue(paths[0].exists())
            self.assertTrue(paths[1].exists())
            payload = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["reason_code_counts"], {"PRODUCT_NAME_TIMEOUT": 1})


if __name__ == "__main__":
    unittest.main()
