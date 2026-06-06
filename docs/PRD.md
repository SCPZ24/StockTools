# 产品需求文档

## 1. 产品概述

StockTools（命令行名：`st`）是一个面向 A 股中长线投资者的终端工具。核心目标是让用户每天只花 10 分钟完成选股、跟踪、买卖决策的完整工作流。

形态：CLI + TUI。第一版只实现 CLI 指令，TUI 后续再做。

数据持久化使用 SQLite。

运行方式：
- 项目提供 `setup.sh`，用于创建工作目录、写入 shell 配置、初始化数据库、配置 cron。
- `setup.sh` 会把 `st` 指令写入 `~/.zshrc` 或 `~/.bashrc`，简化用户调用。
- 默认工作目录为 `~/.stock_tools`，用户可在 setup 阶段自定义。
- 主数据库路径为 `<workdir>/database.db`。
- 模型配置数据库路径为 `<workdir>/config.db`。
- 工作目录发现顺序：`STOCKTOOLS_HOME` 环境变量 > `~/.stock_tools_path` > 默认 `~/.stock_tools`。


## 2. 用户画像

- 有一定技术分析基础的 A 股散户
- 只做中长线（持仓周期数周到数月），只做多
- 日常使用同花顺看盘，但需要自动化的形态筛选和持仓管理辅助
- 偏好终端工具，能接受命令行交互


## 3. 功能性需求

### 3.1 数据管理（st init / st update）

| 命令 | 说明 |
|------|------|
| `setup.sh` | 初始化工作目录、写入 shell 配置、初始化 `database.db` / `config.db`、引导配置 cron |
| `st init` | 从 baostock 拉取全A过去1年日K数据入库 |
| `st update` | 每日增量：从 akshare 拉取当日全市场数据追加入库 |
| `st cron set <hh> <mm>` | 设置每日自动执行 `st update` 的 cron 时间 |

- `setup.sh` 和 `st init` 职责分离：`setup.sh` 负责本机环境和数据库表结构初始化，`st init` 只负责抓取初始化行情数据。
- `setup.sh` 每创建一个配置、文件或 cron 项前，都必须先判断是否已经存在；如果已经存在，则跳过该 setup 步骤，进入下一步。
- `st init` 只需执行一次，后续用 `st update` 保持数据最新。
- `setup.sh` 会引导用户配置 cron：默认每天 15:05 执行 `st update`，用户也可以选择不配置 cron。
- `st cron set <hh> <mm>` 用于后续修改 cron 触发时间。
- cron 正常启用后，系统预期很少出现漏拉；如果确实漏拉，先不做自动补拉逻辑。
- `st update` 在收盘后拉取的当日快照视为正式日 K。
- 日 K 价格一律使用前复权口径。
- 数据统一存储为：code, name, date, open, close, high, low, volume
- 股票代码统一为纯 6 位数字，如 `000001`、`600519`。
- `st init` 不创建工作目录、不写 shell rc、不初始化 `config.db`、不配置 cron；个别股票拉取失败时沉默跳过，不阻断整体初始化。

### 3.2 选股扫描（st find）

| 命令 | 说明 |
|------|------|
| `st find box` | 低位箱体整理扫描 |
| `st find channel` | 上升通道扫描 |
| `st find volume_absorb` | 爆量吸筹扫描 |
| `st find independent` | 独立行情扫描 |
| `st find <scanner> --csv <path>` | 将扫描结果导出为 CSV ，不传path默认在工作区|

- 数据源：本地sqlite（日线）
- 股票池支持：全A
- 输出：终端表格，展示符合扫描条件的股票及关键指标；不按得分排序。
- 判定模型：对于一只股票，每个扫描器只判断“符合扫描条件”或“不符合扫描条件”。
- 支持导出 CSV，必须由用户显式传入 `--csv <path>`。
- 支持通过参数覆盖默认阈值。
- 具体扫描算法后续实现。扫描器采用抽象类/多态结构，每个形态一个实现，后续可扩展更多形态。

### 3.3 记录/关注池（st record）

| 命令 | 说明 |
|------|------|
| `st record add <code>` | 将股票加入关注池 |
| `st record add <code> -m <str-message>` | 将股票加入关注池，并添加备注 |
| `st record show <code>` | 查看指定股票的详情 |
| `st record note <code> <str-message> (--replace)` | 设置/更新备注，并选择是完全覆盖还是追加 |
| `st record go <code>` | 标记该股票“明天买” |
| `st record list` | 查看关注池所有股票 |
| `st record rm <code>` | 从关注池移除 |

- 记录时保存：股票代码、名称、识别到的形态、备注、加入时间、是否明天买。
- `st record add` 会自动对该股票运行一遍各个形态识别，把符合的形态写入 `pattern` 字段。
- `st record go <code>` 将 `watchlist.buy_tomorrow` 标记为 true。
- 用途：持续跟踪感兴趣但还没买入的股票，观察后续走势
- 数据存储：SQLite

### 3.4 买入提醒（st watch）

| 命令 | 说明 |
|------|------|
| `st watch` | 对关注池中的股票执行买入时机分析 |
| `st watch <code>` | 对指定股票执行买入时机分析 |

- 拉取关注池股票的最新行情
- 调用 DeepSeek API，结合形态数据和行情数据，给出是否应该买入的判断
- 输出：一句话结论 + 简短理由（关键支撑位、形态确认程度等）
- `st watch` 可重复运行；同一只股票同一天已有 watch 分析记录时，新结果覆盖当天旧记录。

### 3.5 持仓管理（st hold）

| 命令 | 说明 |
|------|------|
| `st hold in <code> --price <买入价>` | 登记买入（止损/目标价可选） |
| `st hold out <code> --price <卖出价>` | 登记卖出（平仓） |
| `st hold out <code> --price <卖出价> --dec` | 登记减仓，不关闭全部 open 持仓 |
| `st hold set <code> --stop <止损价>` | 设置/更新止损价 |
| `st hold set <code> --target <目标价>` | 设置/更新目标价 |
| `st hold set <code> --note <备注>` | 设置/更新备注 |
| `st hold show <code>` | 查看持仓详情 |
| `st hold list` | 查看当前持仓 |
| `st hold history` | 查看历史交易记录 |
| `st hold history --near <number>` | 查看最近 N 条历史交易记录 |
| `st hold history --csv <path>` | 导出历史交易记录 CSV |

- 买入时必填：代码、买入价；选填：`--stop`、`--target`、`--note`。
- 买入日期不提供参数，默认当天。
- 允许同一股票存在多笔 open 持仓。
- `st hold out <code> --price <卖出价>` 默认卖出该股票的全部 open 持仓并关闭记录。
- 传入 `--dec` 时表示发生减仓操作，不关闭全部 open 持仓；第一版不记录减仓数量，无需传入数量，只记录一次操作/备注。
- 止损/目标价可后续通过 `st hold set` 手动设置，也可由 `st alert` 分析后在用户确认后写入。
- 不计算盈亏百分比；用户在自己的交易平台查看盈亏。
- `st hold history` 展示所有 closed 记录，支持 `--near <number>` 按时间相近程度列举最近 N 条交易记录，支持 `--csv <path>` 导出。
- 数据存储：SQLite

### 3.6 卖出提醒（st alert）

| 命令 | 说明 |
|------|------|
| `st alert` | 对当前所有持仓执行卖出分析 |
| `st alert <code>` | 对指定持仓执行卖出分析 |

- 拉取持仓股票的最新行情
- 对比设定的止损/止盈线
- 调用 DeepSeek API，结合当前走势给出持有/卖出建议
- 输出：每只持仓一行结论（持有/注意/建议卖出 + 理由）
- 如果 AI 分析结果包含可写入的止损价或目标价，命令需要询问用户是否写入，用户输入 `[y/n]` 后再决定是否更新数据库。


## 4. 非功能性需求

### 4.1 数据层

本地 SQLite 缓存全 A 日K数据，扫描时零网络请求。

数据获取策略：
- **初始化（`st init`）**：通过 baostock 逐只拉取过去1年前复权历史日K，写入 SQLite。首次约35分钟，只需执行一次；失败个股沉默跳过。
- **每日增量（`st update`）**：通过 akshare `stock_zh_a_spot_em()` 一次调用获取全市场当日数据，追加入库。耗时 ~2秒。
- **自动调度**：`setup.sh` 可配置系统 cron，默认每天 15:05 自动执行 `st update`；也可通过 `st cron set <hh> <mm>` 后续修改。

统一存储字段：`code, name, date, open, close, high, low, volume`

性能目标：
- 扫描全A（从本地缓存读取）：< 30 秒
- 单只股票查询：< 1 秒
- DeepSeek API 调用单次超时上限 60 秒

### 4.2 可靠性

- baostock 网络异常时优雅降级，跳过失败个股，不输出失败个股明细
- DeepSeek API 调用失败时输出错误信息，不影响其他功能
- SQLite 写入使用事务，保证数据一致性

### 4.3 可维护性

- 扫描器采用抽象类/多态结构：每个形态一个实现，统一 `detect(df, **kwargs)` 接口
- 数据源通过 provider 层抽象，未来可替换为其他数据源
- 模型配置存储在 `<workdir>/config.db`，默认参数可通过 CLI 参数覆盖

### 4.4 可用性

- 所有命令支持 `--help`
- 错误信息就地 catch 并输出，不让单点错误导致整个命令崩溃
- 中文输出，贴合目标用户习惯

### 4.5 安全性

- DeepSeek API Key 存储在 `<workdir>/config.db` 的模型配置表中，不硬编码到源码。
- SQLite 文件存放在工作目录，默认 `~/.stock_tools`。
- 本项目面向个人使用的开源项目，不额外加入投资建议免责声明。

### 4.6 依赖约束

- Python >= 3.11
- 核心数据依赖：akshare, baostock
- AI 依赖：openai（兼容 DeepSeek API 的 OpenAI SDK）
- TUI 依赖：textual（第一版暂不实现 TUI）
- 数据库使用 Python 标准库 sqlite3


## 5. 数据模型

```sql
CREATE TABLE daily_kline (
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    date        TEXT NOT NULL,
    open        REAL NOT NULL,
    close       REAL NOT NULL,
    high        REAL NOT NULL,
    low         REAL NOT NULL,
    volume      REAL NOT NULL,
    PRIMARY KEY (code, date)
);

CREATE TABLE watchlist (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    pattern     TEXT,
    note        TEXT,
    added_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    buy_tomorrow INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE holdings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'closed'
    entry_price REAL NOT NULL,
    entry_date  TEXT NOT NULL DEFAULT (date('now', 'localtime')),
    stop_loss   REAL,
    take_profit REAL,
    exit_price  REAL,
    exit_date   TEXT,
    note        TEXT
);

CREATE TABLE ai_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    type        TEXT NOT NULL,
    conclusion  TEXT NOT NULL,
    content     TEXT NOT NULL,
    analysis_date TEXT NOT NULL DEFAULT (date('now', 'localtime')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (code, type, analysis_date)
);

CREATE TABLE model_config (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    base_url    TEXT NOT NULL,
    api_key     TEXT NOT NULL,
    model_name  TEXT NOT NULL
);
```


## 6. 技术选型

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 语言 | Python >= 3.11 | 已有代码基础，数据分析生态成熟 |
| CLI 框架 | argparse（标准库） | 零依赖，已有实现 |
| TUI 框架 | Textual | 后续阶段使用，第一版暂不实现 |
| 数据源 | baostock（历史回填）+ akshare（每日增量） | baostock 免费稳定；akshare 支持全市场一次调用 |
| AI | DeepSeek API（通过 openai SDK） | 擅长中文金融分析，OpenAI 兼容协议 |
| 持久化 | SQLite | 标准库自带，单文件，关系查询 |
| 运行模式 | 脉冲式 + cron 增量更新 | 每天收盘后自动更新，用户手动完成研究和决策 |


## 7. 项目结构

项目结构以 [modules.md](modules.md) 为准。核心边界：

- `cli/`：argparse 子命令入口，只负责参数解析、用户交互和输出调用。
- `services/`：完整用例编排层，承接 `find`、`record`、`watch`、`hold`、`alert`、`init/update/cron` 等流程。
- `scanners/`：纯形态检测算法，不直接读写数据库。
- `ai/`：OpenAI 兼容客户端、prompt 构建、AI 结果解析和结构化结果对象。
- `data/`：主库连接、schema、provider、repository。
- `config/`：`config.db` 与模型配置读写。
- `infra/`：工作目录解析、cron、shell rc 写入等系统能力。
- `output/`：终端输出与 CSV 导出，只被 CLI 调用。

当前代码几乎都需要大搬家或重构，项目结构以重构后的目标结构为准。


## 8. 里程碑

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| M1 | setup + 数据库初始化 + CLI 骨架 + 数据更新 | `setup.sh` / `st init` / `st update` / `st cron set` 可用 |
| M2 | 基础扫描闭环 | `st find box` / `st find channel` 可用，扫描器通过 service 批量执行 |
| M3 | 关注池 + 持仓管理 | `st record` + `st hold in/out/list/history` 可用 |
| M4 | DeepSeek 集成 | `st watch` + `st alert` 可用，AI 结果写入 `ai_logs` |
| M5 | 补齐扫描器 | `st find volume_absorb` + `st find independent` 可用 |
| M6 | TUI | 后续补充 TUI 需求后实现 |
