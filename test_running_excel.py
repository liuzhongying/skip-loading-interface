import unittest
from io import BytesIO

from openpyxl import load_workbook
import app


class RunningExcelTests(unittest.TestCase):
    def test_sheets_reasons_labels_and_text_values(self):
        payload = {"today": "2026-10-31", "results": [
            {"py_name": "=SAS003337", "py_label": "Active", "run_num": "003337", "status": "RUNNING", "reason": "Run valid", "tasks": [{"task_id": "t", "status": "RUNNING", "reason": "VM valid"}], "mc_entries": [{"id": 1, "status": "RUNNING", "reason": "MC valid"}]},
            {"py_name": "SAS2", "run_num": "2", "status": "NOT_RUNNING", "reason": "STOP", "tasks": [], "mc_entries": []},
            {"py_name": "SAS3", "run_num": "3", "status": "UNKNOWN", "reason": "Duplicate MC", "tasks": [], "mc_entries": [{"id": 2, "py_label": "Label A", "status": "UNKNOWN", "reason": "Unknown"}, {"id": 3, "py_label": "Label B", "status": "UNKNOWN", "reason": "Unknown"}]},
        ]}
        workbook = load_workbook(BytesIO(app.running_status_excel(payload)))
        self.assertEqual(workbook.sheetnames, ["RUNNING", "NOT_RUNNING", "UNKNOWN"])
        running = workbook["RUNNING"]
        self.assertEqual([c.value for c in running[1]], ["pyName", "pyLabel", "Run_Num", "最終狀態", "RUNNING的主要原因"])
        self.assertEqual(running["A2"].value, "=SAS003337")
        self.assertEqual(running["A2"].data_type, "s")
        self.assertEqual(running["C2"].value, "003337")
        self.assertIn("VM valid", running["E2"].value)
        self.assertIn("MC valid", running["E2"].value)
        self.assertEqual(workbook["NOT_RUNNING"]["E2"].value, "STOP")
        self.assertEqual(workbook["UNKNOWN"]["B2"].value, "Label A; Label B")
        self.assertIn("2026-10-31", workbook.properties.description)

    def test_empty_sheets_and_invalid_status(self):
        workbook = load_workbook(BytesIO(app.running_status_excel({"results": []})))
        self.assertTrue(all(sheet.max_row == 1 for sheet in workbook))
        with self.assertRaises(ValueError):
            app.running_status_excel({"results": [{"status": "OTHER"}]})


if __name__ == "__main__":
    unittest.main()
