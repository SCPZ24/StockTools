# 数据库设计

SQLite 单文件数据库，路径：`data/stocktools.db`


## ER 关系

```
daily_kline (行情数据)
    ↑ code
watchlist (关注池) ──→ 通过 code 关联行情
    ↑ code
holdings (持仓记录) ──→ 通过 code 关联行情
    ↓ id
ai_logs (AI分析记录) ──→ 关联持仓或关注池
```


## 表结构


### daily_kline — 日K线数据

存储全A股历史日K线。`st init` 回填，`st update` 每日追加。

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


### watchlist — 关注池

用户主动关注的股票，等待买入时机。

```sql
CREATE TABLE watchlist (
    code        TEXT    PRIMARY KEY,   -- 股票代码
    name        TEXT    NOT NULL,      -- 股票名称
    pattern     TEXT,                  -- 识别到的形态：'box_break'/'channel'/'volume_absorb'/'independent'
    note        TEXT,                  -- 用户备注
    added_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),  -- 加入时间
    buy_tomorrow BOOLEAN NOT NULL DEFAULT FALSE                        -- 是否来到买入时机
);
```

**设计说明：**
- 一只股票只能出现一次（code 为主键），重复 add 应更新而非报错
- `pattern` 可为空（用户手动加入时可能不指定形态）


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
    pnl_pct     REAL,                                                    -- 盈亏百分比，平仓时计算
    note        TEXT                                                     -- 备注
);

CREATE INDEX idx_holdings_status ON holdings(status);
CREATE INDEX idx_holdings_code ON holdings(code);
```

**设计说明：**
- 同一只股票允许多次建仓（不同时间段），所以用自增 id 而非 code 作主键
- `stop_loss` / `take_profit` 初始可为 NULL，通过 `st hold set` 或 `st alert` 后续填入
- `pnl_pct` 在 `st hold out` 时计算：`(exit_price - entry_price) / entry_price * 100`
- `status` 索引支持快速筛选当前持仓（`WHERE status = 'open'`）


### ai_logs — AI 分析日志

记录每次 DeepSeek API 调用的结果，用于复盘和避免重复调用。

```sql
CREATE TABLE ai_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL,                                        -- 股票代码
    type        TEXT    NOT NULL,                                        -- 'watch'（买入分析）| 'alert'（卖出分析）
    conclusion  TEXT    NOT NULL,                                        -- AI 结论：'buy'/'hold'/'sell'/'wait'
    content     TEXT    NOT NULL,                                        -- AI 给出的内容
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))  -- 分析时间
);

CREATE INDEX idx_ai_logs_code_type ON ai_logs(code, type);
CREATE INDEX idx_ai_logs_created ON ai_logs(created_at);
```

**设计说明：**
- 每次调用 `st watch` 或 `st alert` 都记录一条，不覆盖历史
- `conclusion` 标准化为枚举值，方便程序判断是否需要提醒用户
- 按 `(code, type)` 索引可快速查询某只股票的分析历史
- 按 `created_at` 索引支持"今天已分析过则跳过"的去重逻辑


## 约束与规范

| 规范 | 说明 |
|------|------|
| 代码格式 | 纯6位数字，如 `'000001'`、`'600519'`。不带市场前缀（baostock 的 `sh.`/`sz.` 在入库时剥离） |
| 日期格式 | ISO 8601：`'YYYY-MM-DD'`（date）或 `'YYYY-MM-DD HH:MM:SS'`（datetime） |
| 事务 | 批量写入使用事务包裹，`st init` 每100只股票 commit 一次防止内存溢出 |
| WAL 模式 | 启用 `PRAGMA journal_mode=WAL`，允许读写并发（cron update 和手动查询可能同时发生） |
| 文件位置 | `data/stocktools.db`，纳入 `.gitignore` |


## 初始化 SQL

`st init` 执行时完整运行以下脚本：

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
    added_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
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
    pnl_pct     REAL,
    note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_holdings_status ON holdings(status);
CREATE INDEX IF NOT EXISTS idx_holdings_code ON holdings(code);

CREATE TABLE IF NOT EXISTS ai_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL,
    type        TEXT    NOT NULL,
    conclusion  TEXT    NOT NULL,
    reason      TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_ai_logs_code_type ON ai_logs(code, type);
CREATE INDEX IF NOT EXISTS idx_ai_logs_created ON ai_logs(created_at);
```
