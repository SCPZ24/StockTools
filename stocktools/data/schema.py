MAIN_SCHEMA_SQL = """
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
    confidence  REAL,
    degraded    INTEGER NOT NULL DEFAULT 0,
    votes       TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_logs_code_type ON ai_logs(code, type);
CREATE INDEX IF NOT EXISTS idx_ai_logs_created ON ai_logs(created_at);

CREATE TABLE IF NOT EXISTS concept_index (
    code    TEXT    PRIMARY KEY,
    name    TEXT    NOT NULL,
    active  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS concept_kline (
    code     TEXT    NOT NULL,
    date     TEXT    NOT NULL,
    open     REAL    NOT NULL,
    close    REAL    NOT NULL,
    high     REAL    NOT NULL,
    low      REAL    NOT NULL,
    volume   REAL    NOT NULL,
    amount   REAL    NOT NULL,
    pct_chg  REAL    NOT NULL,
    turnover REAL    NOT NULL,
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_concept_kline_date ON concept_kline(date);
CREATE INDEX IF NOT EXISTS idx_concept_kline_code ON concept_kline(code);

CREATE TABLE IF NOT EXISTS daily_hotspot (
    date        TEXT    NOT NULL,
    code        TEXT    NOT NULL,
    rank        INTEGER NOT NULL,
    pct_chg     REAL    NOT NULL,
    PRIMARY KEY (date, code)
);
CREATE INDEX IF NOT EXISTS idx_hotspot_date ON daily_hotspot(date);
CREATE INDEX IF NOT EXISTS idx_hotspot_code ON daily_hotspot(code);
"""
