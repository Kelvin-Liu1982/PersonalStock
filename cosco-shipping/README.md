# 中远海控 · 主营与业绩追踪看板（方向C + 趋势增强）

一个面向 **中远海控（601919.SH / 01919.HK）** 的单文件 HTML 追踪看板：把集装箱航运主业、港口码头、财报、供给、成本、宏观与政策等关键维度，以模块化卡片 + 长期趋势对比的方式集中呈现，便于日常跟踪公司经营节奏与景气变化。

- **交付物**：`cosco-dashboard.html` —— 单文件、自包含（数据与时序图已 base64 内嵌，无外部 CDN 依赖），双击即可在浏览器打开。
- **风格**：浅色卡片网格 + 状态 chip + 迷你趋势(sparkline)；点「趋势」看完整长期图；底部「长期趋势专区」集中对比。
- **视觉约定**：红 = 上行(涨) / 绿 = 下行(跌)（A 股惯例）。

---

## 目录结构

```
cosco-shipping/
├── cosco-dashboard.html          # 最终交付物（单文件，双击即开）
├── public/index.html             # 同内容部署副本（Cloudflare 静态托管入口）
├── 数据源/                        # 看板读取的全部数据源（已提交）
│   ├── 中远海控_行业供需与运价数据.xlsx   # 运价/吞吐/出口/运力/停航率 + Alphaliner 两表
│   ├── 中远海控_货运量与航线结构数据.xlsx # 季度货运量、分航线箱量与收入
│   ├── 中远海控_财报核心数据.xlsx         # 年度+季度财务、成本结构、港口、分红
│   ├── 中远海控_回购明细.xlsx
│   ├── 中远海控_宏观与政策环境数据.xlsx   # PMI/燃油/租船/ETS/绕航等宏观近似指标
│   ├── 运价指数_周度_2021-2025.csv       # SCFI/CCFI/θ 长历史（θ 5–95% 分位带数据源）
│   └── ha_premium_601919.csv     # H/A 溢价率日频快照（common/ha_premium.py 产出）
├── build_tracker.py              # 读取 数据源/ → 生成时序数据 + 趋势图(base64) → 写 _data_js.txt
├── render_html.py                # 读取 _data_js.txt → 合成 HTML
├── build.py                      # 一键编排（数据源生成 + 看板构建）
├── build_financials.py           # [可选] 重建 财报核心数据.xlsx（联网抓取；东财缓存按需重新生成，不入库）
├── build_buyback.py              # [可选] 重建 回购明细.xlsx（内置已核对数据）
├── alphaliner_sync.py            # Alphaliner TOP100 抓取 → 写入两张 Alphaliner 表
├── alphaliner_server.py          # 本地服务（127.0.0.1），供看板卡片4「同步」按钮调用
├── fix_alphaliner_sheet.py       # 一次性：创建「供给端-Alphaliner周报(摘要)」表
├── fix_export_cols.py            # 幂等：按海关总署口径修正出口四列
├── direction-approved.md         # 方向确认单（设计方向与设计原则）
├── requirements.txt              # Python 依赖
└── .gitignore
```

> 注：`_data_js.txt` 为构建中间产物（每次构建重新生成），已在 `.gitignore` 中忽略，不入库。

---

## 快速开始

1. 直接用浏览器打开 `cosco-dashboard.html` 即可，无需任何安装或联网。
2. 顶部为当日行情快照（A 股 / H 股）；每张卡片 = 最新快照 + 迷你趋势；点「趋势」按钮查看完整长期图。

---

## 重新构建（修改数据后）

### 依赖

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt   # openpyxl, matplotlib
```

### 仅用已提交的 数据源/ 重生成看板（离线、最常用）

```bash
python build_tracker.py
python render_html.py
```

> `render_html.py` 会把 `数据源/ha_premium_601919.csv` 转成 `<script id="haPremiumData">` 内嵌进 HTML，
> 由 `common/ha-premium.js` 渲染顶部卡片里的「H/A 溢价率 · 日频」图（跟随「刷新行情」更新末点）。
> 需要推进这条曲线时，先在**上级目录**重跑一次快照（腾讯日线 + 港币汇率，未复权口径）：
>
> ```bash
> python ../common/ha_premium.py --a sh601919 --h hk01919 --bars 400 \
>   --csv 数据源/ha_premium_601919.csv
> python render_html.py
> ```
>
> 快照缺失时看板会自动隐藏该图，不影响其它内容。

### 一键全流程（含原始数据制备）

```bash
python build.py
```

`build.py` 会依次执行：`build_financials.py` → `build_buyback.py` → `build_tracker.py` → `render_html.py`。
其中 `build_financials.py` 会尝试联网抓取东方财富业绩报表，抓取结果会写入本地缓存 `财报原始数据_缓存.json`（按需生成、不入库）；该文件缺失时脚本会重新联网抓取。

---

## Alphaliner 一键同步（卡片 4 右上角按钮）

卡片「4 行业供需格局」右上角的 **同步** 按钮，会从
[Alphaliner PublicTop100](https://alphaliner.axsmarine.com/PublicTop100/) 抓取最新数据并写入
`数据源/中远海控_行业供需与运价数据.xlsx` 的两个 sheet：

| sheet | 内容 | 对应官网位置 |
|---|---|---|
| `Alphaliner-全球运力` | 在运营船舶/运力/DWT、fully cellular 拆分、区域周运力 | 页面顶部 Global figures |
| `Alphaliner-中远海控` | COSCO Group 那一行：总运力/艘数、自有、租入、手持订单及占比 | Top100 表格第 4 行 |

**使用前先在本机启动服务**（浏览器无法直接写本地 Excel，故用本地服务落盘）：

```bash
.venv/bin/python alphaliner_server.py      # 默认 http://127.0.0.1:8765
```

- 首列是 **发布时间**（Alphaliner 页头所显示的数据时点，YYYY-MM-DD）；同一天只保留一行
- 截图/月报等非接口来源可手动补录（自动按日期插入排序）：
  ```bash
  .venv/bin/python alphaliner_sync.py --add-date 2026-10-02 \
    --ships 7652 --teu 34819109 --dwt 414135576 \
    --fc-ships 6850 --fc-teu 34410401 \
    --ta 158203 --tp 606497 --eu 569388
  ```
- 也可不开浏览器，直接命令行同步：`.venv/bin/python alphaliner_sync.py`
- 数据源是 Ext.Direct 接口 `rooter.php` 的 `top100.getTop100Table` / `getTextCalculations`，纯 HTTP 即可，无需登录
- 线上（Cloudflare）打开的看板同样可以调用本机服务；若服务未启动，按钮会提示「未连接本地服务」

## 数据源说明

| 文件 | 用途 |
|---|---|
| 中远海控_行业供需与运价数据.xlsx | 运价(SCFI/CCFI 各航线)、港口吞吐量、出口总额、运力/闲置率、停航率、成本与宏观指标等 |
| 中远海控_货运量与航线结构数据.xlsx | 分航线箱量与收入占比、季度航运货运量明细等 |
| 中远海控_财报核心数据.xlsx | 营收/归母净利/毛利率/ROE（年度+季度）、成本结构、港口码头业务、分红 |
| 中远海控_回购明细.xlsx | 2026 年 A 股 / H 股回购明细 |
| 中远海控_宏观与政策环境数据.xlsx | PMI、燃油价、租船费率、EU ETS、红海绕航比例等宏观近似指标 |
| 运价指数_周度_2021-2025.csv | SCFI/CCFI 周度长历史及 SCFI/CCFI 即期溢价倍数（θ），供分位带计算 |

> 宏观与政策类指标（PMI、燃油价、租船费率、EU ETS 碳价、红海绕航比例等）为公开数据近似，非公司披露口径，看板内已标注。

---

## 免责声明

本看板为个人研究/学习用途，数据来自公开数据库与公司公告的交叉核对，可能存在误差或时滞，**不构成任何投资建议**。请以公司正式公告与交易所披露为准。
