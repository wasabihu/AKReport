# AKShare-wasa

财报 PDF 下载工具规划项目。

目标是基于 AKShare 和巨潮资讯公开数据源，构建一个支持 A 股、港股公司年报和季报批量下载的本地工具。项目将优先保证源站友好访问、下载结果可靠、测试优先开发。

## 文档

- [财报 PDF 下载工具开发文档](docs/财报PDF下载工具开发文档.md)：产品目标、可行性、总体架构和里程碑
- [后端开发文档](docs/后端开发文档.md)：FastAPI、任务队列、限速器、巨潮接口、下载器和测试要求
- [前端开发文档](docs/前端开发文档.md)：React UI、组件职责、API client、SSE、状态管理和测试要求
- [开发规范](docs/开发规范.md)：测试优先、源站保护、提交规范和完成定义

## 当前状态

### 后端开发进度

- [x] 项目结构初始化 + 虚拟环境 + 依赖安装
- [x] 基础模块：config.py、models.py
- [x] 限速器：rate_limiter.py + 测试 (8/8 通过)
- [x] 数据源：cninfo_client.py、akshare_client.py
- [x] 报告匹配：report_matcher.py + 测试 (23/23 通过)
- [x] 文件命名：filename.py + 测试 (6/6 通过)
- [x] 下载器：downloader.py（.partial → 验证 → atomic rename）
- [x] 存储：database.py、repositories.py（4 表 + CRUD）
- [x] 任务队列：task_queue.py（async worker pool + rate limiter）
- [x] Excel 导入：excel_importer.py
- [x] API 端点：health、reports/search、tasks CRUD、SSE、settings、import/excel
- [x] 主应用：dependencies.py、main.py
- [x] 单元测试通过 (37/37)

### 前后端联调进度

- [x] 前端 Vite 代理 `/api` → `http://127.0.0.1:8000`
- [x] 统一错误格式 `{error: {code, message}}`（exception_handlers.py）
- [x] createTask 响应补充 `status` 字段
- [x] SSE 事件：`log` + `item_updated` + `task_completed` + `ping` 心跳
- [x] `item_updated` 包含 `item_id`/`year`/`report_type` 字段用于精确匹配
- [x] 前端 taskReducer 支持 `item_id` 优先匹配
- [x] 前端 `task_created` 后立即 `getTask` 初始化 items
- [x] 任务完成后前端主动刷新 `task_loaded` 拿最终状态
- [x] 文件名包含股票名称（从 CNInfo secName 提取）
- [x] 时间戳 `started_at`/`finished_at` 改为 ISO 格式
- [x] 重试失败按钮绑定 `retryFailedTaskItems` API
- [x] 端到端测试通过（A股 000001/002415/300750/601318/600519，港股 00700）
- [x] 批量多股+多报告类型测试通过（2股×2类型=4项，全部 success）

### 前后端联调 — 新完成

- [x] 搜索预览：前端点击"搜索预览"显示报告列表（代码/名称/年份/类型/标题/日期/匹配分）
- [x] 设置持久化：页面加载自动读取后端设置，修改后 1s debounce 自动保存
- [x] Excel/CSV 导入：前端文件上传，后端解析并追加到批量代码列表
- [x] API 端点 `/api/import/excel` 已注册

### 已知问题

- 自动降速 (auto_slowdown) 尚未在实际限速场景下验证

### 前端开发进度

- [x] 基础 UI：TopBar + LeftPanel + MainPanel + StatusBar
- [x] 单股/多股查询切换
- [x] 搜索预览表格（ReportCandidate 列表）
- [x] 设置持久化（加载/保存 request_interval/concurrency/auto_slowdown/save_dir）
- [x] Excel/CSV 导入（文件上传 + 解析结果追加到批量列表）
- [x] SSE 事件订阅 + taskReducer 状态管理
- [x] 任务控制：创建/取消/重试失败/恢复
- [x] 日志面板 + 任务结果表格
- [x] 单元测试通过 (12/12)

## 快速启动

### macOS / Linux

```bash
./startup.sh start
```

前端地址: http://127.0.0.1:5173

常用命令:

```bash
./startup.sh status
./startup.sh stop
./startup.sh restart
```

后端单独启动:

```bash
cd backend
source ../.venv/bin/activate
PYTHONPATH=. uvicorn app.main:app --reload --port 8000
```

### Windows

默认下载目录为：

```text
C:\reports
```

快速启动：

```bat
startup.bat start
```

常用命令：

```bat
startup.bat status
startup.bat stop
startup.bat restart
```

后端单独启动：

```bat
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

API 文档: http://localhost:8000/docs

## 测试

```bash
cd backend
source ../.venv/bin/activate
PYTHONPATH=. pytest app/tests/ -v
```
