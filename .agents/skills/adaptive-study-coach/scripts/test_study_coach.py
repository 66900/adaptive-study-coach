"""End-to-end tests for the portable learning manager."""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

import study_coach as coach


class StudyCoachEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        workspace = coach.workspace_root_from_script()
        temp_parent = workspace / coach.DEFAULT_HOME_NAME / "cache" / "temp"
        temp_parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temp_parent)
        self.home = Path(self.temporary.name) / "test-home"
        coach.initialize(self.home)
        config_path = self.home / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["enable_fuzzing"] = False
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.config = coach.load_config(self.home)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_entries(self) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        subjects = [
            ("英语", "词汇", "term"),
            ("数学", "高等数学", "problem"),
            ("生物", "细胞生物学", "concept"),
            ("化学", "实验安全", "procedure"),
        ]
        for index in range(36):
            subject, topic, item_type = subjects[index % len(subjects)]
            entries.append(
                {
                    "subject": subject,
                    "topic": topic,
                    "type": item_type,
                    "prompt": f"{subject}测试题{index + 1}",
                    "answer": f"标准答案{index + 1}",
                    "aliases": [f"等价答案{index + 1}"],
                    "tags": ["e2e"],
                    "source": "test",
                    "confidence": 0.99,
                }
            )
        entries.append(dict(entries[0]))
        entries.append(
            {
                "subject": "英语",
                "topic": "OCR",
                "type": "term",
                "prompt": "ambi?uous",
                "answer": "",
                "confidence": 0.4,
                "source": "vision",
            }
        )
        return entries

    def test_full_learning_loop(self) -> None:
        import_path = self.home / "imports" / "cross-subject.json"
        import_path.write_text(
            json.dumps(self.make_entries(), ensure_ascii=False), encoding="utf-8"
        )
        result = coach.import_file(self.home, self.config, import_path, "英语", "未分类", 0.95)
        self.assertEqual(result["imported"], 36)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["pending"], 1)

        daily = coach.start_session(self.home, self.config, "daily", 20, 5, force_new=True)
        self.assertEqual(daily["count"], 5)
        item_id = daily["items"][0]["item_id"]
        first = coach.record_answer(
            self.home,
            self.config,
            daily["session_id"],
            item_id,
            "again",
            "错误答案",
            "概念混淆",
            1200,
            False,
        )
        due_after_first = first["next_due_utc"]
        self.assertTrue(first["needs_remediation"])

        second = coach.record_answer(
            self.home,
            self.config,
            daily["session_id"],
            item_id,
            "again",
            "仍然错误",
            "变式仍未掌握",
            900,
            True,
        )
        self.assertTrue(second["needs_another_variant"])
        self.assertEqual(second["first_fsrs_rating_preserved"], "Again")
        self.assertEqual(second["due_local"], coach.local_display(due_after_first))

        third = coach.record_answer(
            self.home,
            self.config,
            daily["session_id"],
            item_id,
            "good",
            "标准答案",
            None,
            700,
            True,
        )
        self.assertFalse(third["needs_another_variant"])
        self.assertEqual(third["due_local"], coach.local_display(due_after_first))

        finished = coach.finish_session(self.home, self.config, daily["session_id"])
        self.assertEqual(finished["score_first"], 0.0)
        self.assertTrue(Path(finished["report_md"]).exists())
        self.assertTrue(Path(finished["report_csv"]).exists())
        self.assertTrue(Path(finished["backup"]).exists())

        connection = coach.connect_db(self.home)
        try:
            mistake = connection.execute(
                "SELECT resolved, variant_count FROM mistakes WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            review = connection.execute(
                """
                SELECT rating, due_after_utc FROM reviews
                WHERE item_id = ? AND is_remediation = 0
                """,
                (item_id,),
            ).fetchone()
            remediation_due = connection.execute(
                """
                SELECT DISTINCT due_after_utc FROM reviews
                WHERE item_id = ? AND is_remediation = 1
                """,
                (item_id,),
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(mistake["resolved"], 1)
        self.assertEqual(mistake["variant_count"], 2)
        self.assertEqual(review["rating"], "Again")
        self.assertEqual(review["due_after_utc"], due_after_first)
        self.assertEqual({row[0] for row in remediation_due}, {due_after_first})

        weekly = coach.start_session(self.home, self.config, "weekly", 15, 12, force_new=True)
        monthly = coach.start_session(self.home, self.config, "monthly", 30, 30, force_new=True)
        self.assertEqual(weekly["count"], 12)
        self.assertEqual(monthly["count"], 30)
        self.assertGreaterEqual(len({item["subject"] for item in weekly["items"]}), 4)
        self.assertGreaterEqual(len({item["subject"] for item in monthly["items"]}), 4)

        pending = coach.pending_list(self.home)
        self.assertEqual(pending["count"], 1)
        args = type(
            "Args",
            (),
            {
                "pending_id": pending["items"][0]["pending_id"],
                "subject": None,
                "topic": None,
                "type": None,
                "prompt": "ambiguous",
                "answer": "模棱两可的",
            },
        )()
        resolved = coach.pending_resolve(self.home, self.config, args)
        self.assertTrue(resolved["created"])

        panel = coach.dashboard(self.home, self.config)
        self.assertEqual(panel["total_items"], 37)
        self.assertEqual(panel["pending"], 0)
        self.assertTrue(Path(panel["report"]).exists())

        health = coach.health(self.home, coach.workspace_root_from_script())
        self.assertTrue(health["healthy"])
        self.assertEqual(health["integrity"], "ok")
        self.assertTrue(health["external_pdf_process_disabled"])
        self.assertTrue(health["confined_to_workspace"])
        self.assertNotIn("strict_d_drive", health)

    def test_csv_excel_and_path_guard(self) -> None:
        csv_path = self.home / "imports" / "sample.csv"
        csv_path.write_text(
            "学科,主题,类型,问题,答案,置信度\n英语,今日单词,术语,abate,减弱；缓和,0.95\n",
            encoding="utf-8-sig",
        )
        csv_result = coach.import_file(self.home, self.config, csv_path, "英语", "未分类", 0.95)
        self.assertEqual(csv_result["imported"], 1)

        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "数学"
        sheet.append(["学科", "知识点", "类型", "问题", "答案", "置信度"])
        sheet.append(["数学", "导数", "概念", "导数的几何意义", "切线斜率", 0.95])
        excel_path = self.home / "imports" / "sample.xlsx"
        workbook.save(excel_path)
        workbook.close()
        excel_result = coach.import_file(self.home, self.config, excel_path, "数学", "未分类", 0.95)
        self.assertEqual(excel_result["imported"], 1)

        from pypdf import PdfWriter
        from pypdf.generic import (
            DecodedStreamObject,
            DictionaryObject,
            NameObject,
        )

        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        font_ref = writer._add_object(font)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        content = DecodedStreamObject()
        content.set_data(b"BT /F1 12 Tf 72 720 Td (entropy::disorder) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(content)
        pdf_path = self.home / "imports" / "sample.pdf"
        with pdf_path.open("wb") as stream:
            writer.write(stream)
        pdf_result = coach.import_file(self.home, self.config, pdf_path, "物理", "热力学", 0.95)
        self.assertEqual(pdf_result["imported"], 1)

        with self.assertRaises(coach.StudyError):
            coach.resolve_home(str(coach.workspace_root_from_script().parent / "outside-data"))
        workspace, default_home = coach.resolve_home(None)
        self.assertEqual(default_home, workspace / coach.DEFAULT_HOME_NAME)

        backups = list((self.home / "backups").glob("*.sqlite3"))
        self.assertGreaterEqual(len(backups), 4)
        for backup in backups:
            connection = sqlite3.connect(backup)
            try:
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                connection.close()

    def test_empty_session_is_not_reused_after_import(self) -> None:
        empty = coach.start_session(self.home, self.config, "daily", 20, 5, force_new=False)
        self.assertEqual(empty["count"], 0)

        path = self.home / "imports" / "one.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "subject": "英语",
                        "topic": "今日单词",
                        "type": "term",
                        "prompt": "lucid",
                        "answer": "清晰易懂的",
                        "confidence": 0.99,
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        coach.import_file(self.home, self.config, path, "英语", "未分类", 0.95)
        started = coach.start_session(self.home, self.config, "daily", 20, 5, force_new=False)
        self.assertNotEqual(started["session_id"], empty["session_id"])
        self.assertEqual(started["count"], 1)

    def test_csv_formula_injection_is_neutralized(self) -> None:
        path = self.home / "imports" / "formula.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "subject": "=cmd|' /C calc'!A0",
                        "topic": "+SUM(1,1)",
                        "type": "term",
                        "prompt": "@malicious",
                        "answer": "-2+3",
                        "confidence": 0.99,
                    }
                ]
            ),
            encoding="utf-8",
        )
        coach.import_file(self.home, self.config, path, "英语", "安全", 0.95)
        session = coach.start_session(self.home, self.config, "daily", 20, 1, force_new=True)
        item = session["items"][0]
        coach.record_answer(
            self.home,
            self.config,
            session["session_id"],
            item["item_id"],
            "good",
            "x",
            None,
            1,
            False,
        )
        finished = coach.finish_session(self.home, self.config, session["session_id"])
        raw = Path(finished["report_csv"]).read_text(encoding="utf-8-sig")
        rows = [row for row in csv.reader(io.StringIO(raw)) if row]
        self.assertEqual(len(rows), 2)
        self.assertNotIn("\r\r\n", raw)
        for cell in rows[1]:
            self.assertFalse(cell.lstrip().startswith(("=", "+", "-", "@")))
        self.assertEqual(rows[1][0], "'=cmd|' /C calc'!A0")

    def test_markdown_report_data_is_strictly_escaped(self) -> None:
        raw = "# title | [click](javascript:alert(1)) <img src=x> `code`\n-item"
        escaped = coach.markdown_escape(raw)
        self.assertIn(r"\# title \|", escaped)
        self.assertIn(r"\[click\]\(javascript:alert\(1\)\)", escaped)
        self.assertIn("&lt;img src=x&gt;", escaped)
        self.assertIn(r"\`code\`", escaped)
        self.assertIn(r"<br>\-item", escaped)
        self.assertNotIn("<img", escaped)

    def test_begin_immediate_serializes_database_writers(self) -> None:
        first = coach.connect_db(self.home)
        second = sqlite3.connect(coach.db_path(self.home), timeout=0.05)
        second.execute("PRAGMA busy_timeout = 50")
        try:
            self.assertFalse(first.in_transaction)
            coach.begin_immediate(first)
            with self.assertRaisesRegex(coach.StudyError, "另一个任务"):
                coach.begin_immediate(second)
            first.rollback()
            coach.begin_immediate(second)
            self.assertTrue(second.in_transaction)
            second.rollback()
        finally:
            first.close()
            second.close()

    def test_ocr_confidence_never_implies_content_verification(self) -> None:
        path = self.home / "imports" / "ocr-confidence.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "subject": "数学",
                        "topic": "OCR",
                        "type": "qa",
                        "prompt": "2+2=?",
                        "answer": "5",
                        "source": "vision",
                        "ocr_confidence": 0.99,
                        "content_confidence": 0.99,
                        "content_verified": False,
                    },
                    {
                        "subject": "数学",
                        "topic": "OCR",
                        "type": "qa",
                        "prompt": "3+3=?",
                        "answer": "6",
                        "source": "vision",
                        "ocr_confidence": 0.99,
                        "content_confidence": 0.99,
                        "content_verified": True,
                    },
                    {
                        "subject": "数学",
                        "topic": "OCR",
                        "type": "qa",
                        "prompt": "4+4=?",
                        "answer": "9",
                        "source": "vision",
                        "confidence": 0.99,
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        result = coach.import_file(self.home, self.config, path, "数学", "OCR", 0.95)
        self.assertEqual(result["pending"], 2)
        self.assertEqual(result["imported"], 1)
        pending_items = coach.pending_list(self.home)["items"]
        self.assertTrue(all("OCR 内容尚未人工确认" in item["reason"] for item in pending_items))

    def test_remediation_hard_limit_ends_the_chain(self) -> None:
        self.config["max_remediation_attempts_per_item"] = 2
        self.config["max_remediation_attempts_per_session"] = 4
        path = self.home / "imports" / "limit.json"
        path.write_text(
            json.dumps([{"prompt": "lucid", "answer": "clear", "confidence": 0.99}]),
            encoding="utf-8",
        )
        coach.import_file(self.home, self.config, path, "英语", "词汇", 0.95)
        session = coach.start_session(self.home, self.config, "daily", 20, 1, force_new=True)
        item_id = session["items"][0]["item_id"]
        coach.record_answer(
            self.home,
            self.config,
            session["session_id"],
            item_id,
            "again",
            "wrong",
            None,
            1,
            False,
        )
        first = coach.record_answer(
            self.home,
            self.config,
            session["session_id"],
            item_id,
            "again",
            "wrong-1",
            None,
            1,
            True,
        )
        self.assertTrue(first["needs_another_variant"])
        second = coach.record_answer(
            self.home,
            self.config,
            session["session_id"],
            item_id,
            "again",
            "wrong-2",
            None,
            1,
            True,
        )
        self.assertFalse(second["needs_another_variant"])
        self.assertTrue(second["remediation_exhausted"])
        self.assertEqual(second["exhaustion_reason"], "item_limit")
        with self.assertRaises(coach.StudyError):
            coach.record_answer(
                self.home,
                self.config,
                session["session_id"],
                item_id,
                "again",
                "wrong-3",
                None,
                1,
                True,
            )
        finished = coach.finish_session(self.home, self.config, session["session_id"])
        self.assertEqual(finished["status"], "completed")

    def test_session_remediation_hard_limit_ends_the_chain(self) -> None:
        self.config["max_remediation_attempts_per_item"] = 5
        self.config["max_remediation_attempts_per_session"] = 2
        path = self.home / "imports" / "session-limit.json"
        path.write_text(
            json.dumps([{"prompt": "abate", "answer": "lessen", "confidence": 0.99}]),
            encoding="utf-8",
        )
        coach.import_file(self.home, self.config, path, "英语", "词汇", 0.95)
        session = coach.start_session(self.home, self.config, "daily", 20, 1, force_new=True)
        item_id = session["items"][0]["item_id"]
        coach.record_answer(
            self.home,
            self.config,
            session["session_id"],
            item_id,
            "again",
            "wrong",
            None,
            1,
            False,
        )
        coach.record_answer(
            self.home,
            self.config,
            session["session_id"],
            item_id,
            "again",
            "wrong-1",
            None,
            1,
            True,
        )
        exhausted = coach.record_answer(
            self.home,
            self.config,
            session["session_id"],
            item_id,
            "again",
            "wrong-2",
            None,
            1,
            True,
        )
        self.assertTrue(exhausted["remediation_exhausted"])
        self.assertEqual(exhausted["exhaustion_reason"], "session_limit")
        self.assertEqual(exhausted["session_remediation_attempts"], 2)

    def test_active_session_resumes_across_local_dates(self) -> None:
        path = self.home / "imports" / "resume.json"
        path.write_text(
            json.dumps([{"prompt": "abate", "answer": "lessen", "confidence": 0.99}]),
            encoding="utf-8",
        )
        coach.import_file(self.home, self.config, path, "英语", "词汇", 0.95)
        started = coach.start_session(self.home, self.config, "daily", 20, 1, force_new=False)
        connection = coach.connect_db(self.home)
        try:
            connection.execute(
                "UPDATE sessions SET started_at_utc = ? WHERE id = ?",
                (
                    coach.iso_utc(coach.utc_now() - timedelta(days=2)),
                    started["session_id"],
                ),
            )
            connection.commit()
        finally:
            connection.close()
        resumed = coach.start_session(self.home, self.config, "daily", 20, 1, force_new=False)
        self.assertTrue(resumed["reused"])
        self.assertEqual(resumed["session_id"], started["session_id"])

    def test_backup_retention_and_hash_verification(self) -> None:
        self.config["backup_retention_count"] = 3
        self.config["backup_max_total_mb"] = 100
        for index in range(6):
            coach.backup_database(self.home, f"retention-{index}", self.config)
        backups = sorted((self.home / "backups").glob("*.sqlite3"))
        self.assertEqual(len(backups), 3)
        for backup in backups:
            verification = coach.verify_backup(backup)
            self.assertEqual(verification["sqlite_integrity"], "ok")
            self.assertTrue(verification["sha256_matches"])

    def test_import_rejects_files_outside_repository(self) -> None:
        workspace = coach.workspace_root_from_script()
        with tempfile.TemporaryDirectory(dir=workspace.parent) as temporary:
            outside = Path(temporary) / "outside.json"
            outside.write_text(
                json.dumps([{"prompt": "x", "answer": "y", "confidence": 0.99}]),
                encoding="utf-8",
            )
            with self.assertRaises(coach.StudyError):
                coach.import_file(self.home, self.config, outside, "英语", "安全", 0.95)

    def test_missing_dependency_health_still_returns_json(self) -> None:
        manager = Path(coach.__file__).resolve()
        clean_environment = dict(os.environ)
        clean_environment.pop("PYTHONPATH", None)
        completed = subprocess.run(
            [sys.executable, "-S", str(manager), "health"],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            env=clean_environment,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["healthy"])
        self.assertIn("startup_error", payload)
        self.assertNotIn("Traceback", completed.stderr)

    def test_schema_v1_migrates_without_losing_confidence(self) -> None:
        legacy_home = Path(self.temporary.name) / "legacy-home"
        coach.ensure_dirs(legacy_home)
        connection = sqlite3.connect(coach.db_path(legacy_home))
        try:
            connection.executescript(
                """
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta(key, value) VALUES('schema_version', '1');
                CREATE TABLE items (
                    id TEXT PRIMARY KEY,
                    confidence REAL NOT NULL
                );
                INSERT INTO items(id, confidence) VALUES('item-1', 0.81);
                CREATE TABLE pending_imports (
                    id TEXT PRIMARY KEY,
                    confidence REAL NOT NULL
                );
                INSERT INTO pending_imports(id, confidence) VALUES('pending-1', 0.42);
                """
            )
            connection.commit()
        finally:
            connection.close()
        migrated = coach.connect_db(legacy_home)
        try:
            self.assertIn("ocr_confidence", coach.table_columns(migrated, "items"))
            self.assertIn("content_verified", coach.table_columns(migrated, "pending_imports"))
            self.assertEqual(
                migrated.execute(
                    "SELECT content_confidence FROM items WHERE id='item-1'"
                ).fetchone()[0],
                0.81,
            )
            self.assertEqual(
                migrated.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0],
                coach.SCHEMA_VERSION,
            )
        finally:
            migrated.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
