# 模块划分与项目目录结构

## 1. 整体架构

StockTools 第一版采用 CLI + service + domain/data/infra 的分层结构。核心原则：

- CLI 只负责参数解析、用户交互和输出渲染。
- service 负责完整用例编排。
- scanner 只负责形态算法，不直接读写数据库。
- provider 只负责外部数据源拉取，不直接写 SQLite。
- repository 只负责 SQLite 表访问，不包含业务判断。
- output 只被 CLI 使用，不向 service、scanner、repo 下沉。
- setup 由 `setup.sh` 完成；shell 脚本每一步执行前先探测目标是否已存在，已存在则跳过该步骤。

依赖方向：

```
CLI 层
  ↓
Service / UseCase 层
  ↓
Domain 层（Scanner / AI Analyst 结果对象）
  ↓
Data 层（Provider / Repository / DB）

Infra / Config / Output 为横切模块：
- paths、cron、shell rc、config schema 属于 infra/config，按需被 CLI 或 service 调用
- display、csv 只允许被 CLI 调用
```

## 2. setup.sh 与 st init 边界

### 2.1 `setup.sh`

`setup.sh` 负责本机环境准备，不抓取股票行情。

职责：
- 引导用户选择工作目录，默认 `~/.stock_tools`。
- 创建工作目录。
- 写入工作目录记录文件，供后续 `st` 命令定位工作目录。
- 写入 `~/.zshrc` 或 `~/.bashrc`，让用户可以直接调用 `st`。这个过程中会用到`pwd`来获取用户的安装目录，使得`st`运行指向我们安装目录中的程序。
- 初始化 `<workdir>/database.db`，创建主库表结构。
- 初始化 `<workdir>/config.db`，创建 `model_config` 表，并引导写入模型配置。
- 引导用户配置 cron，默认每天 15:05 执行 `st update`；用户可以选择不配置 cron。

探测机制：
- 创建目录前先判断目录是否存在，存在则跳过创建。
- 写 shell rc 前先判断是否已有 StockTools 配置片段，已有则跳过写入。
- 创建 `database.db` / `config.db` 前先判断文件是否存在；存在则只补齐缺失表，不覆盖已有数据。
- 写模型配置前先判断 `model_config` 是否已有记录；已有则询问是否覆盖，默认不覆盖。
- 写 cron 前先判断是否已有 StockTools cron 项；已有则询问是否替换，默认不替换。

### 2.2 `st init`

`st init` 只负责抓取初始化行情数据：
- 从 baostock 拉取全 A 过去 1 年前复权日 K。
- 写入 `<workdir>/database.db` 的 `daily_kline` 表。
- 个别股票拉取失败时沉默跳过，不阻断整体初始化。

`st init` 不负责：
- 创建工作目录。
- 写 shell rc。
- 创建 `config.db`。
- 配置 cron。
- 创建数据库文件或基础表结构。

## 3. 模块说明

### 3.1 CLI 层（`stocktools/cli/`）

每个子命令对应一个模块。CLI 模块只做参数定义、调用 service、处理必要的用户输入、调用 output 渲染结果。

| 模块 | 对应命令 | 职责 |
|------|----------|------|
| `main.py` | `st` | 顶层 argparse 构建，子命令注册与分发 |
| `cmd_data.py` | `st init / update / cron` | 解析数据与 cron 命令参数，调用 `DataService` / `CronService` |
| `cmd_find.py` | `st find` | 解析扫描器名称、阈值、`--csv`，调用 `FindService` |
| `cmd_record.py` | `st record` | 解析关注池命令，调用 `RecordService` |
| `cmd_watch.py` | `st watch` | 解析买入分析命令，调用 `WatchService` |
| `cmd_hold.py` | `st hold` | 解析持仓命令，调用 `HoldService` |
| `cmd_alert.py` | `st alert` | 调用 `AlertService`，并处理 `[y/n]` 写入确认 |

CLI 层允许依赖：
- `stocktools.services`
- `stocktools.output`
- `stocktools.infra.paths`

CLI 层不允许直接写 SQL，不直接调用 provider，不直接拼 AI prompt。

### 3.2 Service / UseCase 层（`stocktools/services/`）

service 层承接完整业务流程，是 CLI 和底层模块之间的编排层。

| 模块 | 职责 |
|------|------|
| `data_service.py` | `st init` 拉取历史行情；`st update` 拉取当日快照；协调 provider 和 `KlineRepo` |
| `cron_service.py` | `st cron set <hh> <mm>`；协调 crontab 读写 |
| `find_service.py` | 批量读取 K 线，调用指定 scanner，返回符合条件的结果 |
| `record_service.py` | 关注池增删改查；`record add` 时自动运行所有 scanner 并写入 `pattern` |
| `watch_service.py` | 读取关注池与行情，调用买入分析，upsert 当天 `ai_logs` |
| `hold_service.py` | 持仓登记、平仓、减仓操作记录、止损/目标价/备注更新、历史查询 |
| `alert_service.py` | 读取持仓与行情，调用卖出分析，返回建议与可写入字段 |

service 层返回结构化结果，不直接打印。

### 3.3 Domain 层：扫描器（`stocktools/scanners/`）

扫描器是纯形态算法模块，只接收行情数据并返回判定结果。

| 模块 | 职责 |
|------|------|
| `base.py` | 抽象基类 `BaseScanner`，定义 `detect(df, **kwargs) -> ScanResult` |
| `registry.py` | 扫描器注册表，通过名称字符串获取 scanner 类 |
| `results.py` | 定义 `ScanResult` 数据结构 |
| `box.py` | 低位箱体整理形态识别 |
| `channel.py` | 上升通道形态识别 |
| `ma_alignment.py` | MA均线多头排列 |

约束：
- `BaseScanner` 不提供 `scan_all()`。
- 批量扫描放在 `FindService`，由 service 调用 repo 读取 K 线，再调用 scanner。
- scanner 不依赖 SQLite、provider、CLI、output。
- 每个 scanner 对单只股票只判断“符合扫描条件”或“不符合扫描条件”。

建议结果结构：

```python
@dataclass
class ScanResult:
    matched: bool
    pattern: str
    indicators: dict[str, object]
```

### 3.4 AI 层（`stocktools/ai/`）

AI 层负责 OpenAI 兼容客户端、prompt 构建、返回内容解析和结构化结果。

| 模块 | 职责 |
|------|------|
| `client.py` | OpenAI SDK 客户端封装，读取 `config.db` 中的 `base_url / api_key / model_name`，超时 60s |
| `models.py` | 定义 `WatchAnalysis`、`AlertAnalysis` 等结构化结果 |
| `watch_analyst.py` | 构建买入分析 prompt，返回 `WatchAnalysis` |
| `alert_analyst.py` | 构建卖出分析 prompt，返回 `AlertAnalysis`，包含可选止损价/目标价 |

建议结果结构：

```python
@dataclass
class WatchAnalysis:
    code: str
    conclusion: str
    content: str
    analysis_date: str

@dataclass
class AlertAnalysis:
    code: str
    conclusion: str
    content: str
    analysis_date: str
    suggested_stop_loss: float | None = None
    suggested_take_profit: float | None = None
```

AI 层不直接写 `ai_logs`，由 service 调用 `AiLogsRepo.upsert()`。

### 3.5 Data 层（`stocktools/data/`）

#### 3.5.1 SQLite 连接与 schema

| 模块 | 职责 |
|------|------|
| `db.py` | 管理主数据库 `database.db` 连接，提供事务上下文 |
| `schema.py` | 主数据库 DDL：`daily_kline`、`watchlist`、`holdings`、`ai_logs` |

主数据库表结构由 `setup.sh` 初始化；实现时可通过 `schema.py` 提供 SQL 片段或辅助命令。

#### 3.5.2 Provider（`stocktools/data/providers/`）

Provider 只负责获取外部数据，不写数据库。

| 模块 | 职责 |
|------|------|
| `base.py` | 抽象基类 `BaseProvider`，定义 `fetch_history(code, start, end)` 和 `fetch_daily_all()` |
| `baostock_provider.py` | 拉取历史前复权日 K，供 `st init` 使用 |
| `akshare_provider.py` | 拉取全市场收盘后当日快照，供 `st update` 使用 |

#### 3.5.3 Repository（`stocktools/data/repos/`）

每张主库表一个 repo，封装 SQL 操作。

| 模块 | 对应表 | 主要方法 |
|------|--------|----------|
| `kline_repo.py` | `daily_kline` | `bulk_insert`、`get_klines(code, n_days)`、`list_codes()`、`get_latest_date()` |
| `watchlist_repo.py` | `watchlist` | `add`、`remove`、`get`、`list_all`、`update_note`、`set_buy_tomorrow`、`update_pattern` |
| `holdings_repo.py` | `holdings` | `add_entry`、`close_all_open_by_code`、`append_reduction_note`、`update_stop_loss`、`update_take_profit`、`update_note`、`list_open`、`list_closed` |
| `ai_logs_repo.py` | `ai_logs` | `upsert`（同只股票同类型同日覆盖）、`get_latest(code, type)` |

`--dec` 第一版只表示“发生减仓操作”，不记录减仓数量，不新增减仓表。没有 `--dec` 时表示平仓，关闭该股票全部 open 持仓。

### 3.6 Config 层（`stocktools/config/`）

`config.db` 与模型配置独立于主数据层。

| 模块 | 职责 |
|------|------|
| `db.py` | 管理 `config.db` 连接 |
| `schema.py` | `model_config` DDL |
| `model_config_repo.py` | 读写 `base_url`、`api_key`、`model_name` |

`config.db` 由 `setup.sh` 初始化。AI client 通过该层读取模型配置。

### 3.7 Infra 层（`stocktools/infra/`）

系统级能力放在 infra，不混入业务逻辑。

| 模块 | 职责 |
|------|------|
| `paths.py` | 解析工作目录和数据库路径 |
| `cron.py` | 读写系统 crontab |
| `shell_rc.py` | 检测和写入 `~/.zshrc` / `~/.bashrc` 中的 StockTools 配置片段 |

工作目录发现顺序：
1. `STOCKTOOLS_HOME` 环境变量
2. `~/.stock_tools_path`
3. 默认 `~/.stock_tools`

### 3.8 Output 层（`stocktools/output/`）

| 模块 | 职责 |
|------|------|
| `display.py` | 终端表格和普通文本输出 |
| `csv_writer.py` | CSV 导出，所有导出都要求用户显式传入 `--csv <path>` |

output 只被 CLI 层调用，不被 service、repo、scanner、ai 调用。

## 4. 项目目录结构

```
StockTools/
├── setup.sh                        # shell 初始化脚本，负责工作区、shell rc、db 初始化、cron 引导
├── requirements.txt                # 第一版依赖：akshare, baostock, openai
├── requirements-tui.txt            # 后续 TUI 依赖：textual
├── st.py                           # CLI 入口，被 setup.sh 写入 shell rc 后简化为 st
├── docs/
│   ├── PRD.md
│   ├── database.md
│   ├── modules.md
│   └── TUI.md
└── stocktools/
    ├── __init__.py
    ├── cli/
    │   ├── __init__.py
    │   ├── main.py
    │   ├── cmd_data.py
    │   ├── cmd_find.py
    │   ├── cmd_record.py
    │   ├── cmd_watch.py
    │   ├── cmd_hold.py
    │   └── cmd_alert.py
    ├── services/
    │   ├── __init__.py
    │   ├── data_service.py
    │   ├── cron_service.py
    │   ├── find_service.py
    │   ├── record_service.py
    │   ├── watch_service.py
    │   ├── hold_service.py
    │   └── alert_service.py
    ├── scanners/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── registry.py
    │   ├── results.py
    │   ├── box.py
    │   ├── channel.py
    │   └── ma_alignment.py
    ├── ai/
    │   ├── __init__.py
    │   ├── client.py
    │   ├── models.py
    │   ├── watch_analyst.py
    │   └── alert_analyst.py
    ├── data/
    │   ├── __init__.py
    │   ├── db.py
    │   ├── schema.py
    │   ├── providers/
    │   │   ├── __init__.py
    │   │   ├── base.py
    │   │   ├── baostock_provider.py
    │   │   └── akshare_provider.py
    │   └── repos/
    │       ├── __init__.py
    │       ├── kline_repo.py
    │       ├── watchlist_repo.py
    │       ├── holdings_repo.py
    │       └── ai_logs_repo.py
    ├── config/
    │   ├── __init__.py
    │   ├── db.py
    │   ├── schema.py
    │   └── model_config_repo.py
    ├── infra/
    │   ├── __init__.py
    │   ├── paths.py
    │   ├── cron.py
    │   └── shell_rc.py
    └── output/
        ├── __init__.py
        ├── display.py
        └── csv_writer.py
```

## 5. 关键依赖关系

```
cmd_data
  → DataService
  → baostock/akshare provider + KlineRepo

cmd_find
  → FindService
  → KlineRepo + scanner registry

cmd_record
  → RecordService
  → WatchlistRepo + KlineRepo + scanner registry

cmd_watch
  → WatchService
  → WatchlistRepo + KlineRepo + WatchAnalyst + AiLogsRepo

cmd_hold
  → HoldService
  → HoldingsRepo

cmd_alert
  → AlertService
  → HoldingsRepo + KlineRepo + AlertAnalyst + AiLogsRepo

ai.client
  → config.model_config_repo

all CLI commands
  → infra.paths
  → output.display / output.csv_writer
```

禁止依赖：
- Provider 不依赖 Repo 或 DB。
- Scanner 不依赖 Repo、Provider、CLI、Output。
- Service 不依赖 Output。
- Repo 不依赖 Service、CLI、Output。
- Output 不依赖 Service 内部实现。
