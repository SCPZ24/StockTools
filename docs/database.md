# 数据库设计

SQLite 数据库文件放在 StockTools 工作目录中。

默认工作目录：`~/.stock_tools`

用户可在 `setup.sh` 阶段自定义工作目录。

工作目录发现顺序：
1. `STOCKTOOLS_HOME` 环境变量
2. `~/.stock_tools_path`
3. 默认 `~/.stock_tools`

数据库文件：
- 主数据库：`<workdir>/database.db`
- 模型配置数据库：`<workdir>/config.db`


## ER 关系

```
daily_kline (行情数据)
    ↑ code
watchlist (关注池) ──→ 通过 code 关联行情
    ↑ code
holdings (持仓记录) ──→ 通过 code 关联行情
    ↓ id
ai_logs (AI分析记录) ──→ 关联持仓或关注池
model_config (模型配置) ──→ 存储 DeepSeek/OpenAI 兼容配置
```


## 表结构


### daily_kline — 日K线数据

存储全A股前复权历史日K线。`st init` 回填，`st update` 每日追加。

```sql
CREATE TABLE daily_kline (
    code    TEXT    NOT NULL,   -- 股票代码，如 '000001'
    name    TEXT    NOT NULL,   -- 股票名称
    date    TEXT    NOT NULL,   -- 交易日，格式 'YYYY-MM-DD'
    open    REAL    NOT NULL,   -- 开盘价
    close   REAL    NOT NULL,   -- 收盘价
    high    REAL    NOT NULL,   -- 最高价
    low     REAL    NOT NULL,   -- 最低价
    volume  REAL    NOT NULL,   -- 成交量（手）
    PRIMARY KEY (code, date)
);

CREATE INDEX idx_kline_date ON daily_kline(date);
CREATE INDEX idx_kline_code ON daily_kline(code);
```

**设计说明：**
- 复合主键 `(code, date)` 保证同一只股票同一天不会重复插入
- `date` 索引支持按日期范围查询（如 `st update` 检查最新日期）
- `code` 索引支持按股票查询（如 `st watch` 拉取单只行情）
- `volume` 用 REAL 而非 INTEGER，因为 baostock 返回的成交量可能含小数
- 价格统一使用前复权口径


### watchlist — 关注池

用户主动关注的股票，等待买入时机。

```sql
CREATE TABLE watchlist (
    code        TEXT    PRIMARY KEY,   -- 股票代码
    name        TEXT    NOT NULL,      -- 股票名称
    pattern     TEXT,                  -- 识别到的形态：'box'/'channel'/'volume_absorb'/'independent'
    note        TEXT,                  -- 用户备注
    added_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),  -- 加入时间
    buy_tomorrow INTEGER NOT NULL DEFAULT 0                            -- 是否标记“明天买”：0/1
);
```

**设计说明：**
- 一只股票只能出现一次（code 为主键），重复 add 应更新而非报错
- `pattern` 由 `st record add` 自动运行各个扫描器后写入；如果没有任何形态符合，可为空
- `st record go <code>` 将 `buy_tomorrow` 更新为 1


### holdings — 持仓记录

记录每一笔交易（买入→持有→卖出）。

```sql
CREATE TABLE holdings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL,                                        -- 股票代码
    name        TEXT    NOT NULL,                                        -- 股票名称
    status      TEXT    NOT NULL DEFAULT 'open',                         -- 'open' | 'closed'
    entry_price REAL    NOT NULL,                                        -- 买入价
    entry_date  TEXT    NOT NULL DEFAULT (date('now', 'localtime')),     -- 买入日期
    stop_loss   REAL,                                                    -- 止损价（可后设）
    take_profit REAL,                                                    -- 目标价（可后设）
    exit_price  REAL,                                                    -- 卖出价
    exit_date   TEXT,                                                    -- 卖出日期
    note        TEXT                                                     -- 备注
);

CREATE INDEX idx_holdings_status ON holdings(status);
CREATE INDEX idx_holdings_code ON holdings(code);
```

**设计说明：**
- 同一只股票允许多次建仓（不同时间段），所以用自增 id 而非 code 作主键
- `stop_loss` / `take_profit` 初始可为 NULL，通过 `st hold set` 或 `st alert` 后续填入
- 不记录盈亏百分比，用户通过自己的交易平台查看盈亏
- `st hold out <code> --price <卖出价>` 默认关闭该代码下全部 open 持仓；传入 `--dec` 时表示发生减仓操作，不关闭全部 open 持仓，不记录减仓数量，只记录一次操作/备注
- `status` 索引支持快速筛选当前持仓（`WHERE status = 'open'`）


### ai_logs — AI 分析日志

记录 DeepSeek API 调用结果，用于复盘。`st watch` 可重复运行，同一股票同一天的 watch 结果覆盖旧记录。

```sql
CREATE TABLE ai_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL,                                        -- 股票代码
    type        TEXT    NOT NULL,                                        -- 'watch'（买入分析）| 'alert'（卖出分析）
    conclusion  TEXT    NOT NULL,                                        -- AI 结论：'buy'/'hold'/'sell'/'wait'
    content     TEXT    NOT NULL,                                        -- AI 给出的内容
    analysis_date TEXT  NOT NULL DEFAULT (date('now', 'localtime')),     -- 分析日期，用于当天覆盖
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')), -- 分析时间
    UNIQUE (code, type, analysis_date)
);

CREATE INDEX idx_ai_logs_code_type ON ai_logs(code, type);
CREATE INDEX idx_ai_logs_created ON ai_logs(created_at);
```

**设计说明：**
- `content` 存储 AI 输出正文，`conclusion` 存储标准化结论
- 同一 `code + type + analysis_date` 只保留一条，重复运行时覆盖旧记录
- `conclusion` 标准化为枚举值，方便程序判断是否需要提醒用户
- 按 `(code, type)` 索引可快速查询某只股票的分析历史
- 按 `created_at` 索引支持按时间查看分析历史


### model_config — 模型配置

存储 OpenAI 兼容模型配置。该表位于 `<workdir>/config.db`。

```sql
CREATE TABLE model_config (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    base_url    TEXT    NOT NULL,   -- OpenAI 兼容接口地址，如 DeepSeek base url
    api_key     TEXT    NOT NULL,   -- API Key
    model_name  TEXT    NOT NULL    -- 模型名称
);
```

**设计说明：**
- 只保存一组当前生效的模型配置，所以固定 `id = 1`
- `setup.sh` 或后续配置命令负责写入/更新该表。`setup.sh` 写入前需要先判断是否已有记录，已有则询问是否覆盖，默认不覆盖。


## 约束与规范

| 规范 | 说明 |
|------|------|
| 代码格式 | 纯6位数字，如 `'000001'`、`'600519'`。CLI 只接受纯 6 位数字；数据源返回的市场前缀在入库时剥离 |
| 日期格式 | ISO 8601：`'YYYY-MM-DD'`（date）或 `'YYYY-MM-DD HH:MM:SS'`（datetime） |
| 事务 | 批量写入使用事务包裹，`st init` 每100只股票 commit 一次防止内存溢出 |
| WAL 模式 | 启用 `PRAGMA journal_mode=WAL`，允许读写并发（cron update 和手动查询可能同时发生） |
| 文件位置 | 默认 `~/.stock_tools/database.db` 和 `~/.stock_tools/config.db`；用户可通过 `setup.sh` 自定义工作目录 |


## 初始化 SQL

`setup.sh` 初始化 `<workdir>/database.db` 时完整运行以下脚本。创建前需要先判断数据库文件是否存在；如果已存在，只补齐缺失表，不覆盖已有数据。

```sql
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS daily_kline (
    code    TEXT    NOT NULL,
    name    TEXT    NOT NULL,
    date    TEXT    NOT NULL,
    open    REAL    NOT NULL,
    close   REAL    NOT NULL,
    high    REAL    NOT NULL,
    low     REAL    NOT NULL,
    volume  REAL    NOT NULL,
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_kline_date ON daily_kline(date);
CREATE INDEX IF NOT EXISTS idx_kline_code ON daily_kline(code);

CREATE TABLE IF NOT EXISTS watchlist (
    code        TEXT    PRIMARY KEY,
    name        TEXT    NOT NULL,
    pattern     TEXT,
    note        TEXT,
    added_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    buy_tomorrow INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS holdings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'open',
    entry_price REAL    NOT NULL,
    entry_date  TEXT    NOT NULL DEFAULT (date('now', 'localtime')),
    stop_loss   REAL,
    take_profit REAL,
    exit_price  REAL,
    exit_date   TEXT,
    note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_holdings_status ON holdings(status);
CREATE INDEX IF NOT EXISTS idx_holdings_code ON holdings(code);

CREATE TABLE IF NOT EXISTS ai_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL,
    type        TEXT    NOT NULL,
    conclusion  TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    analysis_date TEXT  NOT NULL DEFAULT (date('now', 'localtime')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (code, type, analysis_date)
);
CREATE INDEX IF NOT EXISTS idx_ai_logs_code_type ON ai_logs(code, type);
CREATE INDEX IF NOT EXISTS idx_ai_logs_created ON ai_logs(created_at);
```

`setup.sh` 初始化 `<workdir>/config.db` 时完整运行以下脚本。创建前需要先判断数据库文件是否存在；如果已存在，只补齐缺失表，不覆盖已有数据。

```sql
CREATE TABLE IF NOT EXISTS model_config (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    base_url    TEXT    NOT NULL,
    api_key     TEXT    NOT NULL,
    model_name  TEXT    NOT NULL
);
```
