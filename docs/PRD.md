# 产品需求文档

## 1. 产品概述

StockTools（命令行名：`st`）是一个面向 A 股中长线投资者的终端工具。核心目标是让用户每天只花 10 分钟完成选股、跟踪、买卖决策的完整工作流。

形态：CLI + TUI。

数据持久化使用 SQLite。


## 2. 用户画像

- 有一定技术分析基础的 A 股散户
- 只做中长线（持仓周期数周到数月），只做多
- 日常使用同花顺看盘，但需要自动化的形态筛选和持仓管理辅助
- 偏好终端工具，能接受命令行交互


## 3. 功能性需求

### 3.1 数据管理（st init / st update）

| 命令 | 说明 |
|------|------|
| `st init` | 首次初始化：从 baostock 拉取全A过去1年日K数据入库 |
| `st update` | 每日增量：从 akshare 拉取当日全市场数据追加入库 |

- `st init` 只需执行一次，后续用 `st update` 保持数据最新。init的同时也会创建其他表，相当于项目setup。
- `st update` 可通过系统 cron 每天 15:05 自动执行
- 数据统一存储为：code, name, date, open, close, high, low, volume
只拉取当天快照。所以如果没有每天都运行update，那就得重新init了。

### 3.2 选股扫描（st find）

| 命令 | 说明 |
|------|------|
| `st find box_break` | 低位箱体突破扫描 |
| `st find channel` | 上升通道扫描 |
| `st find volume_absorb` | 爆量吸筹扫描 |
| `st find independent` | 独立行情扫描 |

- 数据源：本地sqlite（日线）
- 股票池支持：全A
- 输出：终端表格，按得分排序，展示关键指标
- 支持导出 CSV
- 支持通过参数覆盖默认阈值

### 3.3 记录/关注池（st record）

| 命令 | 说明 |
|------|------|
| `st record add <code>` | 将股票加入关注池 |
| `st record add <code> -m <str-message>` | 将股票加入关注池，并添加备注 |
| `st record show <code>` | 查看指定股票的详情 |
| `st record set <code> --note <str-message>` | 设置/更新备注 |
| `st record go <code>` | 用户设置标记股票来到买入时机 |
| `st record list` | 查看关注池所有股票 |
| `st record rm <code>` | 从关注池移除 |

- 记录时保存：股票代码、名称、识别到的形态、备注、加入时间
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

### 3.5 持仓管理（st hold）

| 命令 | 说明 |
|------|------|
| `st hold in <code> --price <买入价>` | 登记买入（止损/目标价可选） |
| `st hold out <code> --price <卖出价>` | 登记卖出（平仓） |
| `st hold set <code> --stop <止损价>` | 设置/更新止损价 |
| `st hold set <code> --target <目标价>` | 设置/更新目标价 |
| `st hold set <code> --note <备注>` | 设置/更新备注 |
| `st hold show <code>` | 查看持仓详情 |
| `st hold list` | 查看当前持仓 |
| `st hold history` | 查看历史交易记录 |

- 买入时必填：代码、买入价；选填：`--stop`、`--target`、`--note`
- 止损/目标价可后续通过 `st hold set` 手动设置，也可由 `st alert` 分析后自动填入
- 卖出时关闭持仓记录，计算盈亏
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


## 4. 非功能性需求

### 4.1 数据层

本地 SQLite 缓存全 A 日K数据，扫描时零网络请求。

数据获取策略：
- **初始化（`st init`）**：通过 baostock 逐只拉取过去1年历史日K，写入 SQLite。首次约35分钟，只需执行一次。
- **每日增量（`st update`）**：通过 akshare `stock_zh_a_spot_em()` 一次调用获取全市场当日数据，追加入库。耗时 ~2秒。
- **自动调度**：可配合系统 cron 每天 15:05 自动执行 `st update`。

统一存储字段：`code, name, date, open, close, high, low, volume`

性能目标：
- 扫描全A（从本地缓存读取）：< 30 秒
- 单只股票查询：< 1 秒
- DeepSeek API 调用单次超时上限 60 秒

### 4.2 可靠性

- baostock 网络异常时优雅降级，跳过失败个股，继续扫描
- DeepSeek API 调用失败时输出错误信息，不影响其他功能
- SQLite 写入使用事务，保证数据一致性

### 4.3 可维护性

- 扫描器采用插件式结构：每个形态一个模块，统一 `detect(df, **kwargs)` 接口
- 数据源通过 provider 层抽象，未来可替换为其他数据源
- 配置集中管理（config.py），默认参数可通过 CLI 参数覆盖

### 4.4 可用性

- 所有命令支持 `--help`
- 错误信息明确，告知用户如何修正
- 中文输出，贴合目标用户习惯

### 4.5 安全性

- DeepSeek API Key 通过环境变量传入，不硬编码
- SQLite 文件存放在项目内 `data/` 目录，纳入 `.gitignore`

### 4.6 依赖约束

- Python >= 3.11
- 核心依赖：baostock, pandas, numpy
- AI 依赖：openai（兼容 DeepSeek API 的 OpenAI SDK）
- 零前端依赖，纯终端运行


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
    added_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
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
    pnl_pct     REAL,
    note        TEXT
);
```


## 6. 技术选型

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 语言 | Python >= 3.11 | 已有代码基础，数据分析生态成熟 |
| CLI 框架 | argparse（标准库） | 零依赖，已有实现 |
| TUI 框架 | Textual | 现代组件化，rich 生态，适合表格展示 |
| 数据源 | baostock（历史回填）+ akshare（每日增量） | baostock 免费稳定；akshare 支持全市场一次调用 |
| AI | DeepSeek API（通过 openai SDK） | 擅长中文金融分析，OpenAI 兼容协议 |
| 持久化 | SQLite | 标准库自带，单文件，关系查询 |
| 运行模式 | 脉冲式（用户手动调用） | 每天收盘后跑，匹配10分钟工作流 |


## 7. 项目结构

```
st (CLI入口)
├── commands/         # 子命令实现
│   ├── find.py       # 选股扫描
│   ├── record.py     # 关注池管理
│   ├── watch.py      # 买入提醒
│   ├── hold.py       # 持仓管理
│   └── alert.py      # 卖出提醒
├── scanners/         # 形态检测算法（已有）
├── data/             # 数据源层（已有）
├── ai/               # DeepSeek API 封装
├── db/               # SQLite 存储层
├── output/           # 输出格式化（已有）
└── config.py         # 全局配置（已有）
```


## 8. 里程碑

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| M1 | 数据层 + CLI 骨架 + 现有扫描器迁移 | `st init` / `st update` / `st find box_break` / `st find channel` 可用 |
| M2 | 持仓管理 + 关注池 | `st hold in/out/list` + `st record` 可用 |
| M3 | DeepSeek 集成 | `st watch` + `st alert` 可用 |
| M4 | 补齐扫描器 | `st find volume_absorb` + `st find independent` 可用 |
| M5 | TUI | 交互式界面 |
