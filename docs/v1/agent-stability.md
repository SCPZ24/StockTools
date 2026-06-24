# v1 设计 — AI 分析稳定性（Ensemble + 结构化输出）

> 版本: v1.0
> 日期: 2026-06-24
> 状态: 已评审定稿，待实现

---

## 1. 背景与问题

现有 AI 分析（`st watch` 买入分析、`st alert` 持仓止盈止损）存在两类不稳定，均已定位到代码根因：

### 症状 A：同股、同交易日，结论一会儿看多一会儿看空
- **无 read-through 缓存，每次真重算并覆盖**：[services/watch_service.py](../../stocktools/services/watch_service.py) 每次都重新调模型再 upsert，同日两次 = 两个独立采样。
- **解码本身随机**：[ai/client.py](../../stocktools/ai/client.py) `temperature=0.2` 无 seed，在"多空均衡"的票上来回掷硬币。
- **放大器**：直接把 30 行原始 CSV 丢给模型"看图"，每次感知略有不同。

### 症状 B：Agent「忘记返回」buy/wait 等字段
- 实为**解析器静默兜底**：[ai/watch_analyst.py](../../stocktools/ai/watch_analyst.py) 用正则抓 `conclusion:` 行，模型只要包 markdown / 换行 / 改中文，正则 miss → 静默退化成 `wait`。
- [ai/alert_analyst.py](../../stocktools/ai/alert_analyst.py) 单行正则更脆，止损止盈分两行就双双 `None`，却仍拼成"成功"的结论串。

---

## 2. 设计原则与已定决策

| 项 | 结论 | 理由 |
|----|------|------|
| 缓存 | **不做** | 用户会主动多跑几次以获得更稳的判断，期望"说法不同但思路类似、决策相近"；缓存=每次返回完全一样，违背诉求 |
| 结构化输出 | **JSON + 校验 + 1 次纠错重试** | 消灭"丢字段"；解析失败显式降级，绝不静默兜底成 `wait` |
| temperature / seed | **不依赖、不强制为 0** | 服务商支持度不一；且 ensemble **需要** 5 路有差异性才有投票意义，故保持非零默认温度 |
| 输入特征 | **代码直算指标，替代原始 CSV，且不碰 scanner** | scanner 天生为找多头信号设计，其形态确认会诱导模型看多；改喂中性数值事实 |
| prompt 决策准则 | **不加** | 会破坏模型思考的发散性 |
| 稳定机制 | **5 路独立推理 + reflection 仲裁** | 稳定性来自共识，而非缓存或解码确定性 |

---

## 3. 总体架构

```
用户 → CLI(cmd_watch/cmd_alert) ┐
                                 ├─→ WatchService / AlertService.analyze(on_progress)
用户 → TUI(app._do_watch/_alert)┘            │
                                              ▼
                                   ┌──────  Ensemble 编排  ──────┐
   ai/features.py (代码直算指标) ──▶│  1) 并发跑 5 路单路分析       │
                                   │  2) 代码统计共识(确定性)       │
                                   │  3) 不达标→重跑(≤3 轮)        │
                                   │  4) 仲裁 agent 合成总体概要    │
                                   └──────────────┬───────────────┘
                                                  ▼
                                   ai_logs (追加一行: 结论+概要+置信+原始票)
```

**关键**：分析逻辑单源于 Service 层，CLI 与 TUI 都调同一个 `analyze`（现状已如此，见 §7）。

---

## 4. 组件设计

### 4.1 特征预计算 `ai/features.py`（新增，纯计算，不引 scanner）

由 K 线 DataFrame 直接算出**中性数值事实**，组成 JSON 传给模型：

| 字段 | 含义 |
|------|------|
| `close`, `pct_chg` | 最新收盘价、当日涨跌幅 |
| `ma5/ma10/ma20/ma60` | 各均线最新值 |
| `ma5_slope/ma10_slope/ma20_slope` | 各均线近 5 日斜率（%/日 或线性回归斜率） |
| `dist_to_ma20`, `dist_to_ma60` | 收盘价相对均线的偏离百分比 |
| `ret_5d/ret_10d/ret_20d` | 近 5/10/20 个交易日收益率 |
| `volatility_20d` | 近 20 日日收益标准差 |

- 只给数值，不给"多头排列""突破确认"等带倾向的判断词，由模型自行解读。
- 可附最后 ~5 根 OHLC 原始行做 sanity，但**移除原 30 行 CSV 倾倒**。
- 复用 `scanners/utils.py` 的 MA 计算工具，但**不调用任何 scanner、不读 watchlist 的 `pattern` 字段**（见 §6）。

### 4.2 单路分析器（JSON 契约 + 校验 + 重试 + 降级）

**watch 单路输出**：
```json
{
  "trend": "up | down | range",
  "conclusion": "buy | wait | hold | sell",
  "confidence": 0.0,
  "analysis": "一段分析"
}
```
必填：`conclusion`(枚举) 与 `analysis`；`trend`/`confidence` 请求但非强制。

**alert 单路输出**：
```json
{
  "stop_loss": 12.50,
  "take_profit": 18.00,
  "analysis": "一段分析"
}
```
必填：`stop_loss` / `take_profit`（均须 > 0）与 `analysis`。

**解析与降级流程**（每一路独立执行）：
1. `json.loads`；失败则正则抽取首个 `{...}` 块再试。
2. 校验必填字段与枚举/数值合法性。
3. 不通过 → 追加纠错消息（"上次输出无法解析为合法 JSON / 缺少 conclusion，请只输出 JSON"）**重试 1 次**。
4. 仍不通过 → 该路标记 **degraded（无效票）**，不参与投票。

**客户端改动** [ai/client.py](../../stocktools/ai/client.py)：`invoke` 增 `response_format={"type":"json_object"}`（服务商支持即生效，不支持则靠上面的抽取+校验+重试兜底）；保持非零温度（ensemble 需要差异性）。

### 4.3 Ensemble 编排 `ai/ensemble.py`（新增）

**通用参数**：`SAMPLES=5`，`ROUNDS_MAX=3`，单路重试=1，无效票补跑总尝试设上限。

**watch（分类共识）**：
```
for round in 1..ROUNDS_MAX:
    votes = 并发跑 5 路单路分析（无效票补跑至凑满 5 个有效票）
    按 conclusion 计票；top_label, top_count = 最高票
    if top_count >= 4:                      # 代码确定性判定，不交给 LLM
        summary = 仲裁(votes, agreed=top_label)
        return {conclusion: top_label, content: summary,
                confidence: top_count/5, degraded: False, votes}
# 3 轮仍无 4/5 → 终态
plurality_label, plurality_count = 末轮最高票
summary = 仲裁(votes, agreed=plurality_label, note="未达强共识")
return {conclusion: plurality_label, content: summary,
        confidence: plurality_count/5, degraded: True, votes}
```

**alert（数值共识，取中位数）**：
```
for round in 1..ROUNDS_MAX:
    votes = 并发跑 5 路（补跑至 5 个有效票）
    sl = median(5 个 stop_loss); tp = median(5 个 take_profit)
    # 与 4/5 哲学一致的数值口径：≥4 个值落在中位数 ±TOL% 内即共识
    if within_tol(stop_loss, sl, TOL) >= 4 and within_tol(take_profit, tp, TOL) >= 4:
        summary = 仲裁(votes)
        return {stop_loss: sl, take_profit: tp, content: summary, degraded: False, votes}
# 终态
summary = 仲裁(votes, note="离散度偏高")
return {stop_loss: median, take_profit: median, content: summary, degraded: True, votes}
```
`TOL` 为可调阈值（默认 ±5%~±8%，实测后定）。

**仲裁 agent（reflection）**：
- **只在共识达成或终态时被调用一次**，失败轮不调（省成本）。
- 职责**仅是合成总体概要**——把 N 段分析揉成一段连贯说法；4/5 的布尔判定由代码完成，**不让 LLM 数票**（否则把要消灭的不稳定又请回来）。
- 输出 `{"summary": "..."}`，同样走 JSON 校验。
- 终态时概要需点出分歧（"5 路中 3 路看 X、2 路看 Y，倾向 X 但置信不足"）。

**共识口径**：先用**严格同标签**（4/5 完全一致）。若实测重跑过于频繁，再引入分桶（buy+hold 偏多 / sell+wait... 等）作为可调项——本期不做。

---

## 5. 持久化：`ai_logs` 由覆盖改追加

现状 [data/schema.py](../../stocktools/data/schema.py) `ai_logs` 有 `UNIQUE(code,type,analysis_date)` + upsert，**同日重复分析互相覆盖**，与"多跑几次对比异同"的诉求冲突，且 TUI 的"近 3 次"无从体现。

**改为追加**：
- 去掉 `UNIQUE(code,type,analysis_date)`，每次分析 **INSERT 一行**（按 `id` 自增 + `created_at` 排序）。
- 新增列：
  - `confidence` REAL —— 共识强度（如 `0.8` = 4/5）
  - `degraded` INTEGER NOT NULL DEFAULT 0 —— 终态低置信/解析降级标记
  - `votes` TEXT —— 5 路原始输出的 JSON（可观测性，便于事后区分"采样翻转"还是"解析失败"）
- [ai_logs_repo.py](../../stocktools/data/repos/ai_logs_repo.py)：`upsert` 改为 `insert`（不再 ON CONFLICT）；`get_recent` 不变，TUI"近 3 次"即显示真实的最近 3 次运行。

**迁移注意**：`CREATE TABLE IF NOT EXISTS` 无法删除已存在表的约束。老用户的 `ai_logs` 需**一次性重建迁移**（建新表 → 拷数据 → 删旧表 → 改名 → 重建索引），在 schema 初始化时检测旧结构并执行。

---

## 6. Prompt 调整

- **watch 去掉 `pattern` 字段**：watchlist 存的 `pattern` 来自 scanner，会把模型锚向看多，违背 §2"不喂 scanner 看多信号"，从 prompt 移除。
- **不加决策准则**（保发散性）。
- 输出指令改为"只输出符合 schema 的 JSON"，配合 §4.2 的 `response_format` 与校验。
- analysis 仍要求"先分析后给结论"的顺序。

---

## 7. CLI / TUI 入口统一

**现状（已核实，分析逻辑已单源）**：
- CLI [cmd_watch.py:15](../../stocktools/cli/cmd_watch.py) → `WatchService.analyze`，print 返回值。
- TUI [app.py:293](../../stocktools/tui/app.py) `_do_watch` → `asyncio.to_thread(WatchService.analyze)`（已后台跑，不卡 UI）；展示读 `ai_logs`（[watchlist.py:56](../../stocktools/tui/screens/watchlist.py) `get_recent(...,3)`）。
- alert 同构（`_hd_alert` / `_hd_alert_all`）。

**Ensemble 变慢（单股最坏 ~18 次 LLM 调用）后需补齐**：
1. **进度回调**：`analyze(..., on_progress=None)` 在 Service 层贯穿，报告"当前股票 / 第几轮 / 第几路完成 / 仲裁中"。
   - CLI：接到 print 或 tqdm。
   - TUI：接到状态栏（worker 内经 `call_from_thread` 更新），不再"点了 w 之后无反馈干等"。
2. **展示一致性**：Service 必须把结果落库，CLI 与 TUI 才看到同一份内容；CLI 也可改为落库后回读，保证两端口径一致。
3. **统一约束**：任何相同功能（买入分析 / 持仓分析）只允许经由对应 Service 方法，CLI 与 TUI 不得各自实现分析逻辑。

---

## 8. 成本与并发

- 单股最坏 `5 路 × 3 轮 + 仲裁 ≈ 16~18` 次调用。
- **内层 5 路用线程并发**（LLM 调用 IO 密集，不用数据层那种多进程），设并发上限。
- `st watch`（不带 code）/ `st alert all` 会按关注/持仓数 **N 倍放大**：外层串行或小并发，避免连接数/限流爆炸；进度回调贯穿到每只。

---

## 9. 任务拆解

| # | 任务 | 文件 |
|---|------|------|
| 1 | `invoke` 增 `response_format`；保持非零温度，去 temp/seed 确定性依赖 | `ai/client.py` |
| 2 | 特征预计算（MA/斜率/距均线/收益/波动，纯算、不碰 scanner） | `ai/features.py`（新） |
| 3 | 单路分析器：JSON schema + 校验 + 1 次重试 + degraded（watch & alert） | `ai/watch_analyst.py`、`ai/alert_analyst.py` |
| 4 | Ensemble 编排：5 路并发 + 代码统计共识 + ≤3 轮重跑 + 仲裁合成（watch 分类 / alert 中位数） | `ai/ensemble.py`（新） |
| 5 | watch 去掉 `pattern` 字段 | `ai/watch_analyst.py`、`services/watch_service.py` |
| 6 | `ai_logs` 改追加（去 UNIQUE + 新增 `confidence`/`degraded`/`votes`）+ 一次性重建迁移 | `data/schema.py`、`data/repos/ai_logs_repo.py` |
| 7 | `on_progress` 回调贯穿 Service → CLI(print/tqdm) + TUI(状态栏) | `services/watch_service.py`、`alert_service.py`、`cli/cmd_watch.py`、`cmd_alert.py`、`tui/app.py` |
| 8 | 单测：共识统计 / 重跑终态 / 数值中位数与离散度 / 解析降级 / 补票 | `tests/test_ai.py`（新） |

---

## 10. 已知取舍

- **共识用严格同标签**，可能在真·均衡的票上耗满 3 轮 → 终态返回多数票 + 低置信标记（诚实优于假装确定）。分桶共识留作后续可调项。
- **不追求逐 token 可复现**：ensemble 的价值正来自 5 路差异；稳定性体现在"决策相近"而非"字句相同"。
- **成本换稳定**：单股调用量上升约一个量级，靠并发与进度反馈缓解；`analyze all` 场景需注意限流。
