import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import app


class RunningStatusTests(unittest.TestCase):
    def test_mc_run_number_extraction(self):
        self.assertEqual(app.run_nums_from_mc_name("Offer_sas003337_SAS13337"), ["003337", "13337"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript("""
            CREATE TABLE requests (id INTEGER PRIMARY KEY, run_num TEXT, action TEXT, end_date TEXT, status TEXT);
            CREATE TABLE task_entries (id INTEGER PRIMARY KEY, task_id TEXT, dag_id TEXT, task_inactive_flag TEXT);
            CREATE TABLE dag_entries (id INTEGER PRIMARY KEY, dag_id TEXT, start_datetime TEXT, end_date TEXT, vm_alive_days TEXT);
            CREATE TABLE mc_entries (id INTEGER PRIMARY KEY, proposition_active TEXT, py_name TEXT, prod_start_dt TEXT, eligibility_rule TEXT, start_date TEXT, end_date TEXT);
        """)
        self.conn.execute("INSERT INTO dag_entries VALUES (1, 'dag', '2026,8,1,18,00', '2026,8,31,20,00', '10')")
        self.conn.execute("INSERT INTO task_entries VALUES (1, 'TASK_RDP3337', 'dag', 'N')")
        self.conn.execute("INSERT INTO mc_entries VALUES (1, 'Always', 'SAS3337', '2026-08-01', '', '', '')")
        self.conn.commit()
        self.db = patch.object(app, "DB_PATH", self.path)
        self.clock = patch.object(app, "today", return_value=date(2026, 8, 10))
        self.db.start()
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.db.stop()
        self.conn.close()
        self.temp.cleanup()

    def check(self, *values):
        self.conn.row_factory = sqlite3.Row
        return app.run_num_statuses(self.conn, list(values), app.today())

    def check_names(self, *values):
        return app.check_running_status({"py_names": list(values)})["results"]

    def test_full_match_vm_boundary_and_read_only(self):
        before = self.path.read_bytes()
        first, second = self.check("3337", "13337")
        self.assertEqual(first["status"], "RUNNING")
        self.assertIn("NO_TASK_FOR_RUN_NUM", second["reason"])
        self.assertEqual(self.check_names("SAS3337")[0]["status"], "RUNNING")
        self.assertEqual(before, self.path.read_bytes())
        with patch.object(app, "today", return_value=date(2026, 8, 11)):
            self.assertEqual(self.check("3337")[0]["tasks"][0]["status"], "NOT_RUNNING_VM_EXPIRED")

    def test_latest_effective_skip_and_versions(self):
        self.conn.execute("INSERT INTO requests VALUES (1, '3337', 'STOP', '2026-08-10', 'approved')")
        self.conn.execute("INSERT INTO requests VALUES (2, '3337', 'RESUME', '2026-08-09', 'pending')")
        self.conn.commit()
        self.assertIn("STOPPED_BY_SKIP_LOADING", self.check("3337")[0]["reason"])
        self.conn.execute("INSERT INTO requests VALUES (3, '3337', 'RESUME', '2026-08-09', 'exported')")
        self.conn.execute("INSERT INTO task_entries VALUES (2, 'TASK_RDP3337', 'dag', 'Y')")
        self.conn.commit()
        self.assertEqual(self.check("3337")[0]["tasks"][0]["status"], "NOT_RUNNING_TASK_INACTIVE")

    def test_multiple_tasks_and_latest_dag(self):
        self.conn.execute("INSERT INTO dag_entries VALUES (2, 'dag', '2026,8,1,0,0', '2026,8,31,0,0', '-1')")
        self.conn.execute("INSERT INTO task_entries VALUES (2, 'OTHER_RDP3337', 'other', 'N')")
        self.conn.commit()
        result = self.check("3337")[0]
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual({x["status"] for x in result["tasks"]}, {"UNKNOWN_VM_VALIDITY", "NO_DAG_FOR_TASK"})
        self.conn.execute("INSERT INTO dag_entries VALUES (3, 'other', '2026,8,1,0,0', '2026,8,31,0,0', '10')")
        self.conn.commit()
        self.assertEqual(self.check("3337")[0]["status"], "RUNNING")

    def test_blank_vm_and_invalid_values(self):
        self.conn.execute("INSERT INTO dag_entries VALUES (2, 'dag', '2026,8,1,0,0', '2026,8,31,0,0', '')")
        self.conn.commit()
        self.assertEqual(self.check("3337")[0]["status"], "RUNNING")
        for index, value in enumerate(("-1", "1.5", "0", "bad"), start=3):
            self.conn.execute("INSERT INTO dag_entries VALUES (?, 'dag', '2026,8,1,0,0', '2026,8,31,0,0', ?)", (index, value))
            self.conn.commit()
            self.assertEqual(self.check("3337")[0]["status"], "UNKNOWN")

    def test_leading_zero_and_stop_year_9999(self):
        self.conn.execute("INSERT INTO task_entries VALUES (2, 'TASK_RDP003337', 'dag', 'N')")
        self.conn.execute("INSERT INTO requests VALUES (1, '003337', 'STOP', '9999-12-31', 'approved')")
        self.conn.commit()
        first, second = self.check("3337", "003337")
        self.assertEqual(first["status"], "RUNNING")
        self.assertIn("STOPPED_BY_SKIP_LOADING", second["reason"])
        self.conn.execute("UPDATE requests SET end_date = '9999-01-01' WHERE id = 1")
        self.conn.commit()
        with patch.object(app, "today", return_value=date(9999, 12, 31)):
            self.assertIn("STOPPED_BY_SKIP_LOADING", self.check("003337")[0]["reason"])

    def test_mc_multiple_names_and_boundaries(self):
        self.conn.execute("DELETE FROM mc_entries")
        self.conn.execute("INSERT INTO mc_entries VALUES (1, 'Never', 'Offer_SAS3337', '', '', '', '')")
        self.conn.execute("INSERT INTO mc_entries VALUES (2, 'Date', 'Other_sas3337', '2026-08-10', '', '2026-08-10', '2026-08-10')")
        self.conn.commit()
        first, second = self.check_names("Offer_SAS3337", "Other_sas3337")
        self.assertEqual((first["status"], second["status"]), ("NOT_RUNNING", "RUNNING"))
        self.assertEqual(first["run_num"], second["run_num"])
        self.conn.execute("UPDATE mc_entries SET prod_start_dt = '2026-08-11' WHERE id = 2")
        self.conn.commit()
        self.assertEqual(self.check_names("Other_sas3337")[0]["status"], "NOT_RUNNING")

    def test_mc_unknown_missing_and_exact_match(self):
        self.conn.execute("DELETE FROM mc_entries")
        self.conn.execute("INSERT INTO mc_entries VALUES (1, 'Always', 'SAS13337', '2026-08-01', '', '', '')")
        self.conn.commit()
        result = self.check_names("SAS3337")[0]
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIn("NO_MC_FOR_PYNAME", result["reason"])
        self.conn.execute("INSERT INTO mc_entries VALUES (2, 'Date', 'SAS3337', '2026-08-01', '', 'bad', '2026-08-10')")
        self.conn.commit()
        result = self.check_names("SAS3337")[0]
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIn("UNKNOWN_MC_DATES", result["mc_entries"][0]["reason"])

    def test_mc_and_run_num_combination(self):
        self.conn.execute("UPDATE mc_entries SET proposition_active = 'Never'")
        self.conn.commit()
        result = self.check_names("SAS3337")[0]
        self.assertEqual((result["run_status"], result["mc_entries"][0]["status"], result["status"]), ("RUNNING", "NOT_RUNNING", "NOT_RUNNING"))
        self.conn.execute("UPDATE mc_entries SET proposition_active = 'Always', prod_start_dt = ''")
        self.conn.execute("INSERT INTO requests VALUES (1, '3337', 'STOP', '9999-12-31', 'approved')")
        self.conn.commit()
        result = self.check_names("SAS3337")[0]
        self.assertEqual((result["run_status"], result["mc_entries"][0]["status"], result["status"]), ("NOT_RUNNING", "UNKNOWN", "NOT_RUNNING"))

    def test_duplicate_py_name_and_missing_sas_are_unknown(self):
        self.conn.execute("INSERT INTO mc_entries VALUES (2, 'Always', 'sas3337', '2026-08-01', '', '', '')")
        self.conn.execute("INSERT INTO mc_entries VALUES (3, 'Always', 'NO_NUMBER', '2026-08-01', '', '', '')")
        self.conn.commit()
        duplicate, no_sas = self.check_names("SAS3337", "NO_NUMBER")
        self.assertEqual(duplicate["status"], "UNKNOWN")
        self.assertIn("DUPLICATE_MC_PYNAME", duplicate["reason"])
        self.assertEqual(len(duplicate["mc_entries"]), 2)
        self.assertIn("UNKNOWN_RUN_NUM", no_sas["reason"])

    def test_always_requires_prod_start(self):
        self.conn.execute("UPDATE mc_entries SET prod_start_dt = ''")
        self.conn.commit()
        result = self.check_names("SAS3337")[0]
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIn("UNKNOWN_MC_PROD_START", result["mc_entries"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
