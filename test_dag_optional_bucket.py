import gc
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
import app


class DagOptionalBucketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = app.DB_PATH
        app.DB_PATH = Path(self.temp.name) / "test.db"
        app.init_db()

    def tearDown(self):
        app.DB_PATH = self.old_db
        gc.collect()
        self.temp.cleanup()

    def test_form_accepts_empty_bucket(self):
        values = {key: "value" for key in app.DAG_REQUIRED_FIELDS}
        values["dag_id"] = "FORM_TEST"
        entry = app.create_dag_entry(values)
        self.assertEqual(entry["bucket_folder"], "")
        values["description"] = ""
        with self.assertRaises(ValueError):
            app.create_dag_entry(values)

    def test_excel_accepts_empty_or_missing_bucket_column(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "DAG"
        fields = [(key, label) for key, label in app.DAG_COLUMNS if key != "bucket_folder"]
        sheet.append([label for key, label in fields])
        sheet.append(["EXCEL_TEST" if key == "dag_id" else "value" for key, label in fields])
        file = BytesIO()
        workbook.save(file)
        result = app.import_dag_excel(file.getvalue())
        self.assertEqual(result["imported_count"], 1)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(app.get_dag_history("EXCEL_TEST")["current_record"]["bucket_folder"], "")


if __name__ == "__main__":
    unittest.main()
