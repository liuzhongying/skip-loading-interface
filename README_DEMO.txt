Skip Loading Interface - Demo Package

Run locally on one Windows computer:

1. Double click run_local_demo.cmd.
2. The browser should open http://127.0.0.1:8000.
3. Keep the command window open while using the interface.

Run locally but use a shared team database:

1. Edit run_shared_db_demo.cmd.
2. Replace these two paths with your real shared folder:
   - SKIP_LOADING_DB_PATH
   - SKIP_LOADING_EXPORT_DIR
3. Double click run_shared_db_demo.cmd.
4. Each colleague must use the same shared DB path if they need to see the same records.

Run as a LAN host from one computer:

1. Double click run_lan_demo.cmd on the host computer.
2. Ask IT for the host computer's IP address.
3. Colleagues open http://HOST-IP:8000.

Data files:

- skip_loading.db stores the request database.
- exported Excel files are stored in the exports folder.
- Each Excel export also creates a database backup in the backups folder.

Important:

- A shared folder DB is workable for small, low-concurrency usage only.
- Do not put the database in a OneDrive/SharePoint sync folder.
- Prefer a real server for production use if concurrent approval volume becomes high.
