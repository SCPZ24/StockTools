# v1 PRD — 概念板块热点监控

> 版本: v1.1
> 日期: 2026-06-24
> 状态: 评审已修订

---

## 0. 评审修订记录（v1.0 → v1.1）

| # | 变更 | 原因 |
|---|------|------|
| 1 | 概念抓取统一直连东财、固定 `trust_env=False`，复用共享 Eastmoney session（含多 host 镜像兜底） | 本地代理不稳定，抓取业务不依赖代理；裸请求已验证可用 |
| 2 | `st update` 改为「补缺口」增量，而非「只拉当天」 | 漏跑一次会在 `concept_kline` / `daily_hotspot` 留永久空洞，污染窗口计算 |
| 3 | 删除热点四态状态机；改为每次程序启动从库内重算热点集合（无持久化状态） | 状态机与「不建表」自相矛盾，且原算法无法实现「消退/冷却」 |
| 4 | 热点判定加回「连续 3 天上榜」OR 条件 | 纯 7/10 规则有 ~7 日滞后，抓不到新鲜轮动；补此条成本极低 |
| 5 | 日涨幅榜用一次列表调用产出，不为排名拉 494 次 K 线 | 列表接口单次即返回全部板块当日涨跌幅 |
| 6 | `concept_kline` 改为按需懒加载刷新（`show`/`hot` 用到才补），不每日全量刷新 | 把「排名成本」与「K 线成本」拆开 |
| 7 | 新增盘中运行防护：交易日 09:30–11:30 / 13:00–15:00 拒绝运行（`--force` 越过） | 盘中 `pct_chg` 为实时值，会污染排名与窗口 |
| 8 | 趋势判定一律日线，复用 `scanners/ma_alignment.py` | 全项目 scanner 不看周线 |
| 9 | 合并 `list`/`top`；明确建表迁移触发点；补测试任务 | 评审建议 |

---

## 1. 概述

在现有个股形态扫描体系之上，增加**概念板块热点监控**模块。用户打开工具后不仅能看到个股形态，还能知道"当前市场在炒什么"，从而优先在热点板块内选股，提高胜率。

### 核心原则

- 只做概念板块 K 线抓取 + 涨幅排名 + 短期小热点检测
- **不做**市场主线探测（抛弃成分股过滤、市值过滤等复杂逻辑）
- 数据源：东方财富概念板块 API（直连，不走 akshare，固定不依赖系统代理）
- 数据存储：与个股共用 `database.db`，但独立建表，不混入 `daily_kline`
- 热点判定**无状态**：不持久化热点状态，每次程序启动从库内重算

---

## 2. 数据源

> 两个接口均复用现有直连东财的请求方式（见 §7.1），固定 `trust_env=False`，
> 不依赖系统代理；裸请求已验证可用。

### 2.1 概念板块列表（含当日涨跌幅，用于排名）

```
GET https://push2.eastmoney.com/api/qt/clist/get
  ?pn=1&pz=500&po=1&np=1&fltt=2&invt=2
  &fid=f3
  &fs=m:90 t:3 f:!50
  &fields=f12,f14,f2,f3
```

| 字段 | 含义 | 示例 |
|------|------|------|
| f12 | 板块代码 | BK1128 |
| f14 | 板块名称 | CPO概念 |
| f2 | 最新价 | 2145.32 |
| f3 | 涨跌幅(%) | 3.21 |

**特性**：一次返回全部约 494 个概念板块的**当日涨跌幅**，无需分页。
→ 这意味着「当日涨幅榜（`daily_hotspot`）只需 1 次请求即可产出」，不必为排名逐板块拉 K 线。

### 2.2 概念板块历史 K 线（按需懒加载）

```
GET https://push2his.eastmoney.com/api/qt/stock/kline/get
  ?secid=90.BK1128
  &fields1=f1,f2,f3,f4,f5,f6
  &fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61
  &klt=101                          ← 日K
  &fqt=1                            ← 前复权
  &beg=20240101
  &end=20260624
```

K 线数据每行格式：`日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率`

| 索引 | 字段 | 示例 |
|------|------|------|
| 0 | 日期 | 2024-01-02 |
| 1 | 开盘 | 1589.42 |
| 2 | 收盘 | 1603.21 |
| 3 | 最高 | 1620.15 |
| 4 | 最低 | 1580.33 |
| 5 | 成交量(手) | 4839201 |
| 6 | 成交额(元) | 8.21e9 |
| 7 | 振幅(%) | 2.51 |
| 8 | 涨跌幅(%) | 1.23 |
| 9 | 涨跌额 | 19.45 |
| 10 | 换手率(%) | 3.87 |

**特性**：
- 一次调用返回指定日期范围内的全部日 K，支持 `beg`/`end`，便于按缺口区间回补
- 仅在 `st init`（全量回填）、以及 `st concept show` / `st concept hot` 需要某板块趋势/累计涨幅时**按需调用**，不在每日 `st update` 中全量刷新

---

## 3. 数据库设计

> 全部并入现有 `database.db`（`Paths.database_path`），新表写进
> `stocktools/data/schema.py` 的 `MAIN_SCHEMA_SQL`，沿用 `CREATE TABLE IF NOT EXISTS`
> 幂等建表（迁移触发点见 §7.5）。

### 3.1 concept_index — 概念板块索引表

```sql
CREATE TABLE IF NOT EXISTS concept_index (
    code    TEXT    PRIMARY KEY,   -- BK1128
    name    TEXT    NOT NULL,      -- CPO概念
    active  INTEGER NOT NULL DEFAULT 1  -- 1=活跃, 0=已退市/停更
);
```

- `st init` 时全量写入约 494 条
- `st update` 时按列表接口结果对账（见 §4.2 的「增/删/改」语义）

### 3.2 concept_kline — 概念板块日 K 表

```sql
CREATE TABLE IF NOT EXISTS concept_kline (
    code    TEXT    NOT NULL,      -- BK1128
    date    TEXT    NOT NULL,      -- 2024-01-02
    open    REAL    NOT NULL,
    close   REAL    NOT NULL,
    high    REAL    NOT NULL,
    low     REAL    NOT NULL,
    volume  REAL    NOT NULL,      -- 成交量(手)
    amount  REAL    NOT NULL,      -- 成交额(元)
    pct_chg REAL    NOT NULL,      -- 涨跌幅(%)
    turnover REAL   NOT NULL,      -- 换手率(%)
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_concept_kline_date ON concept_kline(date);
CREATE INDEX IF NOT EXISTS idx_concept_kline_code ON concept_kline(code);
```

与 `daily_kline` 的区别：
- 多了 `amount`（成交额）、`pct_chg`（涨跌幅）、`turnover`（换手率）
- 板块级别的数据更适合用成交额和换手率判断资金流向
- OHLCV 列与个股 `daily_kline` 同构，可直接喂给现有 scanner（见 §7.6）

### 3.3 daily_hotspot — 每日涨幅榜表（派生表）

```sql
CREATE TABLE IF NOT EXISTS daily_hotspot (
    date        TEXT    NOT NULL,      -- 2026-06-24
    code        TEXT    NOT NULL,      -- BK1128
    rank        INTEGER NOT NULL,      -- 1-10
    pct_chg     REAL    NOT NULL,      -- 当日涨幅(%)
    PRIMARY KEY (date, code)
);
CREATE INDEX IF NOT EXISTS idx_hotspot_date ON daily_hotspot(date);
CREATE INDEX IF NOT EXISTS idx_hotspot_code ON daily_hotspot(code);
```

- 行式存储（非宽表），方便按板块维度查询历史
- 每天存涨幅前 10 的概念板块及其涨幅与名次
- 本表是**热点判定的唯一输入**；热点集合本身不落库（见 §5）

---

## 4. 数据生命周期

### 4.1 `st init` — 初始化

1. （前置）确保库表存在：调用 `Paths.init_databases()`（幂等，见 §7.5）
2. 调概念列表 API → 写入 `concept_index`（全量约 494 条）
3. 逐板块调历史 K 线 API（约 494 次请求）→ 写入 `concept_kline`
4. 对每个交易日，从 `concept_kline` 取该日全部板块 `pct_chg` 排序取前 10 → 写入 `daily_hotspot`（历史回填）
5. 不做热点持久化；热点集合在程序运行时按需重算（见 §5）

**预估耗时**：约 494 次 HTTP 请求（拉历史 K 线），串行约 2–3 分钟。

> 历史排名说明：某板块若在窗口内某天尚未成立或停更，则该日无 K 线行、不参与当日排名，
> 属预期行为；按 `date` 聚合排名即可，无需特殊处理。

### 4.2 `st update` — 每日更新（补缺口）

0. **盘中防护**：若当前为交易日且系统时间落在 09:30–11:30 或 13:00–15:00，
   则提示并拒绝运行（`--force` 可越过，见 §7.4）。
1. （前置）确保库表存在：`Paths.init_databases()`（幂等）
2. 调概念列表 API（1 次请求）→ 与 `concept_index` 对账：
   - 列表中有、库中无 → **新增** insert（`active=1`）
   - 库中有、列表中无 → **失效** 置 `active=0`（板块极少退市，多为停更）
   - 同 `code` 名称变化 → **改名** update `name`（`code` 稳定，`name` 可变）
3. 计算 `daily_hotspot` 缺口 `gap = [库内最新榜单日 + 1, 最近交易日]`：
   - **无缺口 / 仅缺当天（常规）**：直接用步骤 2 列表接口返回的当日 `pct_chg`
     排序取前 10 → 写入今日 `daily_hotspot`（**0 次额外 K 线请求**）
   - **多日缺口**（漏跑/长假后）：对活跃板块按区间拉 K 线（约 494 次）→ upsert
     `concept_kline` → 对每个缺失交易日排名取前 10 → 回补 `daily_hotspot`
4. 热点集合按需重算（见 §5），不落库

**预估耗时**：常规日仅 1 次列表请求，秒级；多日缺口回补与 init 同量级（约 2–3 分钟）。

> `st update` 已由现有 cron（`st cron set`）每日驱动，概念更新随个股更新一并完成，
> 无需新增定时任务。

---

## 5. 短期小热点检测算法

### 5.1 定义

> 一个概念板块满足以下**任一**条件，即标记为"短期小热点"：
>
> - **条件 A（持续型）**：连续 10 个交易日内有 **≥7 天**出现在涨幅前 10 名
> - **条件 B（爆发型）**：最近 **连续 3 个交易日**均出现在涨幅前 10 名

条件 B 用于及时捕捉新鲜轮动（条件 A 有 ~7 日滞后）。

### 5.2 算法（运行时内存重算，无状态）

```
触发时机: 程序启动 / 每次执行 st concept 命令
输入: daily_hotspot 表（最近 ≥10 个交易日）
输出: 当前热点板块列表（仅内存）

1. 读取最近 10 个交易日的 daily_hotspot 记录入内存
2. 按板块 code 分组，得到每个板块的上榜交易日集合
3. 条件 A: 窗口内上榜次数 ≥ 7
4. 条件 B: 最近 3 个连续交易日均上榜
5. 满足 A 或 B 即入选；记录命中的条件（用于展示）
6. 按近期累计涨幅（取自 concept_kline，按需懒加载）降序排列
```

### 5.3 状态与持久化

- **不建热点状态表，不持久化热点集合，不维护「激活/持续/消退/冷却」状态机。**
- 每次程序启动时从 `daily_hotspot` 重新计算当前热点集合并载入内存。
- 展示为二元结果（是/否热点）+ 命中条件（7/10、连续3天、或两者）。
- `daily_hotspot` 是唯一持久化的判定依据，本身在 `st init`/`st update` 时维护。

---

## 6. CLI 命令

### 6.1 `st concept` — 概念板块总览

```
st concept [subcommand]

子命令:
  top       涨幅榜：默认前 20；--all 显示全部并分页
  hot       显示当前短期小热点板块
  show BK   查看单个概念板块的详细走势
```

> 评审合并：原 `list`（全量按涨幅排序）与 `top`（前 N）高度重叠，统一为
> `top -n N` / `top --all`。

### 6.2 `st concept top`

```
$ st concept top -n 10
日期: 2026-06-24
排名  代码       名称          涨幅       成交额(亿)
 1   BK1101    先进封装       +3.87%     152.3
 2   BK1128    CPO概念        +3.21%      98.7
 ...
```

默认显示前 20；`--all` 显示全部约 494 个，按涨幅降序，每页 20 行分页。

### 6.3 `st concept hot`

```
$ st concept hot
当前短期小热点:
  BK1128  CPO概念       [10日7上榜 + 连续3天]   上榜 9/10天   累计 +18.5%
  BK1101  先进封装      [10日7上榜]             上榜 8/10天   累计 +14.2%
  BK1136  光通信模块    [连续3天]               连续 3天      累计 +9.4%
```

每行标注命中的条件（A / B / 两者）。无「消退/冷却」分区——热点判定无状态。

### 6.4 `st concept show`

```
$ st concept show BK1128
CPO概念 (BK1128)
├─ 最新价: 2145.32  (+3.21%)
├─ 成交额: 98.7亿
├─ 趋势(日线): 多头排列 (MA5>MA10>MA20>MA60)
├─ 近5日涨幅: +8.7%
├─ 近10日涨幅: +18.5%
├─ 近30日涨幅: +35.2%
├─ 热点状态: 🔥 短期小热点 (10日7上榜 + 连续3天)
└─ 近10日上榜记录:
   ████████░░  (8天)
```

- 趋势判定一律**日线**（复用 `scanners/ma_alignment.py`，见 §7.6）
- 进入命令时对该板块 `concept_kline` 做缺口懒加载（补到最近交易日）再渲染

---

## 7. 技术要点

### 7.1 HTTP 客户端（直连东财，不依赖代理）

- 固定 `session.trust_env = False`：本地代理环境不稳定，抓取业务**完全不依赖代理**；
  裸请求已验证可正常访问东财。
- 复用现有直连东财的请求封装（`akshare_provider.py` 已直连 `push2.eastmoney.com`）：
  抽出共享的 Eastmoney session helper，保留**多 host 镜像兜底**（`82.push2` /
  `push2` / `40.push2`，与代理开关正交，纯提升可用性）及 `UA + Referer` 头。
- K 线接口（§2.2）若发现需要 `ut` token 才放行，沿用同一 token；上线前实测确认。

### 7.2 请求频率

约 494 次请求对东财 API 是安全的（个股扫描是 5000 次才会封 IP）。后续概念板块年增
约 20–30 个，需注意 800+ 次可能逼近阈值。当前设计安全。

### 7.3 增量更新策略（双维度补缺口）

- **`daily_hotspot`（排名）**：常规日用 1 次列表调用即可；多日缺口才回补 K 线区间。
- **`concept_kline`（趋势/累计涨幅）**：按需懒加载，`show`/`hot` 用到哪个板块就把
  它补到最近交易日（gap-aware，`beg`/`end` 指定缺口区间）。
- 不在每日 `st update` 全量刷新 494 板块 K 线。

### 7.4 盘中运行防护

- 交易日（周一至周五）系统时间落在 **09:30–11:30** 或 **13:00–15:00** 时，
  `st update` 整体提示并拒绝运行（个股 + 概念更新一并受此守卫保护，因盘中快照为实时值）。
- 提供 `--force` 越过守卫（供调试 / 特殊场景）。
- **已知简化**：不识别法定节假日——节假日落在工作日时间窗会被误拒，属安全侧（偏保守），
  必要时用 `--force`。

### 7.5 建表与迁移

- 新表加入 `stocktools/data/schema.py` 的 `MAIN_SCHEMA_SQL`，`CREATE TABLE IF NOT EXISTS` 幂等。
- 现状：`Paths.init_databases()` 仅在 TUI 启动与 `st config` 触发，**未挂在 `st init`/`st update`**
  （`cli/common.py:db_path()` 只做 `ensure_workdir`）。
- 为保证老 v0 用户升级后概念表能建出来：在 `st init` / `st update` 入口先调用一次
  `Paths.init_databases()`（幂等、廉价）。

### 7.6 复用现有 scanner 做日线趋势

- 多头排列判定复用 `stocktools/scanners/ma_alignment.py`，不在 `concept_service` 重写。
- `concept_kline` 的 `code/date/open/close/high/low/volume` 与个股 scanner 所需 DataFrame
  同构，取 K 线后直接复用 MA 计算工具（`scanners/utils.py`）。

---

## 8. 实现任务拆解

| 序号 | 任务 | 涉及文件 | 预估 |
|------|------|---------|------|
| 1 | 新增 `concept_index` / `concept_kline` / `daily_hotspot` 建表 SQL | `data/schema.py` | 小 |
| 2 | 抽共享 Eastmoney session helper（`trust_env=False` + 多 host 兜底） | `data/providers/eastmoney_session.py` | 小 |
| 3 | 实现东财概念 API 数据提供者（列表 + K线，独立类，不强行继承 `BaseProvider`） | `data/providers/eastmoney_concept_provider.py` | 中 |
| 4 | 实现 `ConceptKlineRepo`（upsert / 缺口查询 / 取窗口 K 线） | `data/repos/concept_kline_repo.py` | 中 |
| 5 | 实现 `ConceptHotspotRepo`（写/读 `daily_hotspot`，取最近 N 交易日） | `data/repos/concept_hotspot_repo.py` | 小 |
| 6 | `DataService.init_history()` 集成概念初始化（全量 K 线 + 历史榜单回填） | `services/data_service.py` | 中 |
| 7 | `DataService.update_daily()` 集成概念补缺口更新 + 盘中守卫 + 入口建表 | `services/data_service.py` | 中 |
| 8 | 热点检测算法（A/B 条件，运行时内存重算）+ 累计涨幅 | `services/concept_service.py` | 中 |
| 9 | 趋势判定复用 `ma_alignment` 适配概念 K 线 | `services/concept_service.py` | 小 |
| 10 | 实现 `st concept` CLI（`top` / `hot` / `show`，含懒加载刷新） | `cli/cmd_concept.py` | 中 |
| 11 | 注册 CLI 命令到 main parser | `cli/main.py` | 小 |
| 12 | 单元测试：热点检测（A/B 边界）、缺口计算、对账逻辑 | `tests/test_concept.py` | 中 |
| 13 | TUI 概念板块页面（可选，v1.1+） | `tui/screens/concept.py` | 大 |
