# StockTools

StockTools（命令行名：`st`）是一个面向 A 股中长线投资者的终端工具。它把日常研究拆成几个简单动作：更新行情、扫描形态、加入关注池、登记持仓、让 AI 辅助判断买入/卖出时机。

第一版以 CLI 指令为主；TUI 是后续的全屏终端界面入口，设计上通过直接输入 `st` 进入。

## 产品理念

StockTools 的目标不是替代交易系统，也不是做高频盯盘工具，而是帮助中长线投资者每天用较短时间完成一套稳定流程。

- 只做中长线：关注周期以数周到数月为主。
- 只做多：不覆盖做空、套利、日内交易等场景。
- 每天 10 分钟：用本地数据扫描和结构化记录减少重复劳动。
- 只看确定性较高的形态：低位箱体整理、上升通道、爆量吸筹、独立行情。
- CLI 优先：所有关键能力先用命令行跑通，TUI 只是对同一套 service 的可视化封装。

典型工作流：

```bash
st update
st find box
st record add 600519 -m "低位箱体，继续观察"
st watch 600519
st hold in 600519 --price 100 --stop 92 --target 125
st alert 600519
```

## 安装与初始化

### 1. 安装依赖

项目依赖 Python 3.11+。先在项目目录安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

核心依赖包括：

- `akshare`：每日全市场快照
- `baostock`：初始化历史日 K
- `openai`：OpenAI 兼容模型调用
- `pandas` / `numpy`：数据处理和形态扫描
- `textual`：TUI 依赖，当前第一版 CLI 优先

### 2. 运行 setup.sh

在项目根目录执行：

```bash
bash setup.sh
```

`setup.sh` 会做这些事情：

- 选择或创建工作目录，默认 `~/.stock_tools`
- 写入 `~/.stock_tools_path`，供后续 `st` 定位工作目录
- 初始化主数据库 `<workdir>/database.db`
- 初始化模型配置数据库 `<workdir>/config.db`
- 把 `st` 函数写入 `~/.zshrc` 或 `~/.bashrc`
- 引导写入模型配置
- 引导配置每日自动 `st update` 的 cron，默认 15:05

setup 完成后，重新打开终端，或执行脚本提示的：

```bash
source ~/.zshrc
```

如果你使用 bash，则 source 对应的 `~/.bashrc`。

### 3. 初始化历史行情

`setup.sh` 只负责本机环境和数据库结构，不抓行情。第一次使用前需要执行：

```bash
st init
```

`st init` 会通过 baostock 拉取全 A 过去约 1 年的前复权日 K 数据，写入 `<workdir>/database.db`。这个过程可能比较慢，首次约几十分钟；个别股票拉取失败会跳过，不阻断整体初始化。

初始化完成后，日常只需要：

```bash
st update
```

`st update` 会通过 akshare 拉取当日全市场快照并追加入库。

## 工作目录与数据库

工作目录发现顺序：

1. `STOCKTOOLS_HOME` 环境变量
2. `~/.stock_tools_path`
3. 默认 `~/.stock_tools`

工作目录内包含：

- `database.db`：行情、关注池、持仓、AI 分析日志
- `config.db`：模型配置

主行情字段统一为：

```text
code, name, date, open, close, high, low, volume
```

股票代码统一使用纯 6 位数字，例如 `000001`、`600519`。

## CLI 指令

所有命令都支持 `--help`：

```bash
st --help
st find --help
st hold in --help
```

### TUI 入口

TUI 是 CLI 的全屏终端封装，设计入口如下：

```bash
st
```

也就是直接输入 `st`、不带任何子命令，进入 TUI。

当前第一版以 CLI 指令为主；TUI 的页面、快捷键和交互设计见 `docs/TUI.md`。如果当前代码版本尚未接入 TUI，直接使用下面的 CLI 子命令完成同样工作流。

### 数据管理

#### `st init`

初始化历史行情数据。

```bash
st init
```

说明：

- 从 baostock 拉取全 A 过去约 1 年日 K
- 使用前复权口径
- 写入 `<workdir>/database.db`
- 只需要执行一次

#### `st update`

更新当日行情。

```bash
st update
```

说明：

- 从 akshare 拉取当日全市场快照
- 收盘后拉取的快照视为正式日 K
- 写入本地 SQLite

#### `st cron set <hh> <mm>`

设置每日自动执行 `st update` 的 cron 时间。

```bash
st cron set 15 05
```

说明：

- 使用 24 小时制
- 上例表示每天 15:05 自动执行 `st update`
- 只管理 StockTools 自己的 cron 标记块

#### `st cron remove`

移除 StockTools 自动更新 cron。

```bash
st cron remove
```

说明：

- 只移除由 StockTools 标记块管理的 cron 项
- 不影响用户自己的其它 cron

### 模型配置

#### `st config model set`

写入或覆盖当前模型配置。

```bash
st config model set \
  --base-url https://api.deepseek.com \
  --api-key sk-xxx \
  --model-name deepseek-chat
```

说明：

- 配置写入 `<workdir>/config.db`
- 使用 OpenAI 兼容接口
- `watch` 和 `alert` 会读取这组配置调用模型
- 第一版只支持这一种模型配置写入语法

#### `st config model show`

查看当前模型配置。

```bash
st config model show
```

说明：

- 显示 `base_url` 和 `model_name`
- `api_key` 会脱敏显示，不输出原文

### 选股扫描

扫描命令统一从本地 SQLite 读取日 K，不发起网络请求。

```bash
st find <scanner>
```

支持的扫描器：

| 命令 | 说明 |
|---|---|
| `st find box` | 低位箱体整理 |
| `st find channel` | 上升通道 |
| `st find ma_alignment` | MA均线多头排列 |

导出 CSV：

```bash
st find box --csv results/box.csv
```

说明：

- 只有显式传入 `--csv <path>` 才会导出
- 输出展示符合条件的股票及关键指标
- 不按得分排序
- 每个扫描器只判断“符合”或“不符合”

常用阈值参数可通过 CLI 覆盖，例如：

```bash
st find box --height-min 0.06 --height-max 0.45 --position-min 0.45
st find channel --width-min 0.08 --width-max 0.35 --r-squared-min 0.75
```

可用参数以命令帮助为准：

```bash
st find --help
```

### 关注池

关注池用于记录“还没买，但值得继续观察”的股票。

#### `st record add <code>`

加入关注池。

```bash
st record add 600519
```

带备注：

```bash
st record add 600519 -m "低位箱体，等确认突破"
```

说明：

- 自动读取本地行情中的股票名称
- 自动运行所有扫描器，把符合的形态写入 `pattern`

#### `st record show <code>`

查看关注池中某只股票。

```bash
st record show 600519
```

#### `st record note <code> <message>`

追加备注。

```bash
st record note 600519 "今天缩量回踩，继续观察"
```

覆盖备注：

```bash
st record note 600519 "新的备注内容" --replace
```

#### `st record go <code>`

标记“明天买”。

```bash
st record go 600519
```

#### `st record list`

查看关注池全部股票。

```bash
st record list
```

#### `st record rm <code>`

从关注池移除。

```bash
st record rm 600519
```

### 买入提醒

#### `st watch`

对关注池中所有股票执行买入时机分析。

```bash
st watch
```

#### `st watch <code>`

对指定股票执行买入时机分析。

```bash
st watch 600519
```

说明：

- 读取关注池、形态字段和本地最新行情
- 调用 OpenAI 兼容模型
- 输出一句话结论和简短理由
- 同一只股票同一天重复运行会覆盖当天旧的 watch 分析记录

### 持仓管理

#### `st hold in <code> --price <price>`

登记买入。

```bash
st hold in 600519 --price 100
```

可选止损、目标价和备注：

```bash
st hold in 600519 --price 100 --stop 92 --target 125 --note "箱体突破买入"
```

说明：

- 买入日期默认当天
- 同一股票允许多笔 open 持仓

#### `st hold out <code> --price <price>`

登记卖出并关闭该股票全部 open 持仓。

```bash
st hold out 600519 --price 120
```

#### `st hold out <code> --price <price> --dec`

登记减仓。

```bash
st hold out 600519 --price 115 --dec
```

说明：

- 第一版不记录减仓数量
- 不关闭 open 持仓
- 只在持仓备注中记录一次减仓操作

#### `st hold set <code>`

更新止损价、目标价或备注。

```bash
st hold set 600519 --stop 95
st hold set 600519 --target 130
st hold set 600519 --note "上移止损"
```

也可以一次传多个字段：

```bash
st hold set 600519 --stop 95 --target 130 --note "趋势保持"
```

#### `st hold show <code>`

查看指定股票当前 open 持仓。

```bash
st hold show 600519
```

#### `st hold list`

查看当前全部 open 持仓。

```bash
st hold list
```

#### `st hold history`

查看历史 closed 持仓。

```bash
st hold history
```

查看最近 N 条：

```bash
st hold history --near 10
```

导出 CSV：

```bash
st hold history --csv results/hold-history.csv
```

### 卖出提醒

#### `st alert`

对当前所有持仓执行卖出分析。

```bash
st alert
```

#### `st alert <code>`

对指定持仓执行卖出分析。

```bash
st alert 600519
```

说明：

- 读取当前 open 持仓和本地最新行情
- 对比止损/止盈线
- 调用 OpenAI 兼容模型
- 输出持有/注意/建议卖出等结论和理由
- 如果 AI 返回可写入的止损价或目标价，命令会询问是否写入数据库

## 日常使用建议

第一次使用：

```bash
python3 -m pip install -r requirements.txt
bash setup.sh
source ~/.zshrc
st init
```

每天收盘后：

```bash
st update
st find box
st find channel
st find ma_alignment
```

看到值得观察的股票：

```bash
st record add 600519 -m "形态不错，等回踩确认"
st watch 600519
```

买入后：

```bash
st hold in 600519 --price 100 --stop 92 --target 125
st alert 600519
```

复盘：

```bash
st record list
st hold list
st hold history --near 20
```

## 注意事项

- `setup.sh` 不抓行情，行情初始化请单独运行 `st init`。
- `st init` 需要网络访问 baostock，首次执行可能较慢。
- `st update` 需要网络访问 akshare。
- `st watch` 和 `st alert` 需要先配置 OpenAI 兼容模型。
- 扫描只使用本地 SQLite 数据，不会实时联网。
- 本项目面向个人研究和记录，不计算盈亏百分比。
