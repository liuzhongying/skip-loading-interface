import gc
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
import app


class TaskOptionalFieldsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = app.DB_PATH
        app.DB_PATH = Path(self.temp.name) / "test.db"
        app.init_db()

    def tearDown(self):
        app.DB_PATH = self.old_db
        gc.collect()
        self.temp.cleanup()

    def test_form_accepts_blank_optional_fields(self):
        values = {"dag_id": "DAG", "task_id": "TASK", "task_name": "Name"}
        row = app.create_task_entry(values)
        for field in ("shell_command", "file_wait_bucket", "filewait_time_out_in_seconds"):
            self.assertEqual(row[field], "")
        values["task_name"] = ""
        with self.assertRaises(ValueError):
            app.create_task_entry(values)

    def test_excel_accepts_missing_and_blank_optional_fields(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "TASKS"
        sheet.append(["dag_id", "task_id", "task_name", "shell_command"])
        sheet.append(["DAG", "TASK", "Name", None])
        file = BytesIO()
        workbook.save(file)
        result = app.import_tasks_excel(file.getvalue())
        self.assertEqual(result["imported_count"], 1)
        self.assertEqual(result["failed_count"], 0)
        record = app.get_task_history("TASK")["current_record"]
        for field in ("shell_command", "file_wait_bucket", "filewait_time_out_in_seconds"):
            self.assertEqual(record[field], "")


if __name__ == "__main__":
    unittest.main()
