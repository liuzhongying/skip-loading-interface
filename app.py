from __future__ import annotations

import json
import mimetypes
import os
import re
import sqlite3
import sys
from io import BytesIO
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent
    BUNDLE_DIR = BASE_DIR


def configured_path(env_name: str, default: Path) -> Path:
    value = os.environ.get(env_name, "").strip()
    return Path(value) if value else default


DB_PATH = configured_path("SKIP_LOADING_DB_PATH", BASE_DIR / "data" / "skip_loading.db")
EXPORT_DIR = configured_path("SKIP_LOADING_EXPORT_DIR", BASE_DIR / "exports")
BACKUP_DIR = configured_path("SKIP_LOADING_BACKUP_DIR", DB_PATH.parent / "backups")
STATIC_DIR = BUNDLE_DIR / "static"

FAR_FUTURE = date(2099, 12, 31)
DATE_FORMAT = "%Y-%m-%d"
EXCEL_DATE_FORMAT = "dd mmm yyyy"
DATABASE_BUSY_MESSAGE = "Another user is saving. Please retry after a few seconds."
DAG_COLUMNS = [
    ("dag_id", "dag_id"),
    ("description", "description"),
    ("schedule_interval", "schedule_interval"),
    ("event_date_table", "event_date_table"),
    ("start_datetime", "start_datetime"),
    ("end_date", "end_date"),
    ("status", "status"),
    ("email", "email"),
    ("owner", "owner"),
    ("last_released_date", "last_released_date"),
    ("gcp_project_id", "gcp_project_id"),
    ("ad_group", "ADGroup"),
    ("machine_type", "machineType"),
    ("mount_bucket", "mountBucket"),
    ("image_version", "imageVersion"),
    ("request_type", "requestType"),
    ("num_workers", "numWorkers"),
    ("bucket_folder", "bucketFolder"),
    ("run_on_holiday", "run_on_holiday"),
    ("vm_alive_days", "VM_alive_days"),
    ("skip_run_base_completion_token", "skip_run_base_completion_token"),
    ("token_file_bucket", "token_file_bucket"),
    ("token_file_path_in_bucket", "token_file_path_in_bucket"),
    ("token_file_offset", "token_file_offset"),
    ("pega_night_batch_flag", "pega_night_batch_flag"),
    ("stop_successful_mail_ser", "stop_successful_mail_ser"),
    ("pega_intra_batch_flag", "pega_intra_batch_flag"),
    ("myfeed_reminder_flag", "myfeed_reminder_flag"),
]
DAG_REQUIRED_FIELDS = {
    "dag_id",
    "description",
    "schedule_interval",
    "start_datetime",
    "end_date",
    "status",
    "email",
    "owner",
    "gcp_project_id",
    "ad_group",
    "machine_type",
    "mount_bucket",
    "image_version",
    "request_type",
    "bucket_folder",
    "run_on_holiday",
    "skip_run_base_completion_token",
    "token_file_offset",
}
TASK_COLUMNS = [
    ("dag_id", "dag_id"),
    ("task_id", "task_id"),
    ("task_name", "task_name"),
    ("shell_command", "shell_command"),
    ("dataproc_bucket", "dataproc_bucket"),
    ("main_file_run_on_dataproc", "main_file_run_on_dataproc"),
    ("main_python_args", "main_python_args"),
    ("dependency_task", "dependency_task"),
    ("file_wait_bucket", "file_wait_bucket"),
    ("file_wait", "file_wait"),
    ("filewait_time_out_in_seconds", "filewait_time_out_in_seconds"),
    ("sensor_task_name", "sensor_task_name"),
    ("parent_dag", "parent_dag"),
    ("parent_task", "parent_task"),
    ("marker_task_name", "marker_task_name"),
    ("child_dag", "child_dag"),
    ("child_task_id", "child_task_id"),
    ("task_inactive_flag", "task_inactive_flag"),
    ("trigger_rule", "trigger_rule"),
    ("task_unique_key", "task_unique_key"),
    ("monthly_start_day", "monthly_start_day"),
    ("monthly_end_day", "monthly_end_day"),
    ("weekly_start_day", "weekly_start_day"),
    ("weekly_end_day", "weekly_end_day"),
]
TASK_REQUIRED_FIELDS = {
    "dag_id",
    "task_id",
    "task_name",
    "shell_command",
    "file_wait_bucket",
    "filewait_time_out_in_seconds",
}


def ensure_dirs() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def backup_database(batch_id: str) -> Path:
    ensure_dirs()
    backup_path = BACKUP_DIR / f"skip_loading_db_backup_{batch_id}.db"
    with sqlite3.connect(DB_PATH, timeout=30) as source:
        source.execute("PRAGMA busy_timeout = 30000")
        with sqlite3.connect(backup_path) as target:
            source.backup(target)
    return backup_path


def init_db() -> None:
    with connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS mc_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposition_active TEXT, py_name TEXT NOT NULL, py_label TEXT,
            prod_start_dt TEXT, eligibility_rule TEXT, start_date TEXT, end_date TEXT
        )""")
        if "py_label" not in {row["name"] for row in conn.execute("PRAGMA table_info(mc_entries)")}:
            conn.execute("ALTER TABLE mc_entries ADD COLUMN py_label TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mc_py_name ON mc_entries(py_name COLLATE NOCASE)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_num TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('STOP', 'RESUME')),
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                maker TEXT NOT NULL,
                input_date TEXT NOT NULL,
                checker TEXT,
                approval_date TEXT,
                remark TEXT NOT NULL,
                pod TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'exported')),
                reject_reason TEXT,
                export_batch_id TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                previous_request_id INTEGER
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_run_num ON requests(run_num)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dag_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dag_id TEXT NOT NULL,
                description TEXT NOT NULL,
                schedule_interval TEXT NOT NULL,
                event_date_table TEXT,
                start_datetime TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT NOT NULL,
                email TEXT NOT NULL,
                owner TEXT NOT NULL,
                last_released_date TEXT,
                gcp_project_id TEXT NOT NULL,
                ad_group TEXT NOT NULL,
                machine_type TEXT NOT NULL,
                mount_bucket TEXT NOT NULL,
                image_version TEXT NOT NULL,
                request_type TEXT NOT NULL,
                num_workers TEXT,
                bucket_folder TEXT NOT NULL,
                run_on_holiday TEXT NOT NULL,
                vm_alive_days TEXT,
                skip_run_base_completion_token TEXT NOT NULL,
                token_file_bucket TEXT,
                token_file_path_in_bucket TEXT,
                token_file_offset TEXT NOT NULL,
                pega_night_batch_flag TEXT,
                stop_successful_mail_ser TEXT,
                pega_intra_batch_flag TEXT,
                myfeed_reminder_flag TEXT,
                previous_entry_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        existing_dag_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(dag_entries)").fetchall()
        }
        if (
            "skip_run_base_completion_toke" in existing_dag_columns
            and "skip_run_base_completion_token" not in existing_dag_columns
        ):
            conn.execute(
                "ALTER TABLE dag_entries RENAME COLUMN skip_run_base_completion_toke TO skip_run_base_completion_token"
            )
            existing_dag_columns.remove("skip_run_base_completion_toke")
            existing_dag_columns.add("skip_run_base_completion_token")
        if "skip_run_base_completion_token" not in existing_dag_columns:
            conn.execute(
                "ALTER TABLE dag_entries ADD COLUMN skip_run_base_completion_token TEXT NOT NULL DEFAULT 'N'"
            )
            existing_dag_columns.add("skip_run_base_completion_token")
        if "previous_entry_id" not in existing_dag_columns:
            conn.execute("ALTER TABLE dag_entries ADD COLUMN previous_entry_id INTEGER")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dag_entries_dag_id ON dag_entries(dag_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dag_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                task_name TEXT NOT NULL,
                shell_command TEXT NOT NULL,
                dataproc_bucket TEXT,
                main_file_run_on_dataproc TEXT,
                main_python_args TEXT,
                dependency_task TEXT,
                file_wait_bucket TEXT NOT NULL,
                file_wait TEXT,
                filewait_time_out_in_seconds TEXT NOT NULL,
                sensor_task_name TEXT,
                parent_dag TEXT,
                parent_task TEXT,
                marker_task_name TEXT,
                child_dag TEXT,
                child_task_id TEXT,
                task_inactive_flag TEXT,
                trigger_rule TEXT,
                task_unique_key TEXT NOT NULL,
                monthly_start_day TEXT,
                monthly_end_day TEXT,
                weekly_start_day TEXT,
                weekly_end_day TEXT,
                previous_entry_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        existing_task_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(task_entries)").fetchall()
        }
        if (
            "filewait_time_out_in_secon" in existing_task_columns
            and "filewait_time_out_in_seconds" not in existing_task_columns
        ):
            conn.execute(
                "ALTER TABLE task_entries RENAME COLUMN filewait_time_out_in_secon TO filewait_time_out_in_seconds"
            )
            existing_task_columns.remove("filewait_time_out_in_secon")
            existing_task_columns.add("filewait_time_out_in_seconds")
        if "filewait_time_out_in_seconds" not in existing_task_columns:
            conn.execute(
                "ALTER TABLE task_entries ADD COLUMN filewait_time_out_in_seconds TEXT NOT NULL DEFAULT '0'"
            )
            existing_task_columns.add("filewait_time_out_in_seconds")
        if "previous_entry_id" not in existing_task_columns:
            conn.execute("ALTER TABLE task_entries ADD COLUMN previous_entry_id INTEGER")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_entries_unique_key ON task_entries(task_unique_key)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_entries_task_id ON task_entries(task_id)"
        )


def today() -> date:
    return date.today()


def parse_date(value: str, field: str) -> date:
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        raise ValueError(f"{field} must be YYYY-MM-DD")


def parse_excel_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Cannot parse Excel date: {text}")


def excel_date_value(value: str | None, field: str) -> date | str:
    if not value:
        return ""
    return parse_date(value, field)


def normalize_run_num(value: str) -> str:
    clean = value.strip()
    if not clean:
        raise ValueError("Run_Num is required")
    return clean


def require_text(payload: dict[str, Any], key: str, label: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"{label} is required")
    return value


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def latest_effective_request(conn: sqlite3.Connection, run_num: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM requests
        WHERE run_num = ?
          AND status IN ('approved', 'exported')
        ORDER BY id DESC
        LIMIT 1
        """,
        (run_num,),
    ).fetchone()


def latest_any_request(conn: sqlite3.Connection, run_num: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM requests
        WHERE run_num = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (run_num,),
    ).fetchone()


def current_status_from_row(row: sqlite3.Row | None) -> str:
    if row is None:
        return "NO_RECORD"
    if not row["end_date"]:
        return "STOPPED" if row["action"] == "STOP" else "RESUMED"
    end_date = parse_date(row["end_date"], "end_date")
    if row["action"] == "STOP" and end_date >= today():
        return "STOPPED"
    return "RESUMED"


def create_request(payload: dict[str, Any]) -> dict[str, Any]:
    run_num = normalize_run_num(str(payload.get("run_num", "")))
    action = require_text(payload, "action", "Action").upper()
    if action not in {"STOP", "RESUME"}:
        raise ValueError("Action must be STOP or RESUME")

    maker = require_text(payload, "maker", "Maker")
    created_by = str(payload.get("created_by") or maker).strip() or maker
    checker = str(payload.get("checker", "")).strip() or None
    pod = require_text(payload, "pod", "POD")
    remark = require_text(payload, "remark", "Remark")

    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        previous = latest_any_request(conn, run_num)
        latest_effective = latest_effective_request(conn, run_num)

        if action == "STOP":
            start = today()
            end = FAR_FUTURE
        else:
            if latest_effective is None or latest_effective["action"] != "STOP":
                raise ValueError("RESUME requires an existing current STOP record")
            start = parse_date(latest_effective["start_date"], "Start_Date")
            end = today() - timedelta(days=1)

        cursor = conn.execute(
            """
            INSERT INTO requests (
                run_num, action, start_date, end_date, maker, input_date,
                checker, remark, pod, status, created_by, created_at, updated_at,
                previous_request_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (
                run_num,
                action,
                start.isoformat(),
                end.isoformat(),
                maker,
                today().isoformat(),
                checker,
                remark,
                pod,
                created_by,
                now,
                now,
                previous["id"] if previous else None,
            ),
        )
        row = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return row_to_dict(row)


def list_requests(
    status: str | None = None,
    run_num: str | None = None,
    checker: str | None = None,
    pod: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if run_num:
        clauses.append("run_num = ?")
        params.append(run_num)
    if checker:
        clauses.append("LOWER(checker) = LOWER(?)")
        params.append(checker.strip())
    if pod:
        clauses.append("LOWER(pod) = LOWER(?)")
        params.append(pod.strip())

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM requests
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT 500
            """,
            params,
        ).fetchall()
        return [row_to_dict(row) for row in rows]


def get_history(run_num: str) -> dict[str, Any]:
    run_num = normalize_run_num(run_num)
    with connect() as conn:
        history = conn.execute(
            """
            SELECT *
            FROM requests
            WHERE run_num = ?
            ORDER BY created_at DESC, id DESC
            """,
            (run_num,),
        ).fetchall()
        latest = latest_effective_request(conn, run_num)
        return {
            "run_num": run_num,
            "current_status": current_status_from_row(latest),
            "current_record": row_to_dict(latest) if latest else None,
            "history": [row_to_dict(row) for row in history],
        }


def get_defaults(run_num: str | None = None, action: str | None = None) -> dict[str, Any]:
    normalized_action = (action or "STOP").upper()
    if normalized_action not in {"STOP", "RESUME"}:
        raise ValueError("Action must be STOP or RESUME")

    if normalized_action == "STOP":
        return {
            "action": "STOP",
            "start_date": today().isoformat(),
            "end_date": FAR_FUTURE.isoformat(),
            "message": "STOP starts today and stays active until 2099-12-31.",
        }

    run_num_value = normalize_run_num(run_num or "")
    with connect() as conn:
        latest = latest_effective_request(conn, run_num_value)
        if latest is None or latest["action"] != "STOP":
            return {
                "action": "RESUME",
                "start_date": "",
                "end_date": (today() - timedelta(days=1)).isoformat(),
                "message": "RESUME requires an existing current STOP record.",
            }
        return {
            "action": "RESUME",
            "start_date": latest["start_date"],
            "end_date": (today() - timedelta(days=1)).isoformat(),
            "message": "RESUME keeps the current STOP Start_Date and sets End_Date to yesterday.",
        }


def normalize_header(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def import_history_excel(file_bytes: bytes) -> dict[str, Any]:
    workbook = load_workbook(BytesIO(file_bytes), data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Excel is empty")

    headers = {normalize_header(value): index for index, value in enumerate(rows[0])}

    def cell(row: tuple[Any, ...], *names: str) -> Any:
        for name in names:
            index = headers.get(normalize_header(name))
            if index is not None and index < len(row):
                return row[index]
        return ""

    latest_by_run_num: dict[str, dict[str, Any]] = {}
    skipped_blank_run_num = 0
    for row in rows[1:]:
        run_num = str(cell(row, "Run_Num", "Run Num", "Run_Number") or "").strip()
        if not run_num:
            skipped_blank_run_num += 1
            continue

        start_date = parse_excel_date(cell(row, "Start_Date", "Start Date"))
        end_date = parse_excel_date(cell(row, "End_Date", "End Date"))
        input_date = parse_excel_date(cell(row, "Input_Date", "Input Date"))
        approval_date = parse_excel_date(cell(row, "Approval_Date", "Approval Date"))

        action = "RESUME" if end_date is not None and end_date <= today() else "STOP"
        latest_by_run_num[run_num] = {
            "run_num": run_num,
            "action": action,
            "start_date": start_date.isoformat() if start_date else "",
            "end_date": end_date.isoformat() if end_date else "",
            "maker": str(cell(row, "Maker") or "").strip(),
            "input_date": input_date.isoformat() if input_date else "",
            "checker": str(cell(row, "Checker") or "").strip() or None,
            "approval_date": approval_date.isoformat() if approval_date else None,
            "remark": str(cell(row, "REMARK", "Remark") or "").strip(),
            "pod": str(cell(row, "POD") or "").strip(),
        }

    now = datetime.now().isoformat(timespec="seconds")
    imported_ids: list[int] = []
    with connect() as conn:
        for item in latest_by_run_num.values():
            previous = latest_any_request(conn, item["run_num"])
            cursor = conn.execute(
                """
                INSERT INTO requests (
                    run_num, action, start_date, end_date, maker, input_date,
                    checker, approval_date, remark, pod, status, created_by,
                    created_at, updated_at, previous_request_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?, ?, ?, ?)
                """,
                (
                    item["run_num"],
                    item["action"],
                    item["start_date"],
                    item["end_date"],
                    item["maker"],
                    item["input_date"],
                    item["checker"],
                    item["approval_date"],
                    item["remark"],
                    item["pod"],
                    item["maker"] or "import_history",
                    now,
                    now,
                    previous["id"] if previous else None,
                ),
            )
            imported_ids.append(cursor.lastrowid)

    return {
        "imported_count": len(imported_ids),
        "skipped_blank_run_num": skipped_blank_run_num,
        "imported_ids": imported_ids,
    }


def normalize_optional_text(payload: dict[str, Any], key: str) -> str:
    return str(payload.get(key, "")).strip()


def missing_required_dag_fields(values: dict[str, str]) -> list[str]:
    return [label for key, label in DAG_COLUMNS if key in DAG_REQUIRED_FIELDS and not values[key]]


def dag_values_match(row: sqlite3.Row | None, values: dict[str, str]) -> bool:
    if row is None:
        return False
    return all(str(row[key] or "") == values[key] for key, _label in DAG_COLUMNS)


def create_dag_entry(payload: dict[str, Any]) -> dict[str, Any]:
    values = {key: normalize_optional_text(payload, key) for key, _label in DAG_COLUMNS}
    missing = missing_required_dag_fields(values)
    if missing:
        raise ValueError(f"Required DAG fields missing: {', '.join(missing)}")

    now = datetime.now().isoformat(timespec="seconds")
    keys = [key for key, _label in DAG_COLUMNS]
    columns_sql = ", ".join(keys)
    placeholders = ", ".join("?" for _ in keys)
    with connect() as conn:
        previous = latest_dag_entry(conn, values["dag_id"])
        cursor = conn.execute(
            f"""
            INSERT INTO dag_entries (
                {columns_sql}, previous_entry_id, created_at, updated_at
            )
            VALUES ({placeholders}, ?, ?, ?)
            """,
            (
                *[values[key] for key in keys],
                previous["id"] if previous else None,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM dag_entries WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return row_to_dict(row)


def import_dag_excel(file_bytes: bytes) -> dict[str, Any]:
    workbook = load_workbook(BytesIO(file_bytes), data_only=True)
    sheet = workbook["DAG"] if "DAG" in workbook.sheetnames else workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Excel is empty")

    header_row_index = 0
    headers: dict[str, int] = {}
    for index, candidate in enumerate(rows[:20]):
        candidate_headers = {
            normalize_header(value): column_index
            for column_index, value in enumerate(candidate)
            if normalize_header(value)
        }
        if "dag_id" in candidate_headers:
            header_row_index = index
            headers = candidate_headers
            break
    if not headers:
        raise ValueError("DAG sheet header row not found. Expected a dag_id column.")

    aliases = {
        "ad_group": ("adgroup", "ad_group"),
        "machine_type": ("machinetype", "machine_type"),
        "mount_bucket": ("mountbucket", "mount_bucket"),
        "image_version": ("imageversion", "image_version"),
        "request_type": ("requesttype", "request_type"),
        "num_workers": ("numworkers", "num_workers"),
        "bucket_folder": ("bucketfolder", "bucket_folder"),
        "vm_alive_days": ("vm_alive_days", "vm_alive_day", "VM_alive_days"),
        "skip_run_base_completion_token": (
            "skip_run_base_completion_token",
            "skip_run_base_completion_toke",
            "skip_run_base_completion_tokens",
        ),
        "stop_successful_mail_ser": (
            "stop_successful_mail_ser",
            "stop_successful_mail_server",
            "stop_successful_mail_service",
        ),
    }

    def cell(row: tuple[Any, ...], *names: str) -> Any:
        for name in names:
            index = headers.get(normalize_header(name))
            if index is not None and index < len(row):
                return row[index]
        return ""

    imported_ids: list[int] = []
    skipped_blank_dag_id = 0
    skipped_unchanged = 0
    failed_rows: list[dict[str, Any]] = []

    with connect() as conn:
        for row_number, row in enumerate(rows[header_row_index + 1 :], start=header_row_index + 2):
            values = {
                key: cell_text(cell(row, key, label, *aliases.get(key, ())))
                for key, label in DAG_COLUMNS
            }
            if not values["skip_run_base_completion_token"]:
                values["skip_run_base_completion_token"] = "N"
            if not values["dag_id"]:
                skipped_blank_dag_id += 1
                continue

            missing = missing_required_dag_fields(values)
            if missing:
                failed_rows.append(
                    {
                        "row": row_number,
                        "dag_id": values["dag_id"],
                        "error": f"Missing required fields: {', '.join(missing)}",
                    }
                )
                continue

            previous = latest_dag_entry(conn, values["dag_id"])
            if dag_values_match(previous, values):
                skipped_unchanged += 1
                continue

            now = datetime.now().isoformat(timespec="seconds")
            keys = [key for key, _label in DAG_COLUMNS]
            columns_sql = ", ".join(keys)
            placeholders = ", ".join("?" for _ in keys)
            cursor = conn.execute(
                f"""
                INSERT INTO dag_entries (
                    {columns_sql}, previous_entry_id, created_at, updated_at
                )
                VALUES ({placeholders}, ?, ?, ?)
                """,
                (
                    *[values[key] for key in keys],
                    previous["id"] if previous else None,
                    now,
                    now,
                ),
            )
            imported_ids.append(cursor.lastrowid)

    return {
        "sheet": sheet.title,
        "header_row": header_row_index + 1,
        "imported_count": len(imported_ids),
        "skipped_blank_dag_id": skipped_blank_dag_id,
        "skipped_unchanged": skipped_unchanged,
        "failed_count": len(failed_rows),
        "failed_rows": failed_rows[:10],
        "available_headers": list(headers.keys()),
        "imported_ids": imported_ids,
    }


def latest_dag_entry(conn: sqlite3.Connection, dag_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM dag_entries
        WHERE LOWER(dag_id) = LOWER(?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (dag_id.strip(),),
    ).fetchone()


def normalized_page(value: str | None) -> int:
    try:
        page = int(value or "1")
    except ValueError:
        return 1
    return max(page, 1)


def paginated_payload(rows: list[sqlite3.Row], total: int, page: int, page_size: int) -> dict[str, Any]:
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "rows": [row_to_dict(row) for row in rows],
        "total": total,
        "page": min(page, total_pages),
        "page_size": page_size,
        "total_pages": total_pages,
    }


def list_dag_entries(dag_id: str | None = None, page: int = 1, page_size: int = 3) -> dict[str, Any]:
    count_clauses: list[str] = []
    row_clauses: list[str] = []
    params: list[Any] = []
    if dag_id:
        count_clauses.append("LOWER(dag_id) LIKE LOWER(?)")
        row_clauses.append("LOWER(d.dag_id) LIKE LOWER(?)")
        params.append(f"%{dag_id.strip()}%")

    count_where = f"WHERE {' AND '.join(count_clauses)}" if count_clauses else ""
    row_where = f"WHERE {' AND '.join(row_clauses)}" if row_clauses else ""
    with connect() as conn:
        total = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM (
                SELECT LOWER(dag_id) AS dag_key
                FROM dag_entries
                {count_where}
                GROUP BY LOWER(dag_id)
            ) unique_dags
            """,
            params,
        ).fetchone()["count"]
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(max(page, 1), total_pages)
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""
            SELECT d.*
            FROM dag_entries d
            JOIN (
                SELECT LOWER(dag_id) AS dag_key, MAX(id) AS max_id
                FROM dag_entries
                GROUP BY LOWER(dag_id)
            ) latest ON latest.max_id = d.id
            {row_where}
            ORDER BY d.created_at DESC, d.id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
        return paginated_payload(rows, total, page, page_size)


def get_dag_history(dag_id: str, page: int = 1, page_size: int = 3) -> dict[str, Any]:
    dag_id = require_text({"dag_id": dag_id}, "dag_id", "dag_id")
    with connect() as conn:
        latest = latest_dag_entry(conn, dag_id)
        total = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM dag_entries
            WHERE LOWER(dag_id) = LOWER(?)
            """,
            (dag_id,),
        ).fetchone()["count"]
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(max(page, 1), total_pages)
        offset = (page - 1) * page_size
        history = conn.execute(
            """
            SELECT *
            FROM dag_entries
            WHERE LOWER(dag_id) = LOWER(?)
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (dag_id, page_size, offset),
        ).fetchall()
        history_items = [dag_history_row_to_dict(conn, row) for row in history]
        return {
            "dag_id": dag_id,
            "current_record": row_to_dict(latest) if latest else None,
            "history": history_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }


def previous_dag_entry(conn: sqlite3.Connection, row: sqlite3.Row) -> sqlite3.Row | None:
    previous_id = row["previous_entry_id"] if "previous_entry_id" in row.keys() else None
    if previous_id:
        previous = conn.execute(
            "SELECT * FROM dag_entries WHERE id = ?",
            (previous_id,),
        ).fetchone()
        if previous:
            return previous
    return conn.execute(
        """
        SELECT *
        FROM dag_entries
        WHERE LOWER(dag_id) = LOWER(?)
          AND id < ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (row["dag_id"], row["id"]),
    ).fetchone()


def dag_history_row_to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    item = row_to_dict(row)
    previous = previous_dag_entry(conn, row)
    if previous is None:
        item["changes"] = [
            {
                "field": "record",
                "label": "Record",
                "old": "",
                "new": "Created",
            }
        ]
        return item

    changes: list[dict[str, str]] = []
    for key, label in DAG_COLUMNS:
        old = str(previous[key] or "")
        new = str(row[key] or "")
        if old != new:
            changes.append(
                {
                    "field": key,
                    "label": label,
                    "old": old,
                    "new": new,
                }
            )
    item["changes"] = changes
    return item


def export_dag_excel() -> dict[str, Any]:
    batch_id = datetime.now().strftime("dag-export-%Y%m%d-%H%M%S")
    output_path = EXPORT_DIR / f"dag_scheduler_{batch_id}.xlsx"

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.*
            FROM dag_entries d
            JOIN (
                SELECT LOWER(dag_id) AS dag_key, MAX(id) AS max_id
                FROM dag_entries
                GROUP BY LOWER(dag_id)
            ) latest ON latest.max_id = d.id
            ORDER BY d.dag_id
            """
        ).fetchall()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "DAG"
    headers = [label for _key, label in DAG_COLUMNS]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")

    for row in rows:
        sheet.append([row[key] or "" for key, _label in DAG_COLUMNS])

    for index, (_key, label) in enumerate(DAG_COLUMNS, start=1):
        width = min(max(len(label) + 4, 14), 34)
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = width

    if rows:
        table_ref = f"A1:{sheet.cell(row=len(rows) + 1, column=len(headers)).coordinate}"
        table = Table(displayName="DAGTable", ref=table_ref)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        sheet.add_table(table)

    workbook.save(output_path)
    return {
        "batch_id": batch_id,
        "file": str(output_path),
        "record_count": len(rows),
    }


def missing_required_task_fields(values: dict[str, str]) -> list[str]:
    return [label for key, label in TASK_COLUMNS if key in TASK_REQUIRED_FIELDS and not values[key]]


def calculated_task_unique_key(values: dict[str, str]) -> str:
    existing = values.get("task_unique_key", "").strip()
    if existing:
        return existing
    dag_id = values.get("dag_id", "").strip()
    task_id = values.get("task_id", "").strip()
    return f"{dag_id}||{task_id}" if dag_id or task_id else ""


def task_values_match(row: sqlite3.Row | None, values: dict[str, str]) -> bool:
    if row is None:
        return False
    return all(str(row[key] or "") == values[key] for key, _label in TASK_COLUMNS)


def latest_task_entry(conn: sqlite3.Connection, task_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM task_entries
        WHERE LOWER(task_id) = LOWER(?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (task_id.strip(),),
    ).fetchone()


def create_task_entry(payload: dict[str, Any]) -> dict[str, Any]:
    values = {key: normalize_optional_text(payload, key) for key, _label in TASK_COLUMNS}
    missing = missing_required_task_fields(values)
    if missing:
        raise ValueError(f"Required TASKS fields missing: {', '.join(missing)}")
    values["task_unique_key"] = calculated_task_unique_key(values)

    now = datetime.now().isoformat(timespec="seconds")
    keys = [key for key, _label in TASK_COLUMNS]
    columns_sql = ", ".join(keys)
    placeholders = ", ".join("?" for _ in keys)
    with connect() as conn:
        previous = latest_task_entry(conn, values["task_id"])
        cursor = conn.execute(
            f"""
            INSERT INTO task_entries (
                {columns_sql}, previous_entry_id, created_at, updated_at
            )
            VALUES ({placeholders}, ?, ?, ?)
            """,
            (
                *[values[key] for key in keys],
                previous["id"] if previous else None,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM task_entries WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return row_to_dict(row)


def import_tasks_excel(file_bytes: bytes) -> dict[str, Any]:
    workbook = load_workbook(BytesIO(file_bytes), data_only=True)
    sheet = workbook["TASKS"] if "TASKS" in workbook.sheetnames else workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Excel is empty")

    headers = {normalize_header(value): index for index, value in enumerate(rows[0])}

    aliases = {
        "filewait_time_out_in_seconds": (
            "filewait_time_out_in_seconds",
            "filewait_time_out_in_secon",
        ),
        "sensor_task_name": ("sensor_task_name", "sensor_task_na"),
        "parent_dag": ("parent_dag", "parent_dag_"),
        "parent_task": ("parent_task", "parent_task_"),
        "marker_task_name": ("marker_task_name", "marker_task_nar"),
        "child_dag": ("child_dag", "child_dag_"),
        "weekly_start_day": ("weekly_start_day", "weekly_start_da"),
    }

    def cell(row: tuple[Any, ...], *names: str) -> Any:
        for name in names:
            index = headers.get(normalize_header(name))
            if index is not None and index < len(row):
                return row[index]
        return ""

    imported_ids: list[int] = []
    skipped_blank_task = 0
    skipped_unchanged = 0
    failed_rows: list[dict[str, Any]] = []

    with connect() as conn:
        for row_number, row in enumerate(rows[1:], start=2):
            values = {
                key: cell_text(cell(row, key, label, *aliases.get(key, ())))
                for key, label in TASK_COLUMNS
            }
            if not values["dag_id"] and not values["task_id"]:
                skipped_blank_task += 1
                continue

            missing = missing_required_task_fields(values)
            if missing:
                failed_rows.append(
                    {
                        "row": row_number,
                        "task_id": values["task_id"],
                        "error": f"Missing required fields: {', '.join(missing)}",
                    }
                )
                continue
            values["task_unique_key"] = calculated_task_unique_key(values)

            previous = latest_task_entry(conn, values["task_id"])
            if task_values_match(previous, values):
                skipped_unchanged += 1
                continue

            now = datetime.now().isoformat(timespec="seconds")
            keys = [key for key, _label in TASK_COLUMNS]
            columns_sql = ", ".join(keys)
            placeholders = ", ".join("?" for _ in keys)
            cursor = conn.execute(
                f"""
                INSERT INTO task_entries (
                    {columns_sql}, previous_entry_id, created_at, updated_at
                )
                VALUES ({placeholders}, ?, ?, ?)
                """,
                (
                    *[values[key] for key in keys],
                    previous["id"] if previous else None,
                    now,
                    now,
                ),
            )
            imported_ids.append(cursor.lastrowid)

    return {
        "sheet": sheet.title,
        "imported_count": len(imported_ids),
        "skipped_blank_task": skipped_blank_task,
        "skipped_unchanged": skipped_unchanged,
        "failed_count": len(failed_rows),
        "failed_rows": failed_rows[:10],
        "imported_ids": imported_ids,
    }


def list_task_entries(task_id: str | None = None, page: int = 1, page_size: int = 3) -> dict[str, Any]:
    count_clauses: list[str] = []
    row_clauses: list[str] = []
    params: list[Any] = []
    if task_id:
        count_clauses.append("LOWER(task_id) LIKE LOWER(?)")
        row_clauses.append("LOWER(t.task_id) LIKE LOWER(?)")
        params.append(f"%{task_id.strip()}%")

    count_where = f"WHERE {' AND '.join(count_clauses)}" if count_clauses else ""
    row_where = f"WHERE {' AND '.join(row_clauses)}" if row_clauses else ""
    with connect() as conn:
        total = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM (
                SELECT LOWER(task_id) AS task_key
                FROM task_entries
                {count_where}
                GROUP BY LOWER(task_id)
            ) unique_tasks
            """,
            params,
        ).fetchone()["count"]
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(max(page, 1), total_pages)
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""
            SELECT t.*
            FROM task_entries t
            JOIN (
                SELECT LOWER(task_id) AS task_key, MAX(id) AS max_id
                FROM task_entries
                GROUP BY LOWER(task_id)
            ) latest ON latest.max_id = t.id
            {row_where}
            ORDER BY t.created_at DESC, t.id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
        return paginated_payload(rows, total, page, page_size)


def get_task_history(task_id: str, page: int = 1, page_size: int = 3) -> dict[str, Any]:
    task_id = require_text({"task_id": task_id}, "task_id", "task_id")
    with connect() as conn:
        latest = latest_task_entry(conn, task_id)
        total = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM task_entries
            WHERE LOWER(task_id) = LOWER(?)
            """,
            (task_id,),
        ).fetchone()["count"]
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(max(page, 1), total_pages)
        offset = (page - 1) * page_size
        history = conn.execute(
            """
            SELECT *
            FROM task_entries
            WHERE LOWER(task_id) = LOWER(?)
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (task_id, page_size, offset),
        ).fetchall()
        history_items = [task_history_row_to_dict(conn, row) for row in history]
        return {
            "task_id": task_id,
            "current_record": row_to_dict(latest) if latest else None,
            "history": history_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }


def previous_task_entry(conn: sqlite3.Connection, row: sqlite3.Row) -> sqlite3.Row | None:
    previous_id = row["previous_entry_id"] if "previous_entry_id" in row.keys() else None
    if previous_id:
        previous = conn.execute(
            "SELECT * FROM task_entries WHERE id = ?",
            (previous_id,),
        ).fetchone()
        if previous:
            return previous
    return conn.execute(
        """
        SELECT *
        FROM task_entries
        WHERE LOWER(task_id) = LOWER(?)
          AND id < ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (row["task_id"], row["id"]),
    ).fetchone()


def task_history_row_to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    item = row_to_dict(row)
    previous = previous_task_entry(conn, row)
    if previous is None:
        item["changes"] = [
            {
                "field": "record",
                "label": "Record",
                "old": "",
                "new": "Created",
            }
        ]
        return item

    changes: list[dict[str, str]] = []
    for key, label in TASK_COLUMNS:
        old = str(previous[key] or "")
        new = str(row[key] or "")
        if old != new:
            changes.append(
                {
                    "field": key,
                    "label": label,
                    "old": old,
                    "new": new,
                }
            )
    item["changes"] = changes
    return item


def export_tasks_excel() -> dict[str, Any]:
    batch_id = datetime.now().strftime("tasks-export-%Y%m%d-%H%M%S")
    output_path = EXPORT_DIR / f"tasks_{batch_id}.xlsx"

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.*
            FROM task_entries t
            JOIN (
                SELECT LOWER(task_id) AS task_key, MAX(id) AS max_id
                FROM task_entries
                GROUP BY LOWER(task_id)
            ) latest ON latest.max_id = t.id
            ORDER BY t.task_id
            """
        ).fetchall()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "TASKS"
    headers = [label for _key, label in TASK_COLUMNS]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")

    for row in rows:
        sheet.append([row[key] or "" for key, _label in TASK_COLUMNS])

    for index, (_key, label) in enumerate(TASK_COLUMNS, start=1):
        width = min(max(len(label) + 4, 14), 40)
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = width

    if rows:
        table_ref = f"A1:{sheet.cell(row=len(rows) + 1, column=len(headers)).coordinate}"
        table = Table(displayName="TasksTable", ref=table_ref)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        sheet.add_table(table)

    workbook.save(output_path)
    return {
        "batch_id": batch_id,
        "file": str(output_path),
        "record_count": len(rows),
    }


def run_nums_from_task_id(task_id: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"RDP(\d+)", task_id or "", flags=re.IGNORECASE)))


def run_nums_from_mc_name(py_name: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"SAS([0-9]+)", py_name or "", flags=re.IGNORECASE)))


def running_date(value: Any) -> date | None:
    text = str(value or "").strip()
    try:
        parts = text.split(",")
        if len(parts) >= 3:
            return date(*(int(part.strip()) for part in parts[:3]))
        return date.fromisoformat(text[:10])
    except (ValueError, TypeError, OverflowError):
        return None


def mc_validity(row: sqlite3.Row, current_day: date) -> dict[str, Any]:
    item = {key: row[key] for key in ("id", "py_name", "proposition_active", "prod_start_dt", "start_date", "end_date")}
    item["py_label"] = row["py_label"] if "py_label" in row.keys() else None
    mode = str(row["proposition_active"] or "").strip().lower()
    if mode == "never":
        item.update(status="NOT_RUNNING", reason="MC_NEVER: proposition is inactive.")
        return item
    if mode not in ("always", "date"):
        item.update(status="UNKNOWN", reason="UNKNOWN_MC_MODE: proposition status is missing or invalid.")
        return item
    prod_start = running_date(row["prod_start_dt"])
    if prod_start is None:
        item.update(status="UNKNOWN", reason="UNKNOWN_MC_PROD_START: production start date is missing or invalid.")
        return item
    if current_day < prod_start:
        item.update(status="NOT_RUNNING", reason=f"MC_NOT_STARTED: production starts on {prod_start}.")
        return item
    if mode == "date":
        start, end = running_date(row["start_date"]), running_date(row["end_date"])
        if start is None or end is None or start > end:
            item.update(status="UNKNOWN", reason="UNKNOWN_MC_DATES: date range is missing, invalid or inverted.")
            return item
        if current_day < start:
            item.update(status="NOT_RUNNING", reason=f"MC_NOT_STARTED: proposition starts on {start}.")
            return item
        if current_day > end:
            item.update(status="NOT_RUNNING", reason=f"MC_EXPIRED: proposition ended on {end}.")
            return item
    item.update(status="RUNNING", reason="MC_VALID: proposition and production start dates are effective.")
    return item


def run_num_statuses(conn: sqlite3.Connection, run_nums: list[str], current_day: date) -> list[dict[str, Any]]:
    tasks = conn.execute("""
        SELECT t.* FROM task_entries t JOIN
        (SELECT MAX(id) AS id FROM task_entries GROUP BY LOWER(task_id)) latest
        ON t.id = latest.id ORDER BY t.task_id
    """).fetchall()
    dags = conn.execute("""
        SELECT d.* FROM dag_entries d JOIN
        (SELECT MAX(id) AS id FROM dag_entries GROUP BY LOWER(dag_id)) latest
        ON d.id = latest.id
    """).fetchall()
    dag_by_id = {row["dag_id"].lower(): row for row in dags}
    by_run: dict[str, list[sqlite3.Row]] = {}
    for task in tasks:
        for run_num in run_nums_from_task_id(task["task_id"]):
            by_run.setdefault(run_num, []).append(task)
    results = []
    for run_num in run_nums:
        skip = latest_effective_request(conn, run_num)
        result: dict[str, Any] = {"run_num": run_num, "status": "", "reason": "", "tasks": [],
            "skip_loading": None if skip is None else {"id": skip["id"], "action": skip["action"], "end_date": skip["end_date"], "status": skip["status"]}}
        if skip is not None and skip["action"] == "STOP":
            end = running_date(skip["end_date"])
            if end is None:
                result.update(status="UNKNOWN", reason="UNKNOWN_SKIP_END_DATE: STOP end date is invalid.")
                results.append(result)
                continue
            if end.year == 9999 or end >= current_day:
                result.update(status="NOT_RUNNING", reason="STOPPED_BY_SKIP_LOADING: effective STOP has not expired.")
                results.append(result)
                continue
        for task in by_run.get(run_num, []):
            item = {"task_id": task["task_id"], "dag_id": task["dag_id"], "task_version_id": task["id"], "status": "", "reason": ""}
            dag = dag_by_id.get(str(task["dag_id"]).lower())
            if str(task["task_inactive_flag"] or "").strip().upper() == "Y":
                item.update(status="NOT_RUNNING_TASK_INACTIVE", reason="Latest task version is inactive.")
            elif dag is None:
                item.update(status="NO_DAG_FOR_TASK", reason="No DAG found for the task.")
            else:
                item["dag_version_id"] = dag["id"]
                start, end = running_date(dag["start_datetime"]), running_date(dag["end_date"])
                if start is None or end is None or start > end:
                    item.update(status="UNKNOWN_DAG_DATES", reason="DAG dates are missing, invalid, or inverted.")
                elif current_day < start:
                    item.update(status="NOT_RUNNING_DAG_NOT_STARTED", reason=f"DAG starts on {start}.")
                elif current_day > end:
                    item.update(status="NOT_RUNNING_DAG_EXPIRED", reason=f"DAG expired after {end}.")
                else:
                    days_text = str(dag["vm_alive_days"] or "").strip()
                    try:
                        if not days_text:
                            item.update(status="RUNNING", reason="DAG is valid; blank VM_alive_days means no VM expiry.")
                        elif not re.fullmatch(r"[0-9]+", days_text) or int(days_text) < 1:
                            raise ValueError()
                        else:
                            vm_end = start + timedelta(days=int(days_text) - 1)
                            item["vm_end_day"] = vm_end.isoformat()
                            if current_day <= vm_end:
                                item.update(status="RUNNING", reason=f"DAG and VM are valid through {vm_end}.")
                            else:
                                item.update(status="NOT_RUNNING_VM_EXPIRED", reason=f"VM expired after {vm_end}.")
                    except (ValueError, OverflowError):
                        item.update(status="UNKNOWN_VM_VALIDITY", reason="VM_alive_days is missing or invalid.")
            result["tasks"].append(item)
        if not result["tasks"]:
            result.update(status="NOT_RUNNING", reason="NO_TASK_FOR_RUN_NUM: no matching task found.")
        elif any(item["status"] == "RUNNING" for item in result["tasks"]):
            result.update(status="RUNNING", reason="At least one matching task is running.")
        elif any(item["status"].startswith("UNKNOWN") for item in result["tasks"]):
            result.update(status="UNKNOWN", reason="No task is confirmed running; at least one task has unknown validity.")
        else:
            result.update(status="NOT_RUNNING", reason="All matching tasks are not running.")
        results.append(result)
    return results

def check_running_status(payload: dict[str, Any]) -> dict[str, Any]:
    values = payload.get("py_names")
    if not isinstance(values, list) or not values or len(values) > 500:
        raise ValueError("Enter between 1 and 500 pyName values")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Each pyName must be a non-empty string")
    names = list(dict.fromkeys(value.strip() for value in values))
    current_day = today()
    with closing(sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        rows = conn.execute("SELECT * FROM mc_entries ORDER BY id").fetchall()
        by_name: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            by_name.setdefault(row["py_name"].casefold(), []).append(row)
        run_nums = list(dict.fromkeys(num for name in names for num in run_nums_from_mc_name(name)))
        base = {row["run_num"]: row for row in run_num_statuses(conn, run_nums, current_day)}
        results = []
        for name in names:
            matched = by_name.get(name.casefold(), [])
            numbers = run_nums_from_mc_name(name)
            result: dict[str, Any] = {"py_name": name, "py_label": (matched[0]["py_label"] if len(matched) == 1 and "py_label" in matched[0].keys() else None), "run_num": numbers[0] if len(numbers) == 1 else None,
                                      "status": "UNKNOWN", "reason": "", "run_status": None,
                                      "run_reason": None, "tasks": [], "skip_loading": None, "mc_entries": []}
            if not matched:
                result["reason"] = "NO_MC_FOR_PYNAME: no matching MC entry found."
            elif len(matched) > 1:
                result["reason"] = "DUPLICATE_MC_PYNAME: expected exactly one MC record for this pyName."
                result["mc_entries"] = [mc_validity(row, current_day) for row in matched]
            elif len(numbers) != 1:
                result["reason"] = "UNKNOWN_RUN_NUM: pyName must contain exactly one distinct SAS Run_Num."
                result["mc_entries"] = [mc_validity(row, current_day) for row in matched]
            else:
                run = base[numbers[0]]
                result.update(run_status=run["status"], run_reason=run["reason"], tasks=run["tasks"], skip_loading=run["skip_loading"])
                result["mc_entries"] = [mc_validity(row, current_day) for row in matched]
                for item in result["mc_entries"]:
                    item["combined_status"] = combine_running_status(run["status"], item["status"])
                result["status"] = result["mc_entries"][0]["combined_status"]
                result["reason"] = f"Run_Num {numbers[0]}: {run['status']} — {run['reason']}"
            results.append(result)
    return {"today": current_day.isoformat(), "results": results}


def combine_running_status(run_status: str, mc_status: str) -> str:
    if "NOT_RUNNING" in (run_status, mc_status):
        return "NOT_RUNNING"
    if "UNKNOWN" in (run_status, mc_status):
        return "UNKNOWN"
    return "RUNNING"


def task_json_summary(task_row: sqlite3.Row, latest_dags: dict[str, sqlite3.Row]) -> dict[str, Any]:
    dag_row = latest_dags.get(str(task_row["dag_id"] or "").lower())
    latest_dag = None
    if dag_row:
        latest_dag = {
            "dag_id": dag_row["dag_id"],
            "start_datetime": dag_row["start_datetime"],
            "end_date": dag_row["end_date"],
            "VM_alive_days": dag_row["vm_alive_days"],
            "latest_dag_version_id": dag_row["id"],
        }
    return {
        "task_id": task_row["task_id"],
        "dag_id": task_row["dag_id"],
        "task_inactive_flag": task_row["task_inactive_flag"],
        "latest_task_version_id": task_row["id"],
        "latest_dag": latest_dag,
    }


def export_database_json() -> dict[str, Any]:
    batch_id = datetime.now().strftime("db-json-%Y%m%d-%H%M%S")
    output_path = EXPORT_DIR / f"use_case_control_{batch_id}.json"

    with connect() as conn:
        skip_rows = effective_export_rows(conn)
        task_rows = conn.execute(
            """
            SELECT t.*
            FROM task_entries t
            JOIN (
                SELECT LOWER(task_id) AS task_key, MAX(id) AS max_id
                FROM task_entries
                GROUP BY LOWER(task_id)
            ) latest ON latest.max_id = t.id
            ORDER BY t.task_id
            """
        ).fetchall()
        dag_rows = conn.execute(
            """
            SELECT d.*
            FROM dag_entries d
            JOIN (
                SELECT LOWER(dag_id) AS dag_key, MAX(id) AS max_id
                FROM dag_entries
                GROUP BY LOWER(dag_id)
            ) latest ON latest.max_id = d.id
            """
        ).fetchall()

    latest_dags = {str(row["dag_id"]).lower(): row for row in dag_rows}
    data: dict[str, Any] = {}
    matched_task_count = 0
    skip_run_nums = {str(row["run_num"]) for row in skip_rows}
    for skip_row in skip_rows:
        run_num = str(skip_row["run_num"])
        matched_tasks = []
        for task_row in task_rows:
            task_id = str(task_row["task_id"] or "")
            if run_num not in task_id:
                continue
            matched_tasks.append(task_json_summary(task_row, latest_dags))

        matched_task_count += len(matched_tasks)
        data[run_num] = {
            "skip_loading_latest_effective": {
                "action": skip_row["action"],
                "end_date": skip_row["end_date"],
                "status": skip_row["status"],
            },
            "matched_tasks": matched_tasks,
        }

    task_only_data: dict[str, Any] = {}
    for task_row in task_rows:
        task_id = str(task_row["task_id"] or "")
        for run_num in run_nums_from_task_id(task_id):
            if run_num in skip_run_nums:
                continue
            task_only_data.setdefault(
                run_num,
                {
                    "skip_loading_latest_effective": None,
                    "matched_tasks": [],
                },
            )["matched_tasks"].append(task_json_summary(task_row, latest_dags))

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "today": today().isoformat(),
        "run_nums": list(data.keys()),
        "task_only_run_nums": list(task_only_data.keys()),
        "data": data,
        "task_only_data": task_only_data,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "batch_id": batch_id,
        "file": str(output_path),
        "run_num_count": len(data),
        "task_only_run_num_count": len(task_only_data),
        "matched_task_count": matched_task_count,
    }


def decide_request(request_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    decision = require_text(payload, "decision", "Decision").lower()
    if decision not in {"approve", "reject"}:
        raise ValueError("Decision must be approve or reject")
    checker = require_text(payload, "checker", "Checker")
    reject_reason = str(payload.get("reject_reason", "")).strip() or None

    status = "approved" if decision == "approve" else "rejected"
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)
        ).fetchone()
        if existing is None:
            raise ValueError("Request not found")
        if existing["status"] != "pending":
            raise ValueError("Only pending requests can be approved or rejected")
        assigned_checker = (existing["checker"] or "").strip()
        if assigned_checker and assigned_checker.lower() != checker.lower():
            raise ValueError("This request is assigned to another checker")
        if not assigned_checker:
            raise ValueError("This request has no assigned checker")
        conn.execute(
            """
            UPDATE requests
            SET status = ?,
                checker = ?,
                approval_date = ?,
                reject_reason = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (status, checker, today().isoformat(), reject_reason, now, request_id),
        )
        row = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)
        ).fetchone()
        return row_to_dict(row)


def effective_export_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT r.*
        FROM requests r
        JOIN (
            SELECT run_num, MAX(id) AS max_id
            FROM requests
            WHERE status IN ('approved', 'exported')
            GROUP BY run_num
        ) latest ON latest.max_id = r.id
        ORDER BY r.created_at DESC, r.id DESC
        """,
    ).fetchall()
    return rows


def export_excel() -> dict[str, Any]:
    batch_id = datetime.now().strftime("export-%Y%m%d-%H%M%S")
    output_path = EXPORT_DIR / f"skip_loading_{batch_id}.xlsx"

    with connect() as conn:
        rows = effective_export_rows(conn)

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Skip_Loading"
        headers = [
            "Run_Num",
            "Start_Date",
            "End_Date",
            "Maker",
            "Input_Date",
            "Checker",
            "Approval_Date",
            "REMARK",
            "POD",
        ]
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="D9EAF7")

        for row in rows:
            sheet.append(
                [
                    row["run_num"],
                    excel_date_value(row["start_date"], "Start_Date"),
                    excel_date_value(row["end_date"], "End_Date"),
                    row["maker"],
                    excel_date_value(row["input_date"], "Input_Date"),
                    row["checker"] or "",
                    excel_date_value(row["approval_date"], "Approval_Date"),
                    row["remark"],
                    row["pod"],
                ]
            )

        for column in ("B", "C", "E", "G"):
            for cell in sheet[column][1:]:
                if cell.value:
                    cell.number_format = EXCEL_DATE_FORMAT

        widths = {
            "A": 12,
            "B": 14,
            "C": 14,
            "D": 18,
            "E": 14,
            "F": 20,
            "G": 16,
            "H": 44,
            "I": 12,
        }
        for column, width in widths.items():
            sheet.column_dimensions[column].width = width

        if rows:
            table_ref = f"A1:I{len(rows) + 1}"
            table = Table(displayName="SkipLoadingTable", ref=table_ref)
            table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium2",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )
            sheet.add_table(table)

        workbook.save(output_path)

        if rows:
            now = datetime.now().isoformat(timespec="seconds")
            row_ids = [row["id"] for row in rows]
            placeholders = ",".join("?" for _ in row_ids)
            conn.execute(
                f"""
                UPDATE requests
                SET status = 'exported',
                    export_batch_id = COALESCE(export_batch_id, ?),
                    updated_at = ?
                WHERE id IN ({placeholders})
                """,
                (batch_id, now, *row_ids),
            )

    backup_path = backup_database(batch_id)

    return {
        "batch_id": batch_id,
        "file": str(output_path),
        "backup_file": str(backup_path),
        "record_count": len(rows),
    }


def summary() -> dict[str, Any]:
    with connect() as conn:
        pending = conn.execute(
            "SELECT COUNT(*) AS count FROM requests WHERE status = 'pending'"
        ).fetchone()["count"]
        export_rows = effective_export_rows(conn)
        current_stop = sum(1 for row in export_rows if row["action"] == "STOP")
        current_resume = sum(1 for row in export_rows if row["action"] == "RESUME")
        return {
            "pending": pending,
            "will_export_now": len(export_rows),
            "current_stop": current_stop,
            "current_resume": current_resume,
            "today": today().isoformat(),
        }


def api_response(handler: SimpleHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def is_database_busy_error(exc: Exception) -> bool:
    if not isinstance(exc, sqlite3.Error):
        return False
    message = str(exc).lower()
    return "database is locked" in message or "database is busy" in message


def api_error_response(handler: SimpleHTTPRequestHandler, exc: Exception) -> None:
    if is_database_busy_error(exc):
        api_response(handler, 503, {"error": DATABASE_BUSY_MESSAGE})
        return
    api_response(handler, 400, {"error": str(exc)})


def read_json(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def read_multipart_file(handler: SimpleHTTPRequestHandler, field_name: str) -> bytes:
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise ValueError("Expected multipart/form-data upload")
    boundary_marker = "boundary="
    if boundary_marker not in content_type:
        raise ValueError("Upload boundary missing")
    boundary = content_type.split(boundary_marker, 1)[1].strip().strip('"')
    length = int(handler.headers.get("Content-Length", "0"))
    body = handler.rfile.read(length)
    delimiter = f"--{boundary}".encode()
    for part in body.split(delimiter):
        if f'name="{field_name}"'.encode() not in part:
            continue
        if b"\r\n\r\n" not in part:
            continue
        content = part.split(b"\r\n\r\n", 1)[1]
        content = content.rsplit(b"\r\n", 1)[0]
        if not content:
            raise ValueError("Uploaded file is empty")
        return content
    raise ValueError("Uploaded file field not found")


def import_mc_excel(file_bytes: bytes) -> dict[str, Any]:
    workbook = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    try:
        matches = []
        for sheet in workbook.worksheets:
            for row_number, row in enumerate(sheet.iter_rows(min_row=1, max_row=20, values_only=True), 1):
                if len(row) >= 28 and str(row[2] or "").strip().lower() == "pyname":
                    matches.append((sheet, row_number, row))
        if len(matches) != 1:
            raise ValueError("Expected exactly one sheet with pyName in column C; check the Excel header.")
        sheet, header_row, header = matches[0]
        if any(not str(header[i] or "").strip() for i in (0, 10, 12, 26, 27)):
            raise ValueError("Missing header in one of columns A, K, M, AA or AB.")
        rows = []
        skipped = 0
        for row in sheet.iter_rows(min_row=header_row + 1, min_col=1, max_col=28, values_only=True):
            key = str(row[2] or "").strip()
            if not key:
                if any(value is not None for value in row):
                    skipped += 1
                continue
            def cell_value(value: Any) -> str:
                if value is None:
                    return ""
                if isinstance(value, (datetime, date)):
                    return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
                return str(value).strip()
            rows.append(tuple(cell_value(row[i]) for i in (0, 2, 8, 10, 12, 26, 27)))
        if not rows:
            raise ValueError("No rows with a pyName found; no records were imported.")
        with connect() as conn:
            conn.execute("DELETE FROM mc_entries")
            conn.executemany("""INSERT INTO mc_entries
                (proposition_active, py_name, py_label, prod_start_dt, eligibility_rule, start_date, end_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", rows)
        return {"imported_count": len(rows), "skipped_count": skipped, "sheet": sheet.title}
    finally:
        workbook.close()


def lookup_mc(key: str, page: int = 1, page_size: int = 10) -> dict[str, Any]:
    key = require_text({"key": key}, "key", "pyName")
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM mc_entries WHERE py_name = ? COLLATE NOCASE", (key,)).fetchone()[0]
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(max(1, page), pages)
        rows = conn.execute("""SELECT proposition_active, py_name, py_label, prod_start_dt, eligibility_rule, start_date, end_date
            FROM mc_entries WHERE py_name = ? COLLATE NOCASE ORDER BY id DESC LIMIT ? OFFSET ?""",
            (key, page_size, (page - 1) * page_size)).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "total_pages": pages}


class AppHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/summary":
                api_response(self, 200, summary())
            elif parsed.path == "/api/requests":
                query = parse_qs(parsed.query)
                api_response(
                    self,
                    200,
                    list_requests(
                        status=query.get("status", [None])[0],
                        run_num=query.get("run_num", [None])[0],
                        checker=query.get("checker", [None])[0],
                        pod=query.get("pod", [None])[0],
                    ),
                )
            elif parsed.path == "/api/history":
                query = parse_qs(parsed.query)
                api_response(self, 200, get_history(query.get("run_num", [""])[0]))
            elif parsed.path == "/api/defaults":
                query = parse_qs(parsed.query)
                api_response(
                    self,
                    200,
                    get_defaults(
                        run_num=query.get("run_num", [None])[0],
                        action=query.get("action", [None])[0],
                    ),
                )
            elif parsed.path == "/api/export-preview":
                with connect() as conn:
                    rows = effective_export_rows(conn)
                    api_response(self, 200, [row_to_dict(row) for row in rows])
            elif parsed.path == "/api/mc":
                query = parse_qs(parsed.query)
                api_response(self, 200, lookup_mc(query.get("key", [""])[0], normalized_page(query.get("page", [None])[0])))
            elif parsed.path == "/api/dag-entries":
                query = parse_qs(parsed.query)
                api_response(
                    self,
                    200,
                    list_dag_entries(
                        dag_id=query.get("dag_id", [None])[0],
                        page=normalized_page(query.get("page", [None])[0]),
                    ),
                )
            elif parsed.path == "/api/dag-history":
                query = parse_qs(parsed.query)
                api_response(
                    self,
                    200,
                    get_dag_history(
                        query.get("dag_id", [""])[0],
                        page=normalized_page(query.get("page", [None])[0]),
                    ),
                )
            elif parsed.path == "/api/task-entries":
                query = parse_qs(parsed.query)
                api_response(
                    self,
                    200,
                    list_task_entries(
                        task_id=query.get("task_id", query.get("task_unique_key", [None]))[0],
                        page=normalized_page(query.get("page", [None])[0]),
                    ),
                )
            elif parsed.path == "/api/task-history":
                query = parse_qs(parsed.query)
                api_response(
                    self,
                    200,
                    get_task_history(
                        query.get("task_id", query.get("task_unique_key", [""]))[0],
                        page=normalized_page(query.get("page", [None])[0]),
                    ),
                )
            elif parsed.path.startswith("/exports/"):
                self.serve_file(EXPORT_DIR / Path(parsed.path).name)
            elif parsed.path == "/" or parsed.path.startswith("/static/"):
                if parsed.path == "/":
                    path = STATIC_DIR / "index.html"
                else:
                    path = STATIC_DIR / parsed.path.removeprefix("/static/")
                self.serve_file(path)
            else:
                api_response(self, 404, {"error": "Not found"})
        except Exception as exc:
            api_error_response(self, exc)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/mc-import":
                api_response(self, 200, import_mc_excel(read_multipart_file(self, "file")))
                return
            if parsed.path == "/api/import-history":
                file_bytes = read_multipart_file(self, "file")
                api_response(self, 200, import_history_excel(file_bytes))
                return
            if parsed.path == "/api/dag-import":
                file_bytes = read_multipart_file(self, "file")
                api_response(self, 200, import_dag_excel(file_bytes))
                return
            if parsed.path == "/api/tasks-import":
                file_bytes = read_multipart_file(self, "file")
                api_response(self, 200, import_tasks_excel(file_bytes))
                return
            payload = read_json(self)
            if parsed.path == "/api/running-status":
                api_response(self, 200, check_running_status(payload))
            elif parsed.path == "/api/requests":
                api_response(self, 201, create_request(payload))
            elif parsed.path == "/api/dag-entries":
                api_response(self, 201, create_dag_entry(payload))
            elif parsed.path == "/api/task-entries":
                api_response(self, 201, create_task_entry(payload))
            elif parsed.path.startswith("/api/requests/") and parsed.path.endswith("/decision"):
                request_id = int(parsed.path.split("/")[3])
                api_response(self, 200, decide_request(request_id, payload))
            elif parsed.path == "/api/export":
                api_response(self, 200, export_excel())
            elif parsed.path == "/api/dag-export":
                api_response(self, 200, export_dag_excel())
            elif parsed.path == "/api/tasks-export":
                api_response(self, 200, export_tasks_excel())
            elif parsed.path == "/api/export-json":
                api_response(self, 200, export_database_json())
            else:
                api_response(self, 404, {"error": "Not found"})
        except Exception as exc:
            api_error_response(self, exc)

    def serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            api_response(self, 404, {"error": "File not found"})
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def run() -> None:
    init_db()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Skip Loading Interface running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()




