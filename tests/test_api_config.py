import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api_config import (
    APIConfigError,
    api_status_lines,
    load_api_settings,
    python_runtime_metadata,
    vertex_dependency_preflight,
)


class APIConfigTests(unittest.TestCase):
    @staticmethod
    def _credential(root: Path, project_id="project-one") -> Path:
        path = root / "vertex_key.json"
        path.write_text(json.dumps({"project_id": project_id}), encoding="utf-8")
        return path

    def test_relative_vertex_path_resolves_from_project_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = self._credential(root)
            env = {"GOOGLE_APPLICATION_CREDENTIALS": "vertex_key.json"}
            settings = load_api_settings(root, environ=env)
            self.assertEqual(settings.vertex_credential_path, expected.resolve())
            self.assertEqual(env["GOOGLE_APPLICATION_CREDENTIALS"], str(expected.resolve()))

    def test_relative_path_is_independent_of_current_working_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as other_dir:
            root = Path(temp_dir)
            expected = self._credential(root)
            with patch.object(Path, "cwd", return_value=Path(other_dir)):
                settings = load_api_settings(
                    root, environ={"GOOGLE_APPLICATION_CREDENTIALS": "vertex_key.json"},
                )
            self.assertEqual(settings.vertex_credential_path, expected.resolve())

    def test_absolute_vertex_path_is_used_as_is(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as other_dir:
            expected = self._credential(Path(temp_dir))
            settings = load_api_settings(
                Path(other_dir), environ={"GOOGLE_APPLICATION_CREDENTIALS": str(expected)},
            )
            self.assertEqual(settings.vertex_credential_path, expected.resolve())

    def test_missing_credential_has_explicit_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_api_settings(
                Path(temp_dir), environ={"GOOGLE_APPLICATION_CREDENTIALS": "missing.json"},
            )
            with self.assertRaises(APIConfigError) as raised:
                settings.require_vertex()
            self.assertEqual(raised.exception.code, "VERTEX_CREDENTIAL_FILE_MISSING")

    def test_project_id_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._credential(root, "json-project")
            settings = load_api_settings(root, environ={
                "GOOGLE_APPLICATION_CREDENTIALS": "vertex_key.json",
                "GOOGLE_CLOUD_PROJECT": "environment-project",
            })
            with self.assertRaises(APIConfigError) as raised:
                settings.require_vertex()
            self.assertEqual(raised.exception.code, "VERTEX_PROJECT_ID_MISMATCH")

    def test_dotenv_does_not_override_existing_os_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text("NOVITA_API_KEY=dotenv-value\n", encoding="utf-8")
            with patch.dict(os.environ, {"NOVITA_API_KEY": "os-value"}, clear=True):
                settings = load_api_settings(root)
                self.assertEqual(settings.novita_api_key, "os-value")

    def test_novita_and_deepseek_credentials_are_not_substituted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_api_settings(Path(temp_dir), environ={
                "NOVITA_API_KEY": "novita-value",
                "DEEPSEEK_API_KEY": "deepseek-value",
            })
            self.assertEqual(settings.novita_api_key, "novita-value")
            self.assertEqual(settings.deepseek_api_key, "deepseek-value")

    def test_status_diagnostics_do_not_expose_secret_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_api_settings(
                Path(temp_dir), environ={"NOVITA_API_KEY": "do-not-print-this"},
            )
            output = "\n".join(api_status_lines(settings))
            self.assertIn("NOVITA_API_KEY: configured", output)
            self.assertNotIn("do-not-print-this", output)

    def test_vertex_dependency_preflight_reports_missing_dependency(self):
        def importer(name):
            if name == "google.genai":
                raise ModuleNotFoundError(name)
            return object()

        with self.assertRaises(APIConfigError) as raised:
            vertex_dependency_preflight(importer=importer)
        self.assertEqual(raised.exception.code, "VERTEX_DEPENDENCY_MISSING")
        self.assertIn("google-genai", str(raised.exception))

    def test_vertex_dependency_preflight_accepts_required_imports(self):
        imported = []

        def importer(name):
            imported.append(name)
            return object()

        vertex_dependency_preflight(importer=importer)
        self.assertIn("google.auth", imported)
        self.assertIn("google.genai", imported)

    def test_python_runtime_metadata_uses_current_interpreter(self):
        metadata = python_runtime_metadata()
        self.assertTrue(Path(metadata["python_executable"]).is_absolute())
        self.assertTrue(metadata["python_version"])


if __name__ == "__main__":
    unittest.main()
