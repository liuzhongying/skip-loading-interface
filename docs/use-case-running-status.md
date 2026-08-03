# Use Case Running Status 說明

這份文檔說明如何判斷一個 use case 現在是否仍在運行中。判斷需要同時看 `Skip Loading`、`TASKS`、`DAG Scheduler` 和 `VM_alive_days`，不能只靠單一欄位。

核心語義：

- `Skip Loading` 最新有效狀態是 `STOP`：代表這個 `run_num` 被 skip / stop，不應判斷為 running。
- `Skip Loading` 最新有效狀態是 `RESUME`：代表 skip 已解除，可以繼續看 TASKS / DAG / VM。
- `Skip Loading` 沒有記錄：代表沒有 skip 限制，可以繼續看 TASKS / DAG / VM。

## 判斷結論

一個 use case 只有在以下條件全部成立時，才可以判斷為 `RUNNING`：

1. `Skip Loading` 沒有有效 `STOP` 阻止它運行，也就是最新有效狀態是 `RESUME`，或者完全沒有 Skip Loading 記錄。
2. 這個 `run_num` 可以在 `TASKS.task_id` 裏找到對應 task。
3. 對應 task 的最新版本沒有被 inactive，即 `task_inactive_flag` 不是 `Y`。
4. 對應 task 所屬的 `dag_id` 在 `DAG Scheduler` 裏仍在有效日期內。
5. `DAG Scheduler.VM_alive_days` 顯示 VM 仍在有效期內。

只要其中一項不成立，就不能判斷為正在運行。

## 資料來源

### Skip Loading

使用 `requests` 表，按 `run_num` 找最新有效記錄。

有效記錄只包含：

- `status = approved`
- `status = exported`

不使用 `pending` 或 `rejected` 作為實際狀態判斷。

判斷方式：

- 如果最新有效記錄不存在，代表沒有 skip 限制，進入下一步。
- 如果最新有效記錄是 `RESUME`，代表 skip 已解除，進入下一步。
- 如果最新有效記錄是 `STOP`，並且 `end_date >= today`，結果是 `STOPPED_BY_SKIP_LOADING`。
- 如果最新有效記錄是 `STOP`，但 `end_date < today`，這個 STOP 已過期，視為沒有當前 skip 限制，進入下一步。

### TASKS

使用 `task_entries` 表，按最新版本判斷 task 狀態。每個 `task_id` 可能有多個版本，應以最大 `id` 的版本為準。

`run_num` 和 `task_id` 的關係：

- 業務判斷是：這個 `run_num` 是否出現在 `TASKS.task_id` 裏。
- 查找時建議先用標準化後的 `run_num` 做包含匹配，例如 `task_id LIKE '%<run_num>%'`。
- 如果將來有更明確的 mapping table，應以 mapping table 為準。

判斷方式：

- 如果找不到任何對應 `task_id`，結果是 `NO_TASK_FOR_RUN_NUM`。
- 如果找到多個對應 task，需要逐個判斷；只要有一個 task 仍有效，use case 可以繼續進入 DAG / VM 判斷。
- 如果最新 task 版本的 `task_inactive_flag = Y`，該 task 結果是 `NOT_RUNNING_TASK_INACTIVE`。
- 如果 `task_inactive_flag` 是空白、`N` 或其他非 `Y` 值，該 task 視為未 inactive，進入下一步。

### DAG Scheduler

使用 `dag_entries` 表，按 task 所屬的 `dag_id` 找最新 DAG 版本。每個 `dag_id` 可能有多個版本，應以最大 `id` 的版本為準。

日期判斷：

- `start_day` 對應 `DAG Scheduler.start_datetime` 的日期部分。
- `end_day` 對應 `DAG Scheduler.end_date` 的日期部分。
- 當 `start_day <= today <= end_day` 時，DAG 日期仍有效。

判斷方式：

- 如果找不到 task 所屬 `dag_id`，結果是 `NO_DAG_FOR_TASK`。
- 如果今天早於 `start_day`，結果是 `NOT_RUNNING_DAG_NOT_STARTED`。
- 如果今天晚於 `end_day`，結果是 `NOT_RUNNING_DAG_EXPIRED`。
- 如果今天在 `start_day` 和 `end_day` 之間，進入 VM 判斷。

### VM_alive_days

`VM_alive_days` 用來判斷 VM 是否仍然有效。它應該和 DAG 的起始日期一起使用。

建議判斷方式：

- `vm_start_day = start_day`
- `vm_end_day = start_day + VM_alive_days - 1 day`
- 當 `vm_start_day <= today <= vm_end_day` 時，VM 仍有效。

如果 `VM_alive_days` 是空白或不能解析為數字，不能直接判斷 VM 仍有效，結果應為 `UNKNOWN_VM_VALIDITY`。這種情況不應顯示為確定 `RUNNING`。

## 建議判斷順序

```text
Input: run_num, today

1. 讀取 Skip Loading 最新有效記錄
   - 無記錄 -> 沒有 skip 限制，繼續下一步
   - 最新有效記錄是 RESUME -> skip 已解除，繼續下一步
   - 最新有效記錄是 STOP 且 end_date >= today -> STOPPED_BY_SKIP_LOADING
   - 最新有效記錄是 STOP 但 end_date < today -> STOP 已過期，繼續下一步

2. 用 run_num 查找 TASKS.task_id
   - 找不到 -> NO_TASK_FOR_RUN_NUM

3. 對每個對應 task 讀取最新 task 版本
   - task_inactive_flag = Y -> 該 task 不運行
   - 其他值 -> 讀取該 task 的 dag_id

4. 讀取 DAG Scheduler 最新 dag_id 版本
   - 找不到 -> NO_DAG_FOR_TASK
   - today 不在 start_day/end_day 內 -> 該 task 不運行

5. 判斷 VM_alive_days
   - VM_alive_days 無法判斷 -> UNKNOWN_VM_VALIDITY
   - today 在 VM 有效期內 -> RUNNING
   - today 超出 VM 有效期 -> NOT_RUNNING_VM_EXPIRED
```

## 多 task 情況

同一個 `run_num` 可能匹配到多個 `task_id`。建議輸出時保留每個 task 的判斷原因，再給 use case 一個總結論。

總結論規則：

- 只要 `Skip Loading` 當前是有效 `STOP`，use case 總結論就是 `NOT_RUNNING`。
- 只要至少一個 task 判斷為 `RUNNING`，use case 總結論是 `RUNNING`。
- 如果沒有 task 是 `RUNNING`，但至少一個 task 是 `UNKNOWN_VM_VALIDITY`，use case 總結論是 `UNKNOWN`。
- 如果所有 task 都明確不運行，use case 總結論是 `NOT_RUNNING`。

## 範例

### 範例 1：Skip Loading STOP，所以不運行

```text
run_num = 3337
Skip Loading 最新有效記錄 = STOP, end_date = 2099-12-31
TASKS.task_id = CUS_001_DAILY_A_TASK_RDP3337
task_inactive_flag = N
DAG Scheduler.start_datetime = 2026,8,1,18,00
DAG Scheduler.end_date = 2026,8,31,20,00
VM_alive_days = 10
today = 2026-08-04

結果：STOPPED_BY_SKIP_LOADING
總結論：NOT_RUNNING
```

### 範例 2：Skip Loading 已 RESUME，且 task / DAG / VM 都有效

```text
run_num = 3337
Skip Loading 最新有效記錄 = RESUME
TASKS.task_id = CUS_001_DAILY_A_TASK_RDP3337
task_inactive_flag = N
DAG Scheduler.start_datetime = 2026,8,1,18,00
DAG Scheduler.end_date = 2026,8,31,20,00
VM_alive_days = 10
today = 2026-08-04

結果：RUNNING
```

### 範例 3：沒有 Skip Loading 記錄，且 task / DAG / VM 都有效

```text
run_num = 3337
Skip Loading 最新有效記錄 = 無記錄
TASKS.task_id = CUS_001_DAILY_A_TASK_RDP3337
task_inactive_flag = N
DAG Scheduler.start_datetime = 2026,8,1,18,00
DAG Scheduler.end_date = 2026,8,31,20,00
VM_alive_days = 10
today = 2026-08-04

結果：RUNNING
```

### 範例 4：task 已 inactive

```text
run_num = 3337
Skip Loading 最新有效記錄 = RESUME
TASKS.task_id = CUS_001_DAILY_A_TASK_RDP3337
task_inactive_flag = Y

結果：NOT_RUNNING_TASK_INACTIVE
```

### 範例 5：DAG 有效但 VM 已過期

```text
run_num = 3337
Skip Loading 最新有效記錄 = RESUME
task_inactive_flag = N
DAG Scheduler.start_datetime = 2026,8,1,18,00
DAG Scheduler.end_date = 2026,8,31,20,00
VM_alive_days = 2
today = 2026-08-04

結果：NOT_RUNNING_VM_EXPIRED
```

## 實作注意點

- `run_num` 應先做標準化，去掉空格，避免輸入格式造成查不到資料。
- `task_id` 查找建議做大小寫不敏感匹配。
- `DAG Scheduler.start_datetime` 和 `end_date` 目前格式可能是 `YYYY,M,D,H,MM`，實作時要先抽出日期部分再比較。
- 不要用舊版本 task 或舊版本 DAG 判斷狀態；要用每個 `task_id` / `dag_id` 最新版本。
- `pending` request 代表等待審批，不應改變 use case 現在是否運行的判斷。
- `UNKNOWN` 不是 `RUNNING`。只有 Skip Loading 沒有阻止，且 task / DAG / VM 條件都能證明有效時，才輸出 `RUNNING`。
