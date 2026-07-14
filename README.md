# Skip Loading Interface

Internal MVP for replacing direct Excel edits with a small request interface.

## Flow

1. Users submit a `STOP` or `RESUME` request for a `Run_Num`.
   They can optionally assign a checker name for easier queue filtering.
2. Every request is stored as history. Existing records are not overwritten.
3. `Remark / Purpose` is mandatory for audit and traceability.
4. `Create Time` is captured automatically when the user submits a request.
5. Checkers approve or reject pending requests.
6. Day-end export generates an Excel file with the same columns as the existing process:
   `Run_Num`, `Start_Date`, `End_Date`, `Maker`, `Input_Date`, `Checker`, `Approval_Date`, `REMARK`, `POD`.
7. The exported Excel can be committed to GitHub, keeping the existing batch / Omnibase process unchanged.
8. Legacy history Excel can be imported. The importer keeps only the last row per `Run_Num`, marks it as `approved`, and uses import time as `Create Time`.

## Business Rules

- `STOP` defaults `End_Date` to `2099-12-31`.
- `RESUME` defaults `End_Date` to yesterday.
- `RESUME` requires `End_Date` to be before today.
- `Remark / Purpose` is always required.
- Pending requests can be filtered by assigned checker name in the Checker Queue.
- Dashboard metrics show `Pending`, `Will Export Now`, `Current STOP`, and `Current RESUME`.
- The database keeps all history for each `Run_Num`.
- Import History allows blank legacy fields such as Maker, Checker, Remark, and POD. Blank values stay blank in later Excel exports.
- Export includes the latest effective approved/exported state per `Run_Num`.
- `STOP` rows stay active with a future `End_Date`; `RESUME` rows are exported with an `End_Date` before today so the downstream process can update the existing stop record.
- Each Day-end Export gets one batch id in the format `export-YYYYMMDD-HHMMSS`.
- A request's `Export Batch` stores the first batch where that approved record was included. Daily full-picture exports do not overwrite that first export batch.

## Run Locally

Recommended on Windows:

```text
Double-click run_server.cmd
```

Keep that command window open while using the interface.

First-time setup on a normal work computer:

```text
Double-click setup_windows.cmd
```

For colleagues on the same office network:

```text
Double-click run_lan_server.cmd
```

Then ask IT or run `ipconfig` to find your computer's IPv4 address. Colleagues can open:

```text
http://YOUR-COMPUTER-IP:8000
```

Use the bundled Codex Python runtime if system Python does not have `openpyxl`:

```powershell
& "C:\Users\melop\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" app.py
```

Then open:

```text
http://127.0.0.1:8000
```

Data is stored in:

```text
data/skip_loading.db
```

Exported Excel files are written to:

```text
exports/
```
