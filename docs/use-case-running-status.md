# Use Case Running Status 說明

這份文檔說明如何判斷一個 use case 現在是否仍在運行中。判斷需要同時看 `Skip Loading`、`TASKS`、`DAG Scheduler`、`VM_alive_days` 和 `MC`，不能只靠單一欄位。

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
6. 該 pyName 的 MC 記錄有效，並已到 `Prod_Start_Dt`。

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
- 如果 `end_date` 的年份是 `9999`，代表沒有結束日期，STOP 持續有效。
- 如果 STOP 的結束日期無法解析，總結論是 `UNKNOWN`。
- 如果最新有效記錄是 `STOP`，但 `end_date < today`，這個 STOP 已過期，視為沒有當前 skip 限制，進入下一步。

### TASKS

使用 `task_entries` 表，按最新版本判斷 task 狀態。每個 `task_id` 可能有多個版本，應以最大 `id` 的版本為準。

`run_num` 和 `task_id` 的關係：

- `task_id` 中 `RDP` 後面的完整數字代表 `run_num`，必須完整匹配，不能只做數字包含匹配。
- 前導零有意義，例如 `003337` 只匹配 `RDP003337`，不匹配 `RDP3337`。
- 例如查找 `3337` 時，`CUS_001_DAILY_A_TASK_RDP3337` 匹配，但 `CUS_002_DAILY_A_TASK_RDP13337` 不匹配。

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

已確認的日期判斷方式：

- `vm_start_day = start_day`
- 只比較日期，不計 `start_datetime` 的小時和分鐘；開始當日算第 1 日。
- `vm_end_day = start_day + VM_alive_days - 1 day`
- 當 `vm_start_day <= today <= vm_end_day` 時，VM 仍有效。
- 例如 `start_datetime = 2026-08-01 18:00`、`VM_alive_days = 10`，有效期為 2026-08-01 至 2026-08-10，2026-08-11 開始過期。

如果 `VM_alive_days` 是空白，代表 VM 沒有到期日；DAG 日期仍須有效。0、負數、小數或無法解析的值無效，結果為 `UNKNOWN_VM_VALIDITY`。DAG 日期無法解析或日期範圍顛倒時，結果為 `UNKNOWN_DAG_DATES`。

## 建議判斷順序

```text
Input: run_num, today

1. 讀取 Skip Loading 最新有效記錄
   - 無記錄 -> 沒有 skip 限制，繼續下一步
   - 最新有效記錄是 RESUME -> skip 已解除，繼續下一步
   - 最新有效記錄是 STOP 且 end_date >= today -> STOPPED_BY_SKIP_LOADING
   - 最新有效記錄是 STOP 但 end_date < today -> STOP 已過期，繼續下一步

2. 用 run_num 完整匹配 TASKS.task_id 中 RDP 後的數字
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
- 如果沒有 task 是 `RUNNING`，但至少一個 task 的有效性是 `UNKNOWN`，use case 總結論是 `UNKNOWN`。
- 如果所有 task 都明確不運行，use case 總結論是 `NOT_RUNNING`。

以上是 Run_Num 原有的結論。與 MC 結合後，兩者都有效才是 `RUNNING`；任何一方明確無效時是 `NOT_RUNNING`；否則是 `UNKNOWN`。

## MC

- 查詢以 `pyName` 為 key，按 pyName 分別判斷。`pyName` 中 `SAS` 後的完整數字字串對應 `run_num`，不區分大小寫，並保留前導零。多個 pyName 可對應同一 Run_Num，共用原有 Run_Num 判斷，但各自結合自己的 MC 資料。
- `pyIsPropositionActive = Never` 表示無效；`Always` 表示不受 proposition 日期範圍限制；`Date` 表示要在 `StartDate` 到 `EndDate` 的範圍內。
- `Always` 和 `Date` 同時需要已到 `Prod_Start_Dt`；不認識的狀態或無法判斷的必要日期顯示 `UNKNOWN`。
- 日期只比較日曆日期，開始及結束日期當日包含在內。`Always` 不需要 `StartDate` 或 `EndDate`；`Date` 必須有有效的日期範圍。
- `Prod_Start_Dt` 必須有有效日期，包括 `Always`；缺失或無效顯示 `UNKNOWN`。
- MC 的 pyName 應該唯一，並且包含 SAS 數字。找不到 pyName、同一 pyName 有多筆記錄，或名稱沒有唯一的 SAS 數字時，顯示 `UNKNOWN` 並說明原因；重複記錄仍逐筆顯示。
- MC 匯入使用整份 Excel 替換現有 MC 資料；查詢基於當前已匯入的快照。

## 原有 Run_Num 規則範例

以下範例只展示 Run_Num 原有的判斷；最終結果還須結合 MC。

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
