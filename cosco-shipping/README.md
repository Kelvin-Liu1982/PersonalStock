# 中远海控 · 主营与业绩追踪看板（方向C + 趋势增强）

一个面向 **中远海控（601919.SH / 01919.HK）** 的单文件 HTML 追踪看板：把集装箱航运主业、港口码头、财报、供给、成本、宏观与政策等关键维度，以模块化卡片 + 长期趋势对比的方式集中呈现，便于日常跟踪公司经营节奏与景气变化。

- **交付物**：`output/cosco-dashboard.html` —— 单文件、自包含（数据与时序图已 base64 内嵌，无外部 CDN 依赖），双击即可在浏览器打开。
- **风格**：浅色卡片网格 + 状态 chip + 迷你趋势(sparkline)；点「趋势」看完整长期图；底部「长期趋势专区」集中对比。
- **视觉约定**：红 = 上行(涨) / 绿 = 下行(跌)（A 股惯例）。

---

## 目录结构

```
cosco-shipping/
├── output/                       # 所有生成的 HTML 与构建中间产物
│   ├── cosco-dashboard.html      # 主看板（单文件，双击即开）
│   ├── drewry-weekly.html        # 周报页：Drewry WCI / IACI / CST / RST
│   ├── alphaliner-weekly.html    # 周报页：Alphaliner 全球船队 / 中远海控
│   ├── sse-weekly.html           # 周报页：SCFI / CCFI 综合 + SCFI 分线（两大板块）
│   └── _data_js.txt              # build_tracker → render_html 的中间产物（gitignore）
├── src/                          # 全部 Python 代码
│   ├── build_tracker.py          # 读 数据源/ → 时序数据 + 趋势图 → 写 output/_data_js.txt
│   ├── render_html.py            # 读 _data_js.txt → 合成主看板（单份输出）
│   ├── build.py                  # 一键编排（依次调用 src/ 下四个脚本）
│   ├── build_financials.py       # [可选] 重建 财报核心数据.xlsx（联网，东财缓存不入库）
│   ├── build_buyback.py          # [可选] 重建 回购明细.xlsx
│   ├── build_weekly_pages.py     # 生成三张周报页（--only 单独重建）
│   ├── build_volume_price.py     # [已废弃] 旧量价页生成器
│   ├── alphaliner_sync.py        # Alphaliner TOP100 抓取 / --verify 只读校验
│   ├── alphaliner_server.py      # 本地服务（127.0.0.1:8765），「同步」按钮后端
│   ├── drewry_ingest.py          # Drewry JSON → xlsx 落库
│   ├── redsea_digitize.py        # 红海绕航截图数字化
│   ├── fix_alphaliner_sheet.py   # 一次性：创建「供给端-Alphaliner周报(摘要)」表
│   └── fix_export_cols.py        # 幂等：按海关总署口径修正出口四列
├── 数据源/                        # 看板读取的全部数据源（已提交）
│   ├── 中远海控_行业供需与运价数据.xlsx   # 吞吐/出口/运力/停航率（Drewry、Alphaliner、SSE 均已拆出）
│   ├── 中远海控_Drewry周报数据.xlsx       # WCI/IACI/CST/RST 四表 + 分析要点
│   ├── 中远海控_Alphaliner周报数据.xlsx   # 全球 / COSCO 两表 + 分析要点
│   ├── 中远海控_SSE周报数据.xlsx          # SCFI&CCFI 综合 + SCFI 分线（当年）
│   ├── 中远海控_货运量与航线结构数据.xlsx # 季度货运量、分航线箱量与收入
│   ├── 中远海控_财报核心数据.xlsx         # 年度+季度财务（含营业利润）、成本结构、港口、分红
│   ├── 中远海控_回购明细.xlsx
│   ├── 中远海控_宏观与政策环境数据.xlsx   # PMI/燃油/租船/ETS/绕航等宏观近似指标
│   ├── 运价指数_周度_2021-2025.csv       # SCFI/CCFI/θ 长历史（θ 5–95% 分位带数据源）
│   └── ha_premium_601919.csv     # H/A 溢价率日频快照（common/ha_premium.py 产出）
├── direction-approved.md         # 方向确认单（设计方向与设计原则）
├── requirements.txt              # Python 依赖
└── README.md
```

> 注：`output/_data_js.txt` 为构建中间产物，已在 `.gitignore` 中忽略，不入库。
>
> **路径约定**：所有脚本用 `__file__` 推导 `ROOT`（=`src/` 的上一级），`数据源/`、`output/`
> 都相对 `ROOT` 解析，因此与当前工作目录无关；命令一律从项目根执行 `.venv/bin/python src/<脚本>.py`。
> `build_tracker.py` 额外用 `ROOT` 的上一级作为工作区根，以导入公共库 `common/svg_charts`。
>
> **线上路径变更**：页面 URL 由 `/cosco-shipping/<页>.html` 变为 `/cosco-shipping/output/<页>.html`；
> 上级 `index.html` 的「追踪看板」入口已同步。主看板只在 `output/` 保留一份，`public/` 冗余副本与 `render_html.py` 双输出逻辑已于 2026-11-14 清理。

---

## 快速开始

1. 直接用浏览器打开 `output/cosco-dashboard.html` 即可，无需任何安装或联网。
2. 顶部为当日行情快照（A 股 / H 股）；每张卡片 = 最新快照 + 迷你趋势；点「趋势」按钮查看完整长期图。

---

## 分层：主看板给结论，周报页给明细

三个独立周报页（`drewry-weekly` / `alphaliner-weekly` / `sse-weekly`）上线后，主看板不再复制周度明细，
只保留「结论层 + 跳转」，避免同一数据出现两个分辨率、两套写法：

| 层 | 位置 | 职责 |
|---|---|---|
| 结论层 | 主看板卡片 | 每卡 3–6 个指标行，只放判断用的锚点数字 |
| 明细层 | 三个周报页 | 全序列、分航线、周环比、官方要点、逐期对照表 |
| 时效层 | 主看板顶部「周度脉搏」条 | 四个数据源各自的数据截止日 + 关键数 + 跳转 |

对应的调整（2026-11-14）：

- **卡 4 行业供需格局已删除**：该卡三个指标（全球船队运力 / WCI 综合 / 停航率）与顶部「周度脉搏」条及 Drewry / Alphaliner 周报页**完全重复**（数字同源同函数），且入口三重复读。
  判断其作为「数据卡」意义消失，故从主看板卡片区与「长期趋势专区 4」整块删除，对应 `supply_fleet` / `supply_order` / `supply_idle` / `control_us` / `control_eu` 五张图一并从 `build_tracker.py` 移除。
  供给维度在卡面已无指标，仅顶部脉搏条 RST 行保留「苏伊士/好望角艘数 + 亚欧经苏伊士比例」。
- **卡 5 宏观与政策环境**（原卡 6）：「红海通航（苏伊士/好望角）」与「苏伊士通行占比」两项周度实测，于 2026-11-14 从卡面与趋势专区第5块**撤回**（Drewry 周报页「红海绕航」块已完整承载，且入口重复）。
  卡 5 现仅 4 行：VLSFO 燃油价 / 租船费率 Harpex / EU ETS 碳价 / 欧美 PMI；对应 `macro_redsea_mix` / `macro_redsea_share` 两张图从 `build_tracker.py` 移除（亚欧经苏伊士比例 `macro_redsea_ae` 仍供脉搏条）。
  「亚欧绕航好望角比例」「运力吸收率」两项**年度估算**（只到 2025，2026 全空）曾先于周度值，现已整体退出卡面。
- **卡 1 集装箱航运主业**：从「指标罗列」改为**单箱经济模型**，只放公司自身指标，**四行**：
  单季货运量 → 单箱收入（USD/TEU）→ 单箱EBIT（USD/TEU）→ 航线结构占比。
  SCFI / CCFI / θ、五航线即期运价、舱位利用率、货运量分航线**全部撤出卡面**，
  对应图表也一并从主看板移除（详见 sse-weekly.html），主看板不再重复运价指数类明细。

> **长期趋势专区「1 集装箱航运主业」同步精简为 4 张图**：季度货运量、单箱收入（季）、单箱EBIT（季）、
> 航线结构占比（跨两列）。原 SCFI / CCFI / θ / 五航线即期运价 / 舱位利用率 共 9 张图已从 `build_tracker.py`
> 的 `CHARTS` 与 `FREQ` 中删除，HTML 体积由 426 KB 降至 365 KB（`_data_js.txt` 由 376 KB 降至 316 KB）。

> 卡内注解不再写死周度数值（原先手写的「SCFI −1.5% 至 3,633.45 / θ 1.96→1.89」会与周报页自动文案漂移），
> 只保留传导逻辑与判断口径，具体数字由「周度脉搏」条和各指标行从 xlsx 实时注入。

### 单箱EBIT 口径（2026-11-14 新增）

`单箱EBIT = 单季营业利润 ÷ 单季货运量 ÷ 7.1`

- 营业利润取自 `中远海控_财报核心数据.xlsx` 的 **`季度核心数据` 新增两列**（`营业利润累计(亿元)` / `营业利润(亿元)`），
  源头是东方财富 `RPT_DMSK_FN_INCOME` 的 `OPERATE_PROFIT`，单季由「当季累计 − 上季累计」还原；
- **分子是合并营业利润**，含码头分部利润（年约 30 亿元 ≈ 16 美元/TEU），故单箱EBIT 绝对水平略高于航运分部 EBIT，
  **趋势可用**；季报无分部拆分，如需精确到航运分部须用年报「分部报告」，年度口径可修正；
- 汇率统一按 **7.1** 折算（与成本表 `×7.1` 口径一致），2021–2022 年人民币较强，该两年美元口径略偏低。

---

## 重新构建（修改数据后）

### 依赖

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt   # openpyxl, matplotlib
```

### 仅用已提交的 数据源/ 重生成看板（离线、最常用）

```bash
python src/build_tracker.py
python src/render_html.py
```

> `render_html.py` 会把 `数据源/ha_premium_601919.csv` 转成 `<script id="haPremiumData">` 内嵌进 HTML，
> 由 `common/ha-premium.js` 渲染顶部卡片里的「H/A 溢价率 · 日频」图（跟随「刷新行情」更新末点）。
> 需要推进这条曲线时，先在**上级目录**重跑一次快照（腾讯日线 + 港币汇率，未复权口径）：
>
> ```bash
> python ../common/ha_premium.py --a sh601919 --h hk01919 --bars 400 \
>   --csv 数据源/ha_premium_601919.csv
> python src/render_html.py
> ```
>
> 快照缺失时看板会自动隐藏该图，不影响其它内容。

### 一键全流程（含原始数据制备）

```bash
python src/build.py
```

`build.py` 会依次执行：`build_financials.py` → `build_buyback.py` → `build_tracker.py` → `render_html.py`。
其中 `build_financials.py` 会尝试联网抓取东方财富业绩报表，抓取结果会写入本地缓存 `财报原始数据_缓存.json`（按需生成、不入库）；该文件缺失时脚本会重新联网抓取。

---

## Alphaliner 周报（alphaliner-weekly.html）

数据在独立文件 **`数据源/中远海控_Alphaliner周报数据.xlsx`**（2026-11-13 从
`中远海控_行业供需与运价数据.xlsx` 拆出），两张数据表 + 一张分析表：

| sheet | 列 | 内容 |
|---|---|---|
| `全球` | 9 | 在运营船舶/运力/DWT、fully cellular 拆分、三大干线周运力（32 期） |
| `COSCO` | 14 | COSCO Group 一行：排名/份额/总运力/艘数/自有/租入/手持订单（32 期） |
| `分析要点` | 6 | 来源「全球」/「COSCO」各 5 条，随每期快照自动重算 |

页面上按来源分两块：**GLOBAL 全球船队 → COSCO 中远海控**。2026-11-24 起与 Drewry 页统一为
左侧垂直菜单 + 右侧全宽内容区（`.vlayout/.vside/.vmain`，三页共用）：侧栏两项来源 +
「同步 Alphaliner TOP100」按钮与状态 + 返回主看板，滚动自动高亮；两块纵向堆叠，
图表网格固定 2 列等宽，全宽图与 9 期快照表占满行。`id="global"` / `id="cosco"` 保留供深链。
两块底部 `.note` 口径说明已删除（与「本期要点」重复），两张快照表由 8 期扩为 **9 期**。
Alphaliner 官网**只给数字、没有任何文字洞察**，所以这一页的分析全部由本表数据生成：
每张图下的 `.ann` 与块顶的「本期要点」都是脚本按当期数据算的（`al_points_global()` /
`al_points_cosco()`），不依赖人工撰写；同一份要点也会写进 `分析要点` 表，便于核对或手工改写
（改动后若数据截止日与最新一期一致，页面就采用表内版本）。

### 抓取节奏

官网每日更新，本页**定义为每周六取一次当日快照**作为该周数据（`发布时间` = 抓取当日）。

两条路径执行**同一条三步流水线**，结果一致；A 是「周六快照采集」自动化的手动兜底入口，
用于自动逻辑漏执行时补跑：

| 步 | 动作 | 共用实现 |
|---|---|---|
| ① | 抓 PublicTop100 → 写「全球」「COSCO」→ 重算「分析要点」 | `alphaliner_sync.sync()` |
| ② | **只**重建 `alphaliner-weekly.html` | `build_weekly_pages.main(["--only","alphaliner"])` |
| ③ | 三项校验（末行日期 / 两表行数相等 / 两组要点各 5 条且截止日一致） | `alphaliner_sync.verify()` |

```bash
# A. 页面顶部「同步 Alphaliner TOP100」按钮（需先启动本地服务，浏览器无法直接写 Excel）
.venv/bin/python src/alphaliner_server.py      # 默认 http://127.0.0.1:8765，/sync 一次跑完 ①②③
#    服务内用 threading.Lock 串行化 /sync；按阶段返回 render / checks / stages，
#    中途失败会带 partial.written 说明「数据已写入但后续阶段失败」

# B. 命令行（每周六自动化走这条）
.venv/bin/python src/alphaliner_sync.py                       # ①
.venv/bin/python src/build_weekly_pages.py --only alphaliner  # ②
#    ③ 两条链路共用同一个校验函数（只读，返回 checks / all_passed）
.venv/bin/python src/alphaliner_sync.py --verify
```

写入前会检测 `~$中远海控_Alphaliner周报数据.xlsx` 锁文件，存在即拒绝、不重试、不伪造新行。
`--only alphaliner` 是 ② 的**固定写法**：本时点只有 Alphaliner xlsx 变了，
`drewry-weekly.html` 与 `sse-weekly.html` 的数据未更新，不应被重渲染（也不做任何针对它们的抓取）。
不带参数会全量重建三页，仅在各数据源手工更新后使用；`--only drewry` / `--only sse` 同理各管一页。
按钮成功后本地页面（`file://` 或本机静态服务）会自动 reload 显示新图表；
**线上 Cloudflare 副本 reload 后仍是云端旧 HTML**，按钮会提示「本机数据与本地页面已更新，线上需推送后才生效」。

- 首列 **发布时间** = Alphaliner 页头的数据时点（YYYY-MM-DD），**同一天只保留一行**（重复抓取覆盖）
- 数据源是 Ext.Direct 接口 `rooter.php` 的 `top100.getTop100Table` / `getTextCalculations`，纯 HTTP，无需登录
- 截图/月报等非接口来源可手工补录：
  ```bash
  .venv/bin/python src/alphaliner_sync.py --add-date 2026-10-02 \
    --ships 7652 --teu 34819109 --dwt 414135576 \
    --fc-ships 6850 --fc-teu 34410401 \
    --ta 158203 --tp 606497 --eu 569388
  ```
- 线上（Cloudflare）打开的看板同样可以调用本机服务；服务未启动时按钮提示「未连接本地服务」

### 两个已知口径问题

1. **`全球份额(%)` 源表是 `#REF!` 断链**（32 行全部），本页一律按 *公司总运力 ÷ 全球运力* 重算，不读源表值；
   同步脚本写入时也直接算百分数落库。
2. **快照不定期**（间隔 4–28 天，中位 9 天），不是严格周度。x 轴按真实日期定位、不插值，
   **不要把它当等距周序列做差分**；页面表格也标注了「相邻行不可当作一周比较」。

---

## Drewry 周报（drewry-weekly.html）

**页面布局（2026-11-24 起三页统一）**：参照 Tabler「Fluid vertical layout」，三张周报页共用
`.vlayout/.vside/.vmain` 组件——左侧 212px 粘性菜单（Drewry 四项来源 / Alphaliner 两项+同步按钮 /
SSE 两项），右侧全宽内容区，滚动自动高亮当前块；≤1100px 菜单回落为静态，≤700px 图表网格单列。
各来源块纵向堆叠，块内 `.vmain .chart-grid` 固定 2 列等宽；全宽图与表格用 `wide` 占满行。
页高 58px，故侧栏 `top:68px`、锚点 `scroll-margin-top:68px`。改动须落在脚本源头再重渲染，
勿直接改 HTML。「本期要点」沿用 `<details>` 默认折叠。
三页共用页尾脚本提供 **SVG 悬停读数**（2026-11-24）：鼠标在任意 `svg.cv` 上移动时，按 SVG 坐标
定位最近数据点，画黑色虚线竖线并在跟随浮层中列出该日期的所有序列值（折线取 `circle[data-s]`、
柱状取 `rect[data-s]`）；图例点击隐藏与双击放大不受影响。首次读取时 `<title>` 文本转存到
`data-tt` 并清空，避免浏览器原生 tooltip 与浮层重复；图标题移入 `aria-label`。

**顶层入口（2026-11-24）**：根目录 `index.html` 的 `.quicklinks` 新增第三张「航运周报」卡
（`--ind-shipping`），直接指向 `output/drewry-weekly.html`（默认周报）；曾建的 `weekly-hub.html`
聚合层已按用户要求移除，Alphaliner / SSE 页仍可由 Drewry 页顶部页签切换进入。
主看板 `render_html.py` 模板中的顶部 `wk-nav` 三个周报按钮已移除（脉搏条中的带数据入口保留）。

数据已独立成文件 **`数据源/中远海控_Drewry周报数据.xlsx`**（2026-11-13 从
`中远海控_行业供需与运价数据.xlsx` 拆出），一源一表：

| sheet | 来源 | 频率 | 内容 |
|---|---|---|---|
| `WCI` | [World Container Index](https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry) | 每周四 | 综合 + 周环比 + 4 条上海出口航线（47 期） |
| `IACI` | [Intra-Asia Container Index](https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/intra-asia-container-index) | 每周四 | 综合 + 周环比 + 8 条航线（25 期，自 2026-06-04） |
| `CST` | [Cancelled Sailings Tracker](https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/cancelled-sailings-tracker) | 每周五 | 覆盖周数 / 计划 / 停航 / 停航率 / 三干线结构 / 营运率（47 期） |
| `RST` | [Red Sea Diversion Tracker](https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/red-sea-diversion-tracker) | 每两周（周二） | 经苏伊士 / 经好望角 周度通航艘数 + 亚欧运力占比（59 周） |
| `分析要点` | 上述四源 | 随各期 | 官方原文提炼，键＝(数据截止, 来源) |

页面上四个来源各成一块，从上到下：**WCI → IACI → CST → RST**，由左侧垂直菜单导航。
三张数据表**各用自己的发布日**（WCI/IACI 周四、CST 周五），合并时按 **ISO 周**
（`date.isocalendar()`）对齐，不要求日期字符串相同；`read_drewry()` 在建页前会校验
两表周序一一对应、同日期间日期差 ≤3 天、IACI 是 WCI 的子集，任一条不满足直接报错。

### 三步流水线

```bash
# ① 数据 + 官方分析要点 → xlsx（先关掉 Excel，脚本会检测 ~$ 锁文件）
.venv/bin/python src/drewry_ingest.py 数据源/drewry_2026-11-13.json
# ② + ③ 图表与分析注解 → HTML（只重建 Drewry 页）
.venv/bin/python src/build_weekly_pages.py --only drewry
```

**step 0** 是读官网各期页面，把数字与要点整理进 `数据源/drewry_<日期>.json`
（`edition_date` / `wci` / `iaci` / `cst` / `rst` 五段，结构见该文件自身注释）。

### 单位约定（与拆分前的单表不同）

> **2026-11-23 更新**：录入 CST 20 Nov 版（W48–W52，724 计划 / 42 停航 / 6%，跨太 48% / 亚欧 33% /
> 跨大西洋 19%，94% 执行率）。因构建时强制 `set(WCI 周) == set(CST 周)`，同期补录 WCI 19 Nov 版
> （$4,176，-3%；RTM 3,496 / LAX 7,026 / GOA 4,436 / NYC 8,194）及其官方要点。
>
> **2026-11-23 IACI 补录**：19 Nov 期 IACI 综合 $1,444（+$4 / +0.28%），8 条航线同步写入。
> Nehru / Singapore / Busan 取官网正文（3141 / 2064 / 203），其余 5 条从官网 Canva 矢量图按
> Y 轴刻度线性拟合，并用 11-12 期已知值逐序列校准（统一下移 3.7 美元）。

`CST` 表的停航率 / 取消量占比 / 营运率按 **百分数** 存储（`7` 表示 7%），
旧单表是小数比例（`0.07`）。读取端在各自边界归一：
`build_tracker.py::_drewry_weekly()` 除 100 还原比例，`build_weekly_pages.py` 直接用百分数。

### 分析要点为什么落库到 xlsx

要点写在 sheet **`分析要点`**（A 数据截止｜B 来源｜C 标题｜D 要点｜E 序｜F 采集时间），
而不是直接写进 HTML —— 否则下次 `build_weekly_pages.py` 重跑就丢了。
`read_analysis()` 按「来源 + 最新数据截止」取用，同一组重复写入会先删后插（幂等）。

### 页面注解的两层结构

每张图下方 `.ann` = **① 自动生成句**（脚本按本表数据算，含本期值/周环比/年内极值/连续周数，
永远与图一致）＋ **② 官方原文提炼**（来自 xlsx 的要点卡）。分块顶部另有「本期要点」卡，
对应 IACMI 报告里的 Key signals 版式。

> **CST 日期口径**：CST 每周五发布，比 WCI/IACI（周四）**晚 1 天**，所以 CST 表按**自己的周五日期**记录
> （例如同一期 WCI 记 `2026-11-19`、CST 记 `2026-11-20`）。跨表合并按 ISO 周，两个日期都保留在记录里：
> `d` 为 WCI 侧（统一键）、`d_cst` 为 CST 侧，CST 块的三张图用 `d_cst` 成图。
> 停航率是「未来五周」的**前瞻**值，不是当周实际执行率。
>
> **RST 口径**：RST 块的三张图里，B/C 两列为官网 PNG 图表数字化所得（±3 艘/周），非官方数值；
> 「苏伊士通行占比」= 苏伊士 ÷（苏伊士＋好望角），按**艘数**，本期 25.6%；
> 官方「亚欧运力经苏伊士 60%」是**运力份额**口径，分母不同，**不可用前者反推后者**。
> 「两线合计」图是用来做稳定性校验的：合计应大致恒定，只有货量在两线间重新分配；
> 2026-01-04 一周合计仅 94 艘（前后周 143 / 226），疑节假日短周或数据缺报，勿读作航线切换。
> 详见该表表下「口径与来源说明」。

---

## SSE 周报（sse-weekly.html）

数据在独立文件 **`数据源/中远海控_SSE周报数据.xlsx`**（2026-11 从
`中远海控_行业供需与运价数据.xlsx` 拆出），两张 sheet：

| sheet | 列 | 覆盖 |
|---|---|---|
| `SCFI&CCFI` | 日期 / SCFI 综合 / SCFI 周环比 / CCFI 综合 / CCFI 周环比 / SCFI÷CCFI 即期溢价倍数 | 2021-01-08 起 **292 期** |
| `SCFI 分线` | 日期 / 欧洲 / 地中海 / 美西 / 美东 / 波斯湾 / 舱位利用率(定性) / 市场行情简评 | 仅当年，2026 年内 **45 期** |

页面两大块（`build_sse()`）：

| 块 | 内容 |
|---|---|
| ① SCFI·CCFI | SCFI 全序列（2021 起）+ CCFI + 即期溢价倍数 + 周环比柱状（近 104 期）+ 最近 9 期表 |
| ② SCFI 分线 | 5 条主干航线，按单位分「欧地 / 美线 / 波斯湾」三张图 + 6 张 KPI + 最近 9 期表 |

> 排版自 2026-11-24 起与其余两张周报页统一：左侧两项垂直菜单 + 右侧全宽内容区，两块纵向堆叠；
> 综合块四图与分线块三图+9期表均按 2 列等宽排布（分线表与波斯湾图并排）。
> `id="sseidx"` / `id="sseroute"` 保留供深链引用；本期要点沿用 `kps_block()` 的 `<details>` 默认折叠。

> 两块底部的 `.note` 口径说明已删除（与「本期要点」重复）；图卡内 `.ann` 数据注解保留。
> 「官方原文 / 近 10 期简评摘要」板块已移除（2026-11-14）；`SCFI 分线` 表的「市场行情简评」列仍保留在数据文件中，只是不再上页。

```bash
.venv/bin/python src/build_weekly_pages.py --only sse   # 只重建 SSE 页
.venv/bin/python src/build_tracker.py && .venv/bin/python src/render_html.py   # 主看板（含新增导航入口）
```

### 口径（务必按此）

- **SCFI 是即期、CCFI 是长协加权**，两者不可直接比大小；`SCFI÷CCFI` 即期溢价倍数 = 当期收入弹性。
- **CCFI 2021 年缺 19 期**（2021-05-07 ~ 2021-12-17 间无值）：绘图仍按 `CCFI_START = 2022-01-01` 过滤；页面文案已不再标注该起点。
- 周序列**非严格等距**：春节等长假造成 4–15 天间隔（中位 7 天），x 轴按真实日期定位，
  **不能对周环比取算术均值**。
- 分线单位并存：欧/地/波 = **USD/TEU**，美西/美东 = **USD/FEU**，故按单位分两组作图；
  分线只有当年，不与 WCI 四航线同图对照（Drewry 与 SSE 口径不同）。
- 周环比在源表里是**小数比例**（0.0051 = 0.51%），页面 `_pctp()` 与主看板 `pct()` 统一 ×100；
  两列的字段值已与相邻两期实际差分逐期核对，0 异常。
- 主看板 `build_tracker.py` 的 `fr` 宽表由 **`_sse_wide()`** 按日期内连接两张 sheet 得到（45 期），
  不再读已删除的 `周运价指数(SCFI&CCFI)`。
- **官方周报正文有时只给 SCFI 与分航线、不给 CCFI**（如 2026-11-20 期）：CCFI 取上海航交所
  同日发布的《航运指数丨YYYY.MM.DD》（由新浪财经等转载，署名「来源：上海航交所」），
  并在分线表「市场行情简评」列注明出处；禁止用上期 CCFI 代填。
  2026-11-20 期实测：SCFI 3503.78 / CCFI 1923.21（+0.2%），与上一期 3572.33 / 1919.27 差分吻合。

### 每期更新

1. 两张 sheet 末尾各加一行（同一发布日，均为周五；分线表可只更新 5 列与正文）；
   **不要用 openpyxl 直接保存整个工作簿**——它会抹掉全部公式缓存值，使 `data_only=True` 读到 `None`、
   即期溢价倍数整列断裂。做法：直接补 xlsx 内 `xl/worksheets/sheet1.xml` / `sheet2.xml` 的 `<row>`，
   同步改 `<dimension>`，公式单元格写 `<f>…</f><v>缓存值</v>`（必要时补 `xl/calcChain.xml`）。
2. 重跑 `src/build_weekly_pages.py --only sse`（只重建 SSE 页）+ `build_tracker.py` + `render_html.py`（主看板）；
   若要一次性重建三张周报页，才不带 `--only`。

---

## 数据源说明

| 文件 | 用途 |
|---|---|
| 中远海控_行业供需与运价数据.xlsx | 运价(SCFI/CCFI 各航线)、港口吞吐量、出口总额、运力/闲置率、停航率联盟结构、成本与宏观指标等（Drewry 相关表已于 2026-11-13 拆出） |
| 中远海控_Drewry周报数据.xlsx | **Drewry 四大免费追踪器**：`WCI` / `IACI` / `CST` / `RST` 四张数据表 + `分析要点` |
| 中远海控_Alphaliner周报数据.xlsx | **Alphaliner**：`全球` / `COSCO` 两张数据表 + `分析要点`（每周六取一次快照） |
| 中远海控_SSE周报数据.xlsx | **上海航交所**：`SCFI&CCFI`（综合指数，2021 起 290 期）+ `SCFI 分线`（五航线 + 舱位利用率定性 + 周报正文，仅当年） |
| 中远海控_货运量与航线结构数据.xlsx | 分航线箱量与收入占比、季度航运货运量明细等 |
| 中远海控_财报核心数据.xlsx | 营收/归母净利/毛利率/ROE/**营业利润**（年度+季度，营业利润由东财 OPERATE_PROFIT 补入，供单箱EBIT 使用）、成本结构、港口码头业务、分红 |
| 中远海控_回购明细.xlsx | 2026 年 A 股 / H 股回购明细 |
| 中远海控_宏观与政策环境数据.xlsx | PMI、燃油价、租船费率、EU ETS、红海绕航比例等宏观近似指标（**年度**值，2021–2025） |
| 运价指数_周度_2021-2025.csv | SCFI/CCFI 周度长历史及 SCFI/CCFI 即期溢价倍数（θ），供分位带计算 |
| WCI_分航线_周度_2025.csv | WCI 四条上海出口航线（鹿特丹/洛杉矶/热那亚/纽约，USD/FEU）**2025 年离线历史快照，不参与任何看板构建**；由雪球周度运价对照表三张截图转录（**52 期，25 年 W1–W53，2025-01-02 ~ 12-25**，日期按当周周四 WCI 发布日映射，7 天等距；环比自洽 196 条 + 跨截图衔接 8 条比对全通过），其末期与 `WCI` 表 `2026-01-01` 行四列数值完全一致（圣诞/新年周同值），**未来并表须去重** |

> **2026-11-14 清理说明**：迁移期的 4 个临时转录 CSV（`Drewry_停航率_2026.csv`、`IACI_分航线_周度_2026.csv`、`IACI_周度_2026.csv`、`WCI_分航线_周度_2026.csv`）已删除——数据均已完整落入 `中远海控_Drewry周报数据.xlsx` 的 `CST` / `IACI` / `WCI` 表（分别 46 / 24 / 46 期，覆盖各 CSV 的全部区间）。`output/volume-price.html`（已废弃旧量价页，无页面引用）同步删除；生成器 `src/build_volume_price.py` 仅留档保留。仍保留的 `WCI_周度_2025-2026.csv` 含 2025-11-13 ~ 12-25 的 WCI 综合指数，xlsx `WCI` 表起点为 2026-01-01，**该段为独有历史数据，故未删**。

> **舱位利用率口径（2026-11 起）**：该指标**无公开周度数值来源**——Sea-Intelligence《Sunday Spotlight》、Linerlytica 等机构的装载率仅在付费报告中以文字描述出现，上海航交所周报亦不稳定给出数字。故本表统一记为三档定性标签：**紧张（≥95%）/ 平衡（85%–95%）/ 宽松（<85%）**，依据周报正文判定；当周未披露则**留空**，看板不做跨周顺延（避免显示无来源的数值）。看板对应图表为阶梯图，非百分比折线。

> 宏观与政策类指标（PMI、燃油价、租船费率、EU ETS 碳价等）为公开数据近似，非公司披露口径，看板内已标注。
> **红海通航两项例外**：卡 5 的「红海通航（苏伊士/好望角）」「苏伊士通行占比」已改为 Drewry RST 的**周度实测值**
> （源表 `中远海控_Drewry周报数据.xlsx` 的 `RST`，57 周），不再使用 `中远海控_宏观与政策环境数据.xlsx` 的年度估算；
> 该 xlsx 里的「亚欧绕航好望角比例 / 运力吸收率」仅作 2021–2025 背景参考，2026 年无值，故不进卡片主指标。

---

## 免责声明

本看板为个人研究/学习用途，数据来自公开数据库与公司公告的交叉核对，可能存在误差或时滞，**不构成任何投资建议**。请以公司正式公告与交易所披露为准。
