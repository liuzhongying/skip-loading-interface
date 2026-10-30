import gc
import tempfile
import unittest
from datetime import datetime
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
import app


class McTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = app.DB_PATH
        app.DB_PATH = Path(self.temp.name) / "test.db"
        app.init_db()

    def tearDown(self):
        app.DB_PATH = self.old_db
        gc.collect()
        self.temp.cleanup()

    def workbook(self, valid=True):
        workbook = Workbook()
        sheet = workbook.active
        headers = [f"col{i}" for i in range(1, 29)]
        headers[2] = "pyName" if valid else "other"
        sheet.append(headers)
        for index in range(12):
            row = [None] * 28
            for column, value in {0: "Date", 2: "KEY", 10: datetime(2026, 8, 1, 6), 12: f"rule{index}", 26: "start", 27: "end"}.items():
                row[column] = value
            sheet.append(row)
        output = BytesIO()
        workbook.save(output)
        return output.getvalue()

    def test_import_and_lookup_all_matching_rows(self):
        self.assertEqual(app.import_mc_excel(self.workbook())["imported_count"], 12)
        result = app.lookup_mc("key")
        self.assertEqual((result["total"], result["total_pages"], len(result["items"])), (12, 2, 10))
        self.assertEqual(result["items"][0]["prod_start_dt"], "2026-08-01 06:00:00")
        self.assertEqual(len(app.lookup_mc("KEY", 2)["items"]), 2)
        self.assertEqual(app.lookup_mc("missing")["total"], 0)

    def test_invalid_workbook_does_not_import(self):
        app.import_mc_excel(self.workbook())
        with self.assertRaises(ValueError):
            app.import_mc_excel(self.workbook(False))
        self.assertEqual(app.lookup_mc("KEY")["total"], 12)

    def test_import_replaces_previous_records(self):
        app.import_mc_excel(self.workbook())
        app.import_mc_excel(self.workbook())
        self.assertEqual(app.lookup_mc("KEY")["total"], 12)


if __name__ == "__main__":
    unittest.main()
