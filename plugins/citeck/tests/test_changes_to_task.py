"""Tests for citeck-changes-to-task — task.md parsing and type mapping."""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "skills", "citeck-changes-to-task", "scripts"
)
PLUGIN_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _ensure_plugin_in_path():
    if PLUGIN_ROOT not in sys.path:
        sys.path.insert(0, PLUGIN_ROOT)


def _import_module():
    """Import create_from_taskmd as a module."""
    import importlib.util
    _ensure_plugin_in_path()
    spec = importlib.util.spec_from_file_location(
        "create_from_taskmd",
        os.path.join(SCRIPTS_DIR, "create_from_taskmd.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_task_file(content):
    """Write a temporary task.md file and return its path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return f.name


SAMPLE_BUG = """\
**Тип:** Ошибка

## Fix login validation on mobile

При входе через мобильное устройство валидация не срабатывает.

#### Что изменено

- Исправлена валидация форм на мобильных устройствах
"""

SAMPLE_STORY = """\
**Тип:** История

## Add dark mode support

Добавлена поддержка тёмной темы для улучшения пользовательского опыта.

#### Что изменено

- Реализован переключатель тёмной темы в настройках
"""

SAMPLE_TASK = """\
**Тип:** Задача

## Refactor authentication module

Рефакторинг модуля аутентификации для улучшения поддержки.

#### Что изменено

- Выделен общий модуль авторизации в lib/
"""


class TestParseTaskFile(unittest.TestCase):

    def test_parse_bug_type(self):
        module = _import_module()
        path = _write_task_file(SAMPLE_BUG)
        try:
            result = module.parse_task_file(path)
            self.assertEqual(result["type"], "Ошибка")
            self.assertEqual(result["summary"], "Fix login validation on mobile")
            self.assertIn("валидация", result["description"])
        finally:
            os.unlink(path)

    def test_parse_story_type(self):
        module = _import_module()
        path = _write_task_file(SAMPLE_STORY)
        try:
            result = module.parse_task_file(path)
            self.assertEqual(result["type"], "История")
            self.assertEqual(result["summary"], "Add dark mode support")
        finally:
            os.unlink(path)

    def test_parse_task_type(self):
        module = _import_module()
        path = _write_task_file(SAMPLE_TASK)
        try:
            result = module.parse_task_file(path)
            self.assertEqual(result["type"], "Задача")
            self.assertEqual(result["summary"], "Refactor authentication module")
        finally:
            os.unlink(path)

    def test_missing_type_line(self):
        module = _import_module()
        path = _write_task_file("## Some title\n\nDescription here.")
        try:
            with self.assertRaises(ValueError) as ctx:
                module.parse_task_file(path)
            self.assertIn("Cannot find type", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_unknown_type(self):
        module = _import_module()
        path = _write_task_file("**Тип:** Unknown\n\n## Title\n\nDesc.")
        try:
            with self.assertRaises(ValueError) as ctx:
                module.parse_task_file(path)
            self.assertIn("Unknown type", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_missing_title(self):
        module = _import_module()
        path = _write_task_file("**Тип:** Ошибка\n\nNo heading here.")
        try:
            with self.assertRaises(ValueError) as ctx:
                module.parse_task_file(path)
            self.assertIn("Cannot find title", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_file_not_found(self):
        module = _import_module()
        with self.assertRaises(FileNotFoundError):
            module.parse_task_file("/nonexistent/task.md")

    def test_description_is_after_title(self):
        module = _import_module()
        content = "**Тип:** Задача\n\n## My Title\n\nFirst paragraph.\n\nSecond paragraph."
        path = _write_task_file(content)
        try:
            result = module.parse_task_file(path)
            self.assertIn("First paragraph", result["description"])
            self.assertIn("Second paragraph", result["description"])
            self.assertNotIn("My Title", result["description"])
        finally:
            os.unlink(path)


class TestTypeMapping(unittest.TestCase):

    def test_all_types_mapped(self):
        module = _import_module()
        self.assertEqual(
            module.TYPE_MAP["Ошибка"], "ept-issue-bug"
        )
        self.assertEqual(
            module.TYPE_MAP["История"], "ept-issue-story"
        )
        self.assertEqual(
            module.TYPE_MAP["Задача"], "ept-issue-task"
        )

    def test_type_map_has_three_entries(self):
        module = _import_module()
        self.assertEqual(len(module.TYPE_MAP), 3)


class TestBuildRecord(unittest.TestCase):

    def test_build_bug_record(self):
        module = _import_module()
        parsed = {"type": "Ошибка", "summary": "Fix bug", "description": "Details"}
        record = module.build_record(parsed, project="EPT")
        self.assertEqual(record["id"], "emodel/ept-issue@")
        self.assertEqual(
            record["attributes"]["type?str"], "ept-issue-bug"
        )
        self.assertEqual(record["attributes"]["_workspace?str"], "EPT")
        self.assertEqual(record["attributes"]["summary?str"], "Fix bug")
        self.assertEqual(record["attributes"]["description?str"], "Details")
        self.assertEqual(record["attributes"]["priority?str"], "300_medium")

    def test_build_with_assignee(self):
        module = _import_module()
        parsed = {"type": "История", "summary": "Story", "description": "D"}
        record = module.build_record(parsed, project="HR", assignee="dev1")
        self.assertEqual(
            record["attributes"]["implementer?str"], "emodel/person@dev1"
        )

    def test_build_with_prefixed_assignee(self):
        module = _import_module()
        parsed = {"type": "Задача", "summary": "Task", "description": "D"}
        record = module.build_record(
            parsed, project="X", assignee="emodel/person@admin"
        )
        self.assertEqual(
            record["attributes"]["implementer?str"], "emodel/person@admin"
        )

    def test_build_with_custom_priority(self):
        module = _import_module()
        parsed = {"type": "Ошибка", "summary": "Bug", "description": "D"}
        record = module.build_record(
            parsed, project="EPT", priority="100_urgent"
        )
        self.assertEqual(record["attributes"]["priority?str"], "100_urgent")


class TestDryRun(unittest.TestCase):

    def test_dry_run_output(self):
        module = _import_module()
        path = _write_task_file(SAMPLE_BUG)
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                module.main([
                    "--task-file", path, "--project", "EPT", "--dry-run"
                ])
            output = out.getvalue()
            self.assertIn("Issue Preview:", output)
            self.assertIn("Ошибка", output)
            self.assertIn("bug", output)
            self.assertIn("EPT", output)
            self.assertIn("Fix login validation on mobile", output)
            self.assertIn("emodel/ept-issue@", output)
        finally:
            os.unlink(path)

    def test_dry_run_with_assignee(self):
        module = _import_module()
        path = _write_task_file(SAMPLE_STORY)
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                module.main([
                    "--task-file", path, "--project", "HR",
                    "--assignee", "tester", "--dry-run"
                ])
            output = out.getvalue()
            self.assertIn("emodel/person@tester", output)
        finally:
            os.unlink(path)


class TestCreateIssue(unittest.TestCase):

    @patch("lib.records_api.records_mutate")
    def test_create_success(self, mock_mutate):
        mock_mutate.return_value = {
            "records": [{"id": "emodel/ept-issue@EPT-42"}]
        }
        module = _import_module()
        path = _write_task_file(SAMPLE_TASK)
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                module.main(["--task-file", path, "--project", "EPT"])
            output = out.getvalue()
            self.assertIn("Created issue: emodel/ept-issue@EPT-42", output)
            mock_mutate.assert_called_once()
            record = mock_mutate.call_args[0][0][0]
            self.assertEqual(
                record["attributes"]["type?str"], "ept-issue-task"
            )
            self.assertEqual(record["attributes"]["_workspace?str"], "EPT")
        finally:
            os.unlink(path)

    @patch("lib.records_api.records_mutate")
    def test_create_api_error(self, mock_mutate):
        from lib.records_api import RecordsApiError
        mock_mutate.side_effect = RecordsApiError(
            "Server error", response_body="details"
        )
        module = _import_module()
        path = _write_task_file(SAMPLE_BUG)
        try:
            with self.assertRaises(SystemExit) as ctx:
                module.main(["--task-file", path, "--project", "EPT"])
            self.assertEqual(ctx.exception.code, 1)
        finally:
            os.unlink(path)

    def test_invalid_task_file_exits(self):
        module = _import_module()
        with self.assertRaises(SystemExit) as ctx:
            module.main([
                "--task-file", "/nonexistent/task.md",
                "--project", "EPT"
            ])
        self.assertEqual(ctx.exception.code, 1)


class TestCLI(unittest.TestCase):

    def test_help_flag(self):
        script_path = os.path.join(SCRIPTS_DIR, "create_from_taskmd.py")
        result = subprocess.run(
            [sys.executable, script_path, "--help"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--task-file", result.stdout)
        self.assertIn("--project", result.stdout)
        self.assertIn("--dry-run", result.stdout)

    def test_missing_required_args(self):
        script_path = os.path.join(SCRIPTS_DIR, "create_from_taskmd.py")
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--task-file", result.stderr)


class TestFormatPreview(unittest.TestCase):

    def test_format_shows_type_mapping(self):
        module = _import_module()
        record = {
            "id": "emodel/ept-issue@",
            "attributes": {
                "type?str": "ept-issue-bug",
                "_workspace?str": "EPT",
                "summary?str": "Fix bug",
                "description?str": "Some description",
                "priority?str": "300_medium",
            },
        }
        result = module.format_preview(record, "Ошибка")
        self.assertIn("Ошибка", result)
        self.assertIn("bug", result)
        self.assertIn("EPT", result)
        self.assertIn("Fix bug", result)

    def test_format_truncates_long_description(self):
        module = _import_module()
        desc = "\n".join([f"Line {i}" for i in range(10)])
        record = {
            "id": "emodel/ept-issue@",
            "attributes": {
                "type?str": "ept-issue-task",
                "_workspace?str": "X",
                "summary?str": "Task",
                "description?str": desc,
                "priority?str": "300_medium",
            },
        }
        result = module.format_preview(record, "Задача")
        self.assertIn("...", result)


if __name__ == "__main__":
    unittest.main()
