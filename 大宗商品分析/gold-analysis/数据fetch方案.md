# gold-analysis 项目文档 · 数据架构、口径与运维

> 原名《数据刷新方案 · 哪些真实数据需 fetch 替代快照》，生成于 2026-08-30。
> 📌 **2026-11-15 文档合并**：本项目原有 3 份 md，另两份
> （`direction-approved.md` / `gold-analysis-清理方案.md`）为 2026-08 的历史过程稿，
> 内容多已随重构失效；其仍有价值的信息已提炼为文末**附录 A / B**，原件移入系统废纸篓。
> **本文件是 gold-analysis 唯一项目文档。**
>
> 覆盖范围：方向选型与范围（附录 A）、目录约定与沿革（6.1 / 附录 B）、数据架构与真实数据点、
> 数据源与口径陷阱、fetch 脚本用法、页面模块（分析模版 / 事件条 / A2–A6 宏观因子）、校验与遗留。
> 对象：`output/gold-terminal.html`（终稿 · 终端仪表盘）。

---

## 一、当前数据架构（关键前提）

> ✅ **本节记录的是重构前的问题诊断。方案 Z 已于 2026-08-30 落地，架构缺口已消除，详见第六节「方案 Z 落地记录」。**

页面数据分三处，刷新能力完全不同：

| 位置                                         | 机制                                         | 能否被 `update_gold_data.py` 更新 | 能否实时 fetch              |
| ------------------------------------------ | ------------------------------------------ | ---------------------------- | ----------------------- |
| `GOLD_DATA` 数据块（`/*GOLD_DATA_START/END*/`） | `data-field` 绑定，JS `applyData()` 注入        | ✅ 脚本只改这块                     | ⚠️ 仅 `spot` 有刷新按钮 fetch |
| 顶栏 TICKER（行 305–316）                       | **大部分硬编码文本**，仅 `XAU/USD` 绑了 `data-field`   | ❌ 其余为静态文字                    | ❌                       |
| 央行购金面板 / 债务面板（SVG+表）                       | **完全硬编码 SVG 与 HTML 表**，JS 数组写死在 `<script>` | ❌ 不在 GOLD_DATA               | ❌                       |

> ⚠️ 架构缺口（已修复）：TICKER 里的 10Y UST / DXY / CB OWN / WORLD DEBT 即使 GOLD_DATA 更新也**不会变**（没绑 `data-field`）；央行购金面板与债务面板的全部数值是死 SVG，脚本和刷新按钮都碰不到。这才是"快照"的主要藏身地。

---

## 二、真实数据点逐条映射

刷新频率分级：**实时**(日/盘中) · **周期**(季/月/年) · **研究**(人工/搜索)

| #  | 数据点                                       | 当前快照值              | 来源           | 频率  | 应取的 fetch 方式                                  | 现状（2026-09-19 刷新）                                   |
| -- | ----------------------------------------- | ------------------ | ------------ | --- | --------------------------------------------- | --------------------------------------------------- |
| 1  | 现货 XAU/USD `spot`                         | $4,379             | gold-api.com | 实时  | 已有刷新按钮 fetch ✅                                | ✅ 已接通（fetch + 绑字段）                                  |
| 2  | XAU 滚动价 `tickerXau`                       | $4,379             | gold-api.com | 实时  | 同 #1                                          | ✅ 已接通（绑字段，随 #1 更新）                                  |
| 3  | XAU 日涨跌 `tickerXauChg`                    | +0.8%              | 行情终端/接口      | 实时  | 由 #1 接口或行情 API 取                              | ⚠️ 仍硬编码未取（待补 fetch）                                 |
| 4  | 10Y 美债 `tickerUst`                        | 4.94%              | FRED `DGS10` | 实时  | FRED API（脚本侧 fetch，key 已接）                    | ✅ 已接通 FRED（绑字段，4.94% 实测）                            |
| 5  | 美元指数 `tickerDxy`                          | 98.4               | 行情/forex API | 实时  | FRED 无 ICE DXY，用广义美元指数或第三方                    | 🟡 已绑字段 · ICE 口径人工维护（`dxyBroad`/DTWEXBGS 118.1 仅参考） |
| 6  | 历史高点 `ath`                                | $5,590             | 行情终端         | 周期  | 校验；新高尚可出现                                     | 🟡 已纳入 GOLD_DATA · 周期快照                             |
| 7  | 见顶日 `athDate`                             | 2026-01-28         | 行情终端         | 周期  | 同 #6                                          | 🟡 已纳入 GOLD_DATA · 周期快照                             |
| 8  | 高点区间 `athRange`                           | $5,590–5,603       | 行情终端         | 周期  | 同 #6                                          | 🟡 已纳入 GOLD_DATA · 周期快照                             |
| 9  | 首破4000 `first4k`                          | $4,000             | 历史           | 静态  | 不用取                                           | 静态锚（GOLD_DATA）                                      |
| 10 | 上半年低点 `lowValue`                          | $3,959             | 行情终端         | 周期  | 校验（可能出新低）                                     | 🟡 已纳入 GOLD_DATA · 周期快照                             |
| 11 | 较高点回落 `lowDrop`                           | 26%                | 派生           | 派生  | 由 #1/#10 派生                                   | 派生（存 GOLD_DATA）                                     |
| 12 | 自低点反弹 `reboundFromLow`                    | +8.6%              | 派生           | 派生  | 由 #1/#10 派生                                   | 派生（存 GOLD_DATA）                                     |
| 13 | 事件日/涨幅/文案 `event*`                        | 2026-10-10 / +1.43% | 新闻           | 日   | `src/fetch_event.py`：Google News RSS 选标题→`eventText`，日期→`eventDate`，Yahoo `GC=F` 日线→`eventPct`，源名→`eventSource` | ✅ 已接通自动 fetch（2026-10-12 起，见第七节「事件条自动刷新」） |
| 14 | 中国央行持金 `cbChinaOwn`                       | 2,346t             | PBoC / WGC   | 月   | WGC 月度或 PBoC                                  | ✅ 已纳入 GOLD_DATA · 绑字段 · 月更人工                        |
| 15 | 美债务/GDP `worldDebt`                       | 100%               | 研究/IIF（全球口径） | 季/年 | 人工（全球≠FRED 美国口径）                              | ✅ 已纳入 GOLD_DATA · 绑字段 · 人工（全球口径）                    |
| 16 | ~~JPM 目标价 `jpmTarget` / `jpmTargetNext`~~ | —                  | —            | —   | **已于 2026-09-20 移除**（TICKER 与快照均不再展示，数据/种子已清） |                                                     |
| 17 | 央行年净买 863t / H1 +102t / +346t             | 文本                 | WGC          | 季   | WGC 季报（无公开 API）                               | ✅ 已纳入 GOLD_DATA · stat 卡绑字段                         |
| 18 | 中国 H1 净进口 764t                            | 文本                 | 海关 / WGC     | 半年  | 同 #17                                         | ✅ 已纳入 GOLD_DATA · stat 卡绑字段                         |
| 19 | 央行购金 H1 国别 + 月度序列                         | 全量                 | WGC          | 季   | WGC 季报 → 脚本重建                                 | ✅ 已数据驱动（`GOLD_PANEL_DATA.cbCountry/cbMonthly`）      |
| 20 | 美债务真实数据 2021–25 表 + 图                     | 全量                 | FRED/CBO     | 年   | FRED API（脚本重建）                                | ✅ 已数据驱动（`GOLD_PANEL_DATA.debt`）                     |
| 21 | 叙事/逻辑内嵌数值（矿产3,600t、连续20月增持等）              | 文本                 | 多源           | 周期  | 人工校验                                          | 🟡 嵌入文本 · 人工校验                                      |
| 22 | 价格时间轴 `gold_annual_price_history`        | 年均价 1970–2025     | 世界银行 Pink Sheet | 年    | A1 历史趋势图覆盖；`HIST` 为 HTML 内 JS 常量（1970–2025） | 🟡 页面已覆盖，数据未 xlsx 化（见第十一、十二节）             |

---

## 三、需 fetch 替代快照的真实数据（结论 · 2026-08-30 更新）

> 方案 Z 已落地：TICKER / stat 卡 / 央行购金面板 / 债务面板 / 价格时间轴 **全部改为数据驱动**，数值统一从 `data/gold_data.xlsx` 进出。下面是「已接通 / 待补 / 永久人工」的最新归类。

**A 类 · 实时行情（浏览器 fetch，页面加载即刷）**

- #1 现货 ✅、#2 XAU 滚动价 ✅、#4 10Y UST ✅（FRED 脚本侧 fetch，4.67% 实测）—— **均已接通且绑字段**
- #3 XAU 日涨跌 ⚠️ 仍硬编码未取 —— **唯一待补的实时项**
- #5 DXY 🟡 ICE 口径无 FRED 源，已绑字段但值仍人工维护（`dxyBroad`/DTWEXBGS 118.1 仅参考）

**B 类 · 周期基本面（脚本刷新，季度/月度重跑 `fetch_gold_data.py`）**

- #14 中国持金、#15 美债务/GDP、#17 央行净买、#18 中国进口 ✅ 已纳入 GOLD_DATA 并绑字段（值由人工/脚本季度更新）
- #19 央行购金面板、#20 债务面板、#22 价格时间轴 ✅ 已数据驱动（`GOLD_PANEL_DATA.cbCountry/cbMonthly/debt/timeline`）
- #6/#7/#8/#10 历史锚点 🟡 已纳入 GOLD_DATA，待下个周期人工/脚本刷新
- ~~#13 事件~~ ✅ 2026-10-12 起由 `src/fetch_event.py` 每日自动刷新（Google News RSS + Yahoo 日线）

**C 类 · 研究/人工（无 clean API，保留为手动更新字段）**

- 驱动权重 30/25/20/15/10%、#21 叙事内嵌数值 —— 永久人工维护

---

## 四、要落地"fetch 替代快照"，需改的架构

> ✅ **本节 5 项架构改造已在方案 Z 中全部落地**（2026-08-30）：TICKER 全绑、脚本 DATA 扩展为 Excel 数据仓、面板数据驱动、FRED 通道接通、WGC 走"下载季报→填 Excel"的人工链路。下方保留原 TODO 描述作为归档。

1. **TICKER 全部绑 `data-field`**：把 #4/#5/#14/#15/#16 也绑到 GOLD_DATA（目前只有 XAU 绑了），否则 GOLD_DATA 更新 TICKER 仍不动。 ✅ 已完成
2. **扩展 `update_gold_data.py` 的 DATA dict**：把 #6–#20 的周期字段与原先只含行情的 GOLD_DATA 合并，标注"季度更新区 / 月度更新区 / 研究更新区"。 ✅ 已迁至 `schema.py` 的 `SEED_SNAPSHOT` + Excel「行情快照」sheet
3. **央行购金面板 + 债务面板改为数据驱动**：
   - 把 #19 的国别/月度数组、#20 的债务/利息/(r−n) 数组纳入数据块；
   - SVG 改为由 JS 读数据块渲染（参考债务面板已有的 `draw()` 函数），不再写死 `<rect>` 坐标；
   - 这样 `update_gold_data.py` 才能像更新行情一样更新这两块"真实数据"。 ✅ 已完成（`GOLD_PANEL_DATA` + IIFE 渲染）
4. **实时通道补 FRED**：刷新按钮目前只 fetch gold-api；要 #4/#5 实时，需加 FRED（带 key）或行情聚合接口，并处理浏览器 CORS。 ✅ FRED 已接通（脚本侧 fetch）；浏览器刷新按钮仍只刷现货（CORS/key 不宜下发）
5. **WGC 数据无公开 API**：#17/#18/#19 的"fetch"实际是"下载 WGC 季报 → 人工/脚本抽取 → 填入数据块"，不是浏览器实时调用。 ✅ 已按此方式落地

---

## 五、可执行下一步（✅ 已拍板：方案 Z）

- ~~方案 X：先把 TICKER 全绑 data-field + 扩展脚本 DATA（覆盖 B 类）~~
- ~~方案 Y：在 X 基础上加 FRED 实时取 #4/#5（需 FRED key）~~
- **方案 Z：连央行购金/债务面板也改为数据驱动 SVG（最大改动，彻底消除死 SVG）—— ✅ 已选定并落地**

> 方案 Z 是 X + Y 的超集：TICKER 全绑、脚本 DATA 扩展、FRED 通道、面板数据驱动全部包含。落地记录见下一节。

---

## 六、方案 Z 落地记录（2026-08-30）

### 6.1 新目录约定（对齐同级的 `oil-analysis/` 项目）

| 目录        | 职责              | 说明                                     |
| --------- | --------------- | -------------------------------------- |
| `src/`    | **全部代码**        | 路径集中在 `src/paths.py`，其余模块引用它，不写死相对路径   |
| `data/`   | **Excel 数据仓**   | `data/gold_data.xlsx` 是唯一数据源，5 个 sheet |
| `output/` | **HTML 页面归档目录** | `gold-terminal.html` 为可重建终稿；另含 3 个自包含独立可视化页（2026-11-15 归档）；历史 `_bak-*.html` 已清理 |

数据流（单向，不可倒流）：

```
数据源 API ──fetch_gold_data.py──▶ data/gold_data.xlsx ──build_html.py──▶ output/gold-terminal.html
                                        ▲
                              人工维护（WGC/研报类）
```

### 6.2 `src/` 模块

| 文件                   | 职责                                                                                |
| -------------------- | --------------------------------------------------------------------------------- |
| `paths.py`           | 路径集中定义（`WORKSPACE / DATA_DIR / DATA_XLSX / SRC_DIR / OUTPUT_DIR / TERMINAL_HTML`） |
| `config.py`          | 数据源端点 + **口径陷阱说明**：`GOLD_API`、`FRED_SERIES`、`DXY_API`、`MANUAL_ONLY`               |
| `schema.py`          | Excel 表结构 + 种子数据（原 `update_gold_data.py` 的 `DATA` 字典迁入此处）                         |
| `excelio.py`         | Excel 读写层：`ensure_workbook()` / `read_*()` / `update_snapshot()` / `touch_meta()` |
| `fetch_gold_data.py` | 抓取 → 写 Excel。参数：`--spot` / `--fred` / `--dry-run`                                 |
| `build_html.py`      | 读 Excel → 注入 HTML 两个标记块。参数：`--check`（只校验不写）                                       |

### 6.3 Excel 表结构（`data/gold_data.xlsx`）

| Sheet    | 列                                    | 数据来源                                                                                                                                |
| -------- | ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `行情快照`   | 字段 / 值 / 说明 / 来源 / 频率                | 30（含 `spot`、`cbNet2025`、`cnImportH1` 等原先硬编码且脚本碰不到的字段）                                                                               |
| `央行购金国别` | 国别 / 净买入(t) / 来源 / 备注                | 11（波兰 +82 … 土耳其 −83）                                                                                                                |
| `央行购金月度` | 月份 / 净买入(t)                          | 国家外汇管理局  主&#x9875;**>&#x20;**&#x7EDF;计数&#x636E;**>&#x20;**&#x7EDF;计数据列&#x8868;**>&#x20;**&#x5916;汇储&#x5907;**>&#x20;**&#x5B98;方储备资产 |
| `黄金月度均价` | 月份 / 月度均价(USD/oz) / 口径说明      | 当年各月（当前 10 行，2026-01 ~ 2026-10）；由 `fetch_gold_monthly.py` 从 Pink Sheet 月度表抓取，跨年自动取最新年份                                  |
| `美债数据`   | 年份 / 债务占GDP% / r / n / 利息占GDP% / r−n | 5（2021–2025）                                                                                                                        |
| `元数据`    | 键 / 值 / 说明                           | 前瞻投影参数：`projB0=121.5`、`projR=2.59`、`projN=5.1`、`projDef=5.9`、`projYears=15`                                                         |

### 6.4 HTML 侧改造

1. **两个标记块**（`build_html.py` 只替换标记之间，完全不碰 CSS/布局）：
   | 标记                                                    | 内容                                                                                 |
   | ----------------------------------------------------- | ---------------------------------------------------------------------------------- |
   | `/*GOLD_DATA_START*/ … /*GOLD_DATA_END*/`             | 标量字段，`applyData()` 遍历 `[data-field]` 注入                                            |
   | `/*GOLD_PANEL_DATA_START*/ … /*GOLD_PANEL_DATA_END*/` | **新增**：面板数组 `window.GOLD_PANEL_DATA`，含 `cbCountry` / `cbMonthly` / `debt` / `meta` |
2. **TICKER 全绑 `data-field`**：10Y UST、DXY、CB OWN、WORLD DEBT/GDP 已全部绑定，此前只有 XAU 绑了。
3. **stat 卡全绑**：`cbNet2025` / `cbH1Summary` / `cnImportH1` / `worldDebt` / `netInterestShare`。
4. **死 SVG → 数据驱动容器**：
   - `<svg id="cbCountry">`、`<svg id="cbMonthly">` 清空为容器，由 IIFE 读 `GOLD_PANEL_DATA` 渲染图1（发散条形）/ 图2（月度节奏）。
   - 债务面板 `dtDebt` / `dtInt` / `dtRN` / `dtFwd` 的 JS 数组改为读数据块；前瞻投影参数改从「元数据」sheet 取。
   - **`spot_price_timeline` 改为数据驱动**（2026-08-30，应需求「需要」）：原 HTML 里的硬编码 `<path>` + 4 个 `<g class="tl-node">` 节点（死 SVG，违反项目约定）已清空为 `<g id="tl-dyn">` 容器，由新 IIFE `drawTimeline(P.timeline)` 读 `GOLD_PANEL_DATA.timeline` 渲染。价位引用「行情快照」字段，由 `build_html.py` 在注入时解析为数字，故 `spot` 一改（如 fetch 后变成 $4,456）曲线末点自动跟着变，**单一数据源**。价格→y 映射沿用 `y = 40 + (5600 - 价位) / 12`，见顶落在顶部、低点在底部（此前曲线方向画反的 bug 已根治）。
   - `draw()` 加了 `if(!svg||!xs||!xs.length) return;` 兜底，数据缺失不会连坐整页脚本；`drawTimeline` 同样有 `if(!svg||!rows||!rows.length) return;` 兜底。


### 6.5 数据源与口径陷阱（务必留意）

| 项           | 状态            | 说明                                                                                                                                                                           |
| ----------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 现货 XAU      | ✅ 已接通         | `https://api.gold-api.com/price/XAU`，免 key                                                                                                                                   |
| FRED        | ✅ 已接通         | key 已写入 `src/config.py` 的 `_DEFAULT_FRED_KEY`（环境变量 `FRED_API_KEY` 优先覆盖）。⚠️ 明文 key，勿提交公开仓库。`tickerUst`(DGS10) 已实测 4.67% 接通                                                    |
| **DXY**     | 🟡 已绑字段 · 值人工 | FRED **没有 ICE DXY**。`DTWEXBGS` 是**广义**美元指数（约 120），与 ICE DXY（约 98）**量级不同**。`tickerDxy`(ICE 口径) 已绑 `data-field` 但值仍人工维护；另设 `dxyBroad`(DTWEXBGS 118.1) 仅作参考，**不覆盖** `tickerDxy` |
| **债务/GDP**  | ⚠️ 口径陷阱       | FRED `GFDGDPA188S` 是**美国联邦**债务/GDP（121.5%），而 TICKER 标签写的是 `WORLD`（全球口径 100%）。已拆为 `worldDebt`（人工维护，全球口径）与 `usDebtGdp`（FRED 可写），避免错量级覆盖                                        |
| 央行购金 / 中国持金 | 人工            | 无公开 API（WGC 季报 / PBoC），已纳入 GOLD_DATA 并绑字段，直接改 Excel 对应行即可，详见 `config.MANUAL_ONLY`                                                                                            |

### 6.6 常用命令

```bash
cd gold-analysis
PY=/Users/sto1/.workbuddy/binaries/python/envs/default/bin/python

$PY src/fetch_gold_data.py --dry-run   # 只看抓到什么，不写 Excel
$PY src/fetch_gold_data.py             # 抓取 → 写 data/gold_data.xlsx
$PY src/fetch_gold_data.py --spot      # 只刷现货
$PY src/fetch_gold_data.py --fred      # 只刷 FRED 序列（需 key）

$PY src/build_html.py --check            # 只校验并预览，不写文件
$PY src/build_html.py                    # Excel → 注入 output/gold-terminal.html
$PY src/build_html.py --strip-node-ids   # 注入 + 清掉编辑器节点标记（部署前用）
```

首次使用或 Excel 被删：`$PY -c "import src.excelio as e; e.ensure_workbook(force=True)"` 用种子数据重建。

#### `--strip-node-ids` 说明

可视化页面编辑器会给每个节点注入 `data-page-node-id`（本项目 471 个，约 +2 万字符）。它是编辑器的节点追踪标记，对渲染无用。

```bash
$PY src/build_html.py --strip-node-ids
# 编辑器节点标记：data-page-node-id × 471 —— 本次将清理，可省 20,253 字符 / 20,253 字节
# ✓ 已清理 data-page-node-id × 471（页面编辑器节点追踪已失效，本脚本无法还原）
# 大小 49,515 字符 / 55,113 字节
```

**只清 `data-page-node-id` 这一个属性** —— `data-field`（39 处数据绑定）和 `data-w`（5 处，权重条 30/25/20/15/10 的原始属性）必须原样保留。

⚠️ **两个注意点**：

1. **清理不可逆**。会破坏页面编辑器的节点追踪。执行前建议备份：  
   `cp output/gold-terminal.html ~/.Trash/xxx/gold-terminal.html.with-node-ids`
2. **若编辑器正打开该文件，清理可能被还原**。实测出现过「脚本报已清理，几秒后读回来又变回 471 个」的情况——外部进程以 `copy2` 语义还原，**保留了 mtime**，所以从时间戳上看不出来，容易误判为脚本没生效。  
   判断方法：清理后隔几秒再 `grep -c data-page-node-id` 复查一次。

### 6.7 FRED 接通后的实测结果（2026-08-30）

| 序列                            | FRED 实测值   | 观测日        | 页面快照  | 差异                            |
| ----------------------------- | ---------- | ---------- | ----- | ----------------------------- |
| `DGS10` → `tickerUst`         | **4.67%**  | 2026-08-27 | 4.18% | **+0.49 个点**（快照已过期）           |
| `DTWEXBGS` → `dxyBroad`       | 118.1      | 2026-08-21 | —     | 新字段，仅参考                       |
| `GFDGDPA188S` → `usDebtGdp`   | **121.5%** | 2025-01-01 | —     | 与债务面板 2025 的 **121.5 完全吻合** ✓ |
| `FYOIGDA188S` → `interestGdp` | 3.15%      | 2025-01-01 | —     | 债务面板用，跨年值需人工并入 sheet          |

> **意外收获**：`GFDGDPA188S` = 121.497% 与债务面板手填的 121.5 完全对上，反向验证了当初「这是**美国联邦**口径、不能当 WORLD 全球口径（100%）用」的判断正确。

**已修复的网络问题**：FRED 对新建连接会偶发 SSL 握手重置（`UNEXPECTED_EOF_WHILE_READING`），表现为**每个新序列第一次请求必失败、重试即成功**——curl 正常但 urllib 报错，极易误判为 key 无效。  
已在 `http_get_json()` 内置重试（`config.HTTP_RETRIES=4`，退避 0.6/1.2/1.8s）。HTTP 4xx/5xx 属确定性错误，不重试直接返回。

**已修复的脚本问题**：`build_html.py` 曾把 `len(str)`（字符数）误标为「字节」（中文 UTF-8 占 3 字节，49,511 字符 = 55,111 字节），改为分别打印。

### 6.8 验证结果

- `GOLD_DATA` 字段 **30** 个；`GOLD_PANEL_DATA` 键 `['cbCountry','cbMonthly','timeline','debt','meta']`
- 标签平衡：div 164/164 · span 112/112 · script 3/3 · svg 7/7 · table 1/1 · style 1/1
- 6 个 SVG 容器 + 1 个 `<g id="tl-dyn">` 容器全部确认为空（内容由 JS 生成，无死 SVG）
- 三段内联脚本均通过 `node --check`
- `data-field` 绑定 **39 处（去重 27，无悬空绑定）**；另有 3 个 GOLD_DATA 字段（`dxyBroad`/`usDebtGdp`/`liveApi`）刻意未绑元素，作备用字段
- Node DOM stub 实跑渲染：
  | 图                           | 元素                           | 关键点                                                     |
  | --------------------------- | ---------------------------- | ------------------------------------------------------- |
  | `cbCountry` 图1              | 11 rect / 31 text            | 条形宽 **337.1 / 164.4 / 341.2** —— 与审批稿逐像素一致              |
  | `cbMonthly` 图2              | 6 rect / 13 text             | 正负双尺度                                                   |
  | `dtDebt` / `dtInt` / `dtRN` | 各 5 circle / 12 text         | 2021–2025                                               |
  | `dtFwd`                     | 48 circle / 4 path / 15 text | 终点 **158 / 200 / 239**（n=5.1 / 3.0 / 1.5），X 轴 2025→2040 |

> `dtFwd` 基准线手工校验：121.5 按 `b×0.9749+5.9` 迭代 15 年 = 157.5 ≈ **158** ✓ 模型自洽。

> ⚠️ **校验脚本陷阱**：正则 `<svg[^>]*id="([^"]+)"` 会误匹配 `data-page-node-id="xxx"` 里的 `id="`。必须用 `\sid=`（前面有空白字符）才能精确命中真正的 `id` 属性。

### 6.9 遗留（不在本次范围）

- 价格时间轴 `spot_price_timeline` 已于 2026-08-30 改为数据驱动（`GOLD_PANEL_DATA.timeline`），**移出遗留清单**。
- 页面上的「刷新」按钮仍只 fetch gold-api 现货；FRED 走脚本侧（key 不宜下发给浏览器，且有 CORS）。
- **#3 XAU 日涨跌 `tickerXauChg` 仍硬编码未取**（唯一的实时待补项）；~~#13 事件文案~~ 已于 2026-10-12 接通自动 fetch（见第七节「事件条自动刷新」）；#21 叙事内嵌数值仍为人工维护字段。
- `tickerDxy`（ICE DXY 口径）仍为人工维护 —— FRED 无此口径，`dxyBroad`(118.1) 仅作参考。
- `interestGdp` 的跨年序列需人工并入「美债数据」sheet（脚本只取最新值）。

---

## 七、事件条自动刷新（2026-10-12）

> 背景：#13 `eventDate / eventPct / eventText` 三字段虽已绑 `data-field`，但**没有任何 fetch 会碰它**，
> 属于纯人工快照 —— 2026-10 时页面 `spot` 已到 $4,379、10Y 已到 5.22%，event 条却仍停在 2026-08-05。

### 7.1 数据源选型（2026-10-11 实测）

| 源                                                     | 结果                     |
| ----------------------------------------------------- | ---------------------- |
| **Google News RSS**（中/英，免费无 key）                       | ✅ 200，中英各 100 条，含 `pubDate` + `source` |
| **Yahoo chart `GC=F` 日线**（免费无 key）                     | ✅ 200，127 个交易日，可算单日涨跌    |
| 华尔街见闻 lives / 东方财富快讯 / Investing RSS                    | ✅ 可用（备用，见 `config.EVENT_FEEDS` 注释） |
| Stooq 日线 CSV                                          | ❌ JS 反爬挑战页               |
| Kitco RSS · mining.com                                | ❌ 404 / 403            |
| FRED 伦敦金定盘价 `GOLDPMGBD228NLBM`                         | ❌ 序列已下架（400 not exist）   |

### 7.2 链路

```
Google News RSS ──标题──> eventText      行情快照 sheet
                 ──日期──> eventDate            │
                 ──源名──> eventSource          │  build_html.py
Yahoo GC=F 日线 ──当日涨跌──> eventPct           ↓
                                        output/gold-terminal.html
        全部候选 ──> 「黄金事件流」sheet（40 行，含链接）
```

- `eventText`（标题）需清洗：去 Google News 的 `- 来源` 后缀、去中文站的 `|关键词堆砌` 尾巴，
  再按中/英分别截断（中文 34 字 / 拉丁 78 字符）。
- **打分**（`config.py` 可调）：`来源权重 × (1+0.35×信号词数) × 1/(1+1.2×天数) × 噪音惩罚`。
  标题必须命中核心词（黄金/金价/gold/XAU…）才进候选；命中"饰品/柜台/克重/促销"等消费噪音则 ×0.25。
- 「黄金事件流」**第 1 行 = 页面正在显示的那条**，其余按日期倒序；想换显示哪条，把该行挪到第 1 行再 `build_html.py`。
  ⚠️ `excelio.read_events()` **不要按日期重排**，否则第 1 行会变成更新但没被选中的候选（曾踩过）。

### 7.3 用法

```bash
python3 src/fetch_event.py            # 抓取并写入
python3 src/fetch_event.py --list 12  # 只看候选 Top12，不落盘
python3 src/fetch_event.py --days 7   # 放宽候选窗口
python3 src/fetch_event.py --dry-run  # 只打印将写入的字段
python3 src/build_html.py             # 注入 HTML
```

### 7.4 页面侧改动

- HERO「当前报盘」note 由 `…单日涨超 4%，因美元走软…`（写死）改为
  `<b data-field="eventDate"> 单日 <b data-field="eventPct">，<span data-field="eventText">`，全数据驱动。
- eventbar 新增 `.evsrc`（来源徽标），绑 `eventSource`。
- `eventPct` 正负不固定，颜色不再写死 `var(--up)`：新增 `tintEvent()` 按符号取 `--up`(绿) / `--down`(红)。
- **EVENT 标签是按钮**（`<button id="evBtn">`，2026-10-13）：点击在候选池
  `GOLD_PANEL_DATA.events`（构建时注入的 40 条）中切换——第 1 次点击切到日期最新的候选，
  之后每点一次循环下一条，走完一圈回到构建时选中的默认条；顶部 databar 会提示
  `EVENT → 日期 · 来源（候选 i/N）`。悬停有提亮，tooltip 说明用法。
- ⚠️ **按钮只能切换已注入的候选，不能在浏览器里抓新新闻**：实测 Google News RSS / Yahoo
  chart 均无 CORS 头，公共代理（allorigins 500、corsproxy 401 要 key、r.jina.ai 403）不可靠；
  要拿"今天"的事件仍需本地跑 `fetch_event.py`。
- 常驻校验：`node tools/test_event_bar.js`（字段齐全 / 绑定完整 / 首行一致 / 格式合法 /
  按钮点击切换 + 循环回绕，DOM-stub 实跑）。

### 7.5 遗留

- `GC=F` 是 COMEX 期货，与 XAU/USD 现货有基差；`eventPct` 是**方向/幅度近似**，不是现货精确涨跌。
- 新闻标题只作"事件提示"，不构成因果判断；重要事件仍需人工核对后在「黄金事件流」里替换首行。
- `tickerXauChg`（XAU 日涨跌）仍硬编码未取 —— 若要一并自动，可复用 `fetch_event.py` 的 `fetch_daily()`。

---

## 八、A 模块 A2–A6 宏观因子数据化（方案 2 · 2026-11-05）

> 背景：删除通用版后，完整版 A 模块里 A1 已有 1970–2026 历史图，但 **A2–A6 五个驱动因子
> 只有静态机制文字 + 2 个空输入框**，没有任何真实数据。本轮按「现值徽章 + mini sparkline」落地。

### 8.1 数据源（2026-11-05 实测可用，全部免费）

| 因子 | 主源 | 实测最新 | 频率 | 写入值 |
|---|---|---|---|---|
| A2 实际利率 | FRED `DFII10` 10Y TIPS | 2.65（11-03） | 日 | 52 周 |
| A3 美元指数 | Yahoo `DX-Y.NYB`（ICE DXY） | 101.63（11-05） | 日 | 52 周 |
| A4 央行购金 | 复用「黄金供需季度」央行及其他机构列 | 288.9t（Q2'26） | 季 | 12 季 |
| A5 地缘风险 | Caldara-Iacoviello GPR `GPRD_MA30` | 164.0（11-02） | 日 | 52 周 |
| A6 金油比 | Yahoo `GC=F` ÷ FRED `DCOILWTICO`(WTI) | 39.5 桶/盎司（11-03） | 日 | 52 周 |

- FRED key 复用 `config.FRED_API_KEY`；Yahoo 日线复用 `fetch_event.fetch_daily()`。
- GPR 日频 xls（3.2MB，CDFV2）缓存于 `data/gpr_daily_recent.xls`，用 `xlrd 2.0.2` 读；
  `--force-gpr` 强制重下，`--no-gpr` 跳过。
- ⚠️ **A6 用的是 GC=F 期货日线**，与页面 `spot` 现货快照（$4,379）不同，
  故比值 ≈39.5 而非用快照算的 43.9；口径已在卡片 title 标注。
- 同 workspace `oil-analysis/data/dataset/prices.json` 有日频 WTI/Brent，但**未跨项目引用**（避免耦合）。

### 8.2 链路（沿用单向流，页面不新增 fetch）

```
FRED / Yahoo / GPR xls / 现有 GDT sheet
        ↓ src/fetch_macro.py（日频→周频降采样，每周最后一个有效值）
data/gold_data.xlsx：「宏观因子现值」5 行 +「宏观因子时序」220 行（长表 因子|日期|数值）
        ↓ src/build_html.py
GOLD_PANEL_DATA.macroLatest / macroSeries
        ↓ output/gold-terminal.html
A2–A6 每张卡 = 只读徽章（值/单位/源/日期）+ 空 <svg class="macro-spark"> + IIFE 渲染
```

- 长表存时序，**避免日/季频率被强行对齐到同一行**；各因子独立绘图，不共轴。
- 空 `<svg>` + IIFE 是项目硬性规范；`draw()` 有空数据兜底（显示「暂无数据 · 请跑 fetch_macro.py」），
  并暴露 `window.__macroStat` 供校验。
- 数据是只读徽章，**人工「判断」输入框 56 个全部保留**。

### 8.3 口径陷阱（勿混用）

1. `DFII10`(2.65) ≠ `DGS10 − T10YIE`(4.95−2.26=2.69)，本表只用 DFII10；T10YIE 仅抓来对照。
2. ICE DXY(≈101) ≠ FRED 广义美元 `DTWEXBGS`(≈121)，量级不同。
3. A4 是 **WGC GDT 季度**口径，与 IFS「央行购金年度」不是同一口径。
4. GPR 是报纸词频**代理**指标、30 日均，非价格、非避险溢价。
5. `GC=F` 是 COMEX 期货、`DCOILWTICO` 是 WTI 现货，金油比仅作趋势观察。
6. 浏览器端 FRED/Yahoo/GPR 全无 CORS → 必须本地 fetch + build_html 注入，页面不新增 fetch。

### 8.4 用法

```bash
python3 src/fetch_macro.py            # 抓取并写 xlsx
python3 src/fetch_macro.py --dry-run   # 只看现值，不落盘
python3 src/fetch_macro.py --force-gpr # 重下 GPR xls
python3 src/build_html.py              # 注入 HTML
node tools/test_macro_factors.js       # 常驻校验
```

### 8.5 校验

`tools/test_macro_factors.js`：5 项现值 / 5 键时序（52·52·12·52·52 点）/ 5 个空 SVG 容器 /
DOM-stub 实跑 IIFE（`badges=5 sparks=5 empty=[]`，各图产出 path+circle+text）/ 空数据兜底 /
人工输入框仍 56 个。全量 9 个校验脚本 PASS；`build_html.py` 重建幂等（模版区在两个注入标记之外）。

### 8.6 遗留

- 页面顶栏 `tickerDxy` 仍写 98.4，而 ICE DXY 实际 101.6 —— 可将 `fetch_macro.py` 的 A3 现值
  同步写入 `tickerDxy`（需用户确认是否改变顶栏口径）。
- A4 目前是季度频率，mini 图只有 12 点；如需更密可改用 IFS 月度净购金（但会换成另一口径）。
- `data/gpr_daily_recent.xls` 3.2MB 是新增缓存，data/ 目录由 756K → 3.9M。

---

## 附录 A · 方向选型与范围确认（原 `direction-approved.md`，2026-08-30）

> 该文档记录项目立项时的视觉方向决策，是「为什么是这个看板」的唯一决策留痕；
> 原件已于 2026-11-15 并入本文件（备份在 `~/.Trash/`）。

### A.1 三版方向（当时 `output/` 下的提案稿）

| 方向 | 文件 | 特征 | 现状 |
| --- | --- | --- | --- |
| 一 · 终端仪表盘 | `gold-terminal.html` | Bloomberg-terminal 风，密集面板网格 + HERO + 力矩阵 + 叙事日志 | ✅ 用户选定，现终稿 |
| 二 · 叙事长卷 | `gold-narrative.html` | 深色研究札记，纵向章节 + 衬线标题 + SVG 弧线 | ❌ 已弃用并删除 |
| 三 · 对决天平 | `gold-tugofwar.html` | 左推涨 / 中天平 / 右压制，情景切换交互 | ❌ 已弃用并删除 |

### A.2 用户选择（原话 / 证据）

- 三方向初稿环节选择：「滚动式网页报告 + 深色分析仪表盘风」。
- 用户发送方向一截图（「央行年净买入 863t / 2025 年」数据卡片）并确认终稿采用方向一。
- 央行购金嵌入方案 = **方案 A**：把第一张数据卡片升级为「可展开的央行购金复合面板」，
  点击内联展示 2026 H1 国别 breakdown 发散条形图（图 1）+ 月度净购金节奏图（图 2），
  图表重绘为 terminal 暗色风格（金 / 绿 / 红）。

### A.3 产出

- 终稿：`output/gold-terminal.html`（已嵌入方案 A）。
- 独立可视化（浅色参考版）：`output/central-bank-gold-2026.html`（2026-11-15 由根目录归档至 `output/`）。

---

## 附录 B · 目录沿革与归档（原 `gold-analysis-清理方案.md`，2026-08-30）

> 原件是 2026-08 的清理方案与历史目录树，多数内容已随重构失效；此处只保留现行约定与沿革节点。
> 详细目录约定见第六节 **6.1**；原件备份在 `~/.Trash/`。

### B.1 现行目录约定（三段式，与同级的 `oil-analysis/` 一致）

| 目录 | 职责 |
| --- | --- |
| `src/` | 全部代码，路径集中在 `src/paths.py`，其余模块引用它，不写死相对路径 |
| `data/` | Excel 数据仓 `gold_data.xlsx`（唯一事实源）+ IFS / GDT / GPR 源文件与缓存 |
| `output/` | **全部 HTML 页面**；`gold-terminal.html` 为可完全重建的终稿 |
| `tools/` | 常驻校验脚本（Node DOM-stub） |
| 项目根目录 | 只放文档与依赖清单；**不放 HTML**；历史 `_bak` 用完即清理 |

单向流：`数据源 → fetch/seed → data/*.xlsx → build_html.py → output/*.html`。
改数据只改 xlsx，**绝不手改终稿 HTML**；`build_html.py` 只替换两个数据标记之间的内容。

### B.2 沿革节点

| 日期 | 动作 |
| --- | --- |
| 2026-08-30 | 删除方向二 / 三提案稿与 `.DS_Store`；**方案 Z 重构**，`output/update_gold_data.py` 退役，其 `DATA` 字典种子值迁入 `src/schema.py`，职责由 `build_html.py` 接管 |
| 2026-09 ~ 10 | 追加双版本分析模版、1970 年以来历史趋势图、央行购金图 1 / 2 / 3、GDT 供需季度图、event 自动刷新 |
| 2026-11-05 | 删除通用版分析模版（仅保留完整版）；A2–A6 宏观因子数据化（方案 2，见第八节） |
| 2026-11-15 | 3 个根目录 HTML 移入 `output/`；`output/` 下 2 个 `_bak-*.html` 移入废纸篓；**合并 3 份 md 为本文件** |

### B.3 当前目录（合并后）

```
gold-analysis/
├── 数据fetch方案.md          ★ 唯一项目文档（本文件）
├── requirements.txt
├── src/                        代码：paths / config / schema / excelio / fetch_* / build_html
├── data/                       gold_data.xlsx（12 sheet）+ 源文件与缓存
├── output/                     4 个 HTML（终稿 + 3 个独立可视化）
└── tools/                      9 个常驻校验脚本
```

已移入 `~/.Trash/` 的文档原件：`direction-approved.md`、`gold-analysis-清理方案.md`（内容见附录 A / B）。

### B.4 删除与校验原则

- 所有删除一律 `mv` 到 `~/.Trash/`（可恢复），**不用 `rm`**。
- 校验脚本不得依赖外部备份文件；「完整版区块未被污染」改用固化 SHA256 基线
  （见 `tools/test_template_single.js`）。
- 任何结构变更后必跑：标签平衡 → 数据块完整 / 无悬空绑定 → 空 SVG 容器 →
  `node --check` 内联脚本 → Node DOM-stub 实跑 → 全量校验脚本 → 确认仅本地未推送。

---

## 九、白底浅色主题（方案 2 · 2026-11-15）

> 用户确认「按方案 2、默认设置来」。附录 A 记录的是 2026-08 的**深色**选型原话，
> 属历史留痕；**当前终稿已改为白底**，本节为现行口径。

### 9.1 默认值（用户确认的 4 项）

| 项 | 取值 |
| --- | --- |
| 范围 | **仅 `output/gold-terminal.html`**；两个债务页保持深色，`central-bank-gold-2026.html` 本就是白底 |
| 涨跌色 | 沿用现有约定（**涨绿 / 跌红**），只加深以适配白底；未改为涨红跌绿 |
| 金色 | `#E0B84C → #9A6B00`（白底对比度 4.69:1，满足 WCAG AA 正文 4.5） |
| 暗色主题 | 不保留（未做双主题切换）；原稿备份在 `~/.Trash/gold-terminal-dark-*.html` |

### 9.2 改动范围

一次性替换 **60 条规则 / 80 处命中**，全部是颜色字面量，不碰 HTML 结构、数据绑定与交互逻辑：

| 阶段 | 内容 | 处数 |
| --- | --- | --- |
| C | `:root` 14 个颜色变量 | 14 |
| A | 特殊上下文（反白文字、渐变、斜纹、阴影、输入框、半透明面积、JS 标签色） | 23 |
| B | 剩余硬编码 hex 按语义映射 | 43 |

- ⚠️ `<style>` 有**两块**（主 CSS + 模版区 CSS），两块都覆盖。
- 主题改动位于 `/*GOLD_DATA_START/END*/` 与 `/*GOLD_PANEL_DATA_START/END*/` **之外**，
  `build_html.py` 只替换这两个标记 → 重建数据不会把白底冲掉（已实测幂等）。
- 可复现脚本：`tools/apply_light_theme.py`（`--dry-run` 只打印统计）。

### 9.3 现行色板

| 变量 | 值 | on #fff 对比度 |
| --- | --- | --- |
| `--bg` / `--panel` | `#ffffff` | — |
| `--bg-2` | `#f7f8fa` | — |
| `--line` / `--line-2` | `#e3e7ed` / `#cbd3dd` | — |
| `--txt` | `#1f2933` | 14.76:1 |
| `--txt-dim` | `#5b6672` | 5.85:1 |
| `--txt-faint` | `#8a94a1` | 3.07:1（仅弱提示） |
| `--gold` | `#9A6B00` | 4.69:1 |
| `--gold-2` | `#8A6508` | 5.32:1 |
| `--gold-dim` | `#E8D9A8` | 仅用于 border / 渐变 |
| `--up` / `--down` | `#1f7a4d` / `#c0392b` | 5.32 / 5.44:1 |
| `--accent-cool` | `#2E6D9E` | 5.53:1 |

图表：网格线 `#e5e9ef`、轴标签 `#6b7684`、主线 `#9A6B00`、面积 `rgba(154,107,0,.12)`、
圆点白心深金边、图表容器底 `#f7f8fa`、输入框底 `#ffffff`。

### 9.4 两个必须记住的坑

1. **`--gold-dim` 从暗金改成浅金后，只能做 border / 渐变**。它原先在 6 处被当作文字色 /
   SVG fill（力矩阵举例行、页脚加粗、储备轴标签等），白底上会完全看不见 → 已全部改为
   `var(--gold-2)`。`test_light_theme.js` 有断言防止回退。
2. **JS 里的图表标签色要按用途分别处理**：条内数值标签（彩色柱上）→ 白字；
   柱外/负值标签（页面底上）→ `var(--txt)`；储备轴标签 → 深金。不能统一替换。

### 9.5 校验与回滚

- 新增 `tools/test_light_theme.js`：14 个变量值 / 6 组 WCAG 对比度 / 37 种暗色残留 /
  暗色专用效果改写 / 浅金未用于文字 / 数据块与结构锚点 / div 平衡。
- 全量 10 个校验脚本 PASS；`build_html.py` 重建幂等；headless Chrome 截图复核首屏。
- 回滚：`~/.Trash/gold-terminal-dark-20261115-133929.html`（改前 204,951 字节）直接覆盖即可。
- 顺带修复 `tools/test_cncb_card_sync.js`：原断言写死 `2,410t / 23 / 103t`，
  xlsx 更新到 2026-10 后误报 FAIL；改为数据驱动（A 校验格式自洽，B/C 用注入数据断言）。

---

## 十、刷新按钮移位与状态条删除（2026-11-15）

用户要求：把「⟳ 刷新实时金价」移到 HERO「当前报盘 · SPOT」卡片右上角，功能不变，
**删除按钮原来所在的整条数据状态栏**。

### 10.1 改动

| 动作 | 内容 |
| --- | --- |
| 删除 | 整条 `.databar`（8 行 / 815 字符）：离线快照标签、`数据截至 2026-09`、实时源、最近刷新、原按钮、提示行 |
| 删除 | 对应 CSS 2,228 字符（`.databar` 及其 9 条子规则） |
| 新增 | HERO 右侧 cell 用 `.spot-head` flex 行包住标题与 `.spot-actions`；按钮靠右（`margin-left:auto`），窄屏 `flex-wrap` 自动换行，不需媒体查询特判 |
| 后续删除 | 14:38 起 `#dbHint` / `.rf-hint` 及所有结果提示文案全部删除（见 10.4） |

### 10.2 最终交互（经 10.4 修订后）

- 核心逻辑保留：`fetch(D.liveApi)` → `D.spot=s; D.tickerXau=s; D.spotAsOf=todayStr(); applyData()`。
- **成功**：只更新金价（HERO 大数字 + TICKER 两处）与「当前报盘 · SPOT (2026-11-15)」里的日期；
  日期变化本身就是唯一反馈，**不显示任何结果文字、按钮不改为「已刷新」**。
- **失败**：不更新日期、不改价格、不提示；按钮恢复可用即可。
- 获取过程中按钮文字为 `⟳ 获取中…`，结束后恢复 `⟳ 刷新实时金价`。
- `setMode()` / `#dbHint` / `✓ 已刷新` / `✗ 获取失败` 已全部删除；
  `location.protocol==='file:'` 时按钮仍禁用（需本地服务器）；`id="refreshBtn"` 不变。

### 10.3 校验与回滚

- `tools/test_refresh_button.js`：状态条与提示元素清零 / 无结果提示文案 / 按钮在 HERO 右上角 /
  模拟成功 → `spot=tickerXau=$3,888` 且 `spotAsOf=当天` 并验证 `applyData` 写回 SPOT 标签 /
  模拟无 price 与 fetch reject 两种失败 → 日期与价格均不变、静默恢复 / `file://` 禁用 / div 平衡。
- 全量 **11/11 PASS**；`build_html.py` 重建幂等；HTTP 200；headless Chrome 截图确认按钮在右上角、
  原状态条消失、标题与按钮不重叠。
- 回滚：`~/.Trash/gold-terminal-before-refresh-move-20261115-143033.html`。

> 说明：按钮仍只更新 `spot` / `tickerXau` 两个字段（3 处显示），不写回 xlsx，
> `tickerXauChg` / `asOf` / 时间轴末点等仍为构建期快照——见第 9 轮答疑，未在本轮范围内修改。

### 10.4 修订：删除结果提示，改用日期反馈（2026-11-15 14:38）

用户要求：点击后不再显示「已通过 https://api.gold-api.com/price/XAU 获取最新现货价。」这类结果信息；
刷新成功把当天日期写进「当前报盘 · SPOT (…)」，失败不更新也不提示。

| 动作 | 内容 |
| --- | --- |
| 删除 | `#dbHint` 元素、`.hero .rf-hint` 两条 CSS、`setMode()` 整个函数、按钮 `✓ 已刷新` / `✗ 获取失败` 文字与 setTimeout 恢复逻辑 |
| 删除 | EVENT 按钮 IIFE 里对 `dbHint` 的「候选 i/N」提示写入；事件条内容切换本身即为反馈 |
| 新增 | `todayStr()`（`YYYY-MM-DD`）；成功时 `D.spotAsOf=todayStr()`，由 `applyData()` 回填到 `data-field="spotAsOf"` |
| 失败 | `btn.disabled=false; btn.textContent=BTN_LABEL;`，不写任何字段、不显示任何提示 |

⚠️ `spotAsOf` 是**内存态**：刷新页面会回到 xlsx 快照 `2026-08`；如需持久，须跑
`fetch_gold_data.py --spot && build_html.py`（并把 `spotAsOf` 写回「行情快照」sheet）。

校验：全量 11/11 PASS；`build_html.py` 重建幂等；HTTP 200。
备份：`~/.Trash/gold-terminal-before-no-hint-20261115-143848.html`。

---

## 十一、价格时间轴改用 A1 历史趋势图 + 修复误删样式（2026-11-15 15:08）

用户：「价格时间轴实现这部分和后面 A1 历史周期定位基本一样，把 A1 历史周期定位这块直接覆盖到
价格时间轴里，后面 A1 先不删除」。

### 11.1 覆盖内容
- 删除「价格时间轴」原区块（2,829 字符）：`spot_price_timeline` 标题 / 4 锚点 SVG
  （`$4,000 破位 / $5,590 ATH / $3,959 低点 / $4,379 快照`）/ `<g id="tl-dyn">`。
- 原位放入与 A1 完全相同的 `hist-wrap`：标题「1970–2026 黄金年均价（USD/oz）」、
  对数轴/线性轴按钮、空 `<svg class="hist-chart">`、口径脚注。
- panel 头改为 `CHART / gold_annual_price_history / 世界银行 Pink Sheet · 1970–2026`；
  页脚 SOURCE 文案同步（原写「示意走势，关键节点均为真实数据」，已不适用）。
- **A1 原图与其 `.ti` 卡片完全保留**，页面现有 **2 张** `hist-chart`（时间轴 1 + A1 1）。
  `renderHist()` 用 `querySelectorAll('.hist-chart')` 遍历渲染，两张都出图；
  `.hist-btn` 也是遍历，任一组按钮切换会同步两张图的对数/线性状态。
- 原 `drawTimeline()` IIFE、`GOLD_PANEL_DATA.timeline`、`价格时间轴` sheet、`read_timeline()`
  当时暂时保留；**已于 2026-11-15 15:28 全部清理**（见第十二节）。

### 11.2 ⚠️ 同时修复了上一轮引入的回归
14:30 删「数据状态条」CSS 时，用 `css_start → css_end` 整段替换，把夹在中间的
**「通用面板」基础样式一起删掉了**（752 字符）：
`.panel` / `.panel > .ph{display:flex;gap:10px}` / `.ph .tag/.tt/.meta` / `.pb{padding}` /
`.grid{display:grid}` / `.wrap{max-width:1360px;margin:0 auto}`。
后果：所有 panel 头部文字挤成一行、卡片无边框、页面失去 1360px 居中。
本轮从 `~/.Trash/gold-terminal-before-refresh-move-20261115-143033.html` 恢复该段
（值已是白底适配版），插回 `/* ===== HERO ===== */` 之前。截图复核布局恢复正常。

> 教训：删除 CSS 段落时不要用「注释 A → 注释 B」的粗边界，必须确认中间没有其它板块；
> 或者只删精确的规则字符串。

### 11.3 校验
- `tools/verify_render.js`：stub 现提供 2 个 `.hist-chart` 元素，targets 由 `tl-dyn` 改为
  `histChartTop` / `histChartA1`，两者均渲染出 7 circle / 6 rect / 3 path / 7 line。
- `tools/test_template_single.js`：历史图数量断言 1 → 2，并新增「时间轴区块内是 hist-chart、
  A1 原图仍在」两条断言。
- 全量 **11/11 PASS**；`build_html.py` 重建幂等；HTTP 200；Chrome 截图确认布局。
- 备份：`~/.Trash/gold-terminal-before-hist-overwrite-20261115-150835.html`。

---

## 十二、清理失效时间轴数据 + 历史图只保留 Pink Sheet 年均价（2026-11-15 15:28）

### 12.1 清理清单
| 位置 | 删除内容 |
| --- | --- |
| `data/gold_data.xlsx` | 「价格时间轴」sheet（4 行 4 列）→ 现为 **11 个 sheet** |
| `src/schema.py` | `SHEET_TIMELINE` / `HEAD_TIMELINE` / `SEED_TIMELINE`；docstring 的 sheet 清单改为 11 个 |
| `src/excelio.py` | `read_timeline()` / `_parse_money()` / 两处 `ensure_workbook` 条目 / 不再使用的 `import re` |
| `src/build_html.py` | `timeline` 读取、`GOLD_PANEL_DATA.timeline` 注入、return 元组、main 解包、预览打印 |
| `output/gold-terminal.html` | `drawTimeline()` 整个 IIFE（2,369 字符） |
| `tools/` | 4 个 audit 脚本里失效的 `tl-dyn` DOM stub |

⚠️ 清理 `read_timeline` 时一度把夹在中间的 `_f()` 辅助函数一起删掉（`NameError`），
已恢复。**同前文教训：删函数段不要用 `def A → def B` 的粗边界。**

### 12.2 历史年均价图移除 2026 项目快照
两张 `hist-chart`（价格时间轴 + A1）现在**只画 Pink Sheet 年均价 1970–2025**：

| 删除/修改 | 内容 |
| --- | --- |
| 删除 | `HIST_MARK` 的 `2026-01 峰值 5,590`、`hline2` 虚线延伸、`hnow` 圆点、`2026 当前 4,379` 文字 |
| 删除 | `.hline2` / `.hnow` 两条死 CSS |
| 修改 | `HIST_BAND` 末段 `[2020,2026.2]` → `[2020,2025]`；`x1=2026.2` → `2025`；X 轴末标签 `2026` → `2025` |
| 文案 | 两处标题 `1970–2026` → `1970–2025`；两处口径脚注删去「2026 为项目快照…非年均价」；sec-title / panel meta / 页脚 SOURCE / JS 注释同步 |
| 保留 | `HIST` 56 个年均价（1970=36 … 2025=3442，未改）；5 个历史盘中极值标记（1980/1999/2011/2015/2020，脚注已注明「非年均」）；Y 轴上限 6000（对数轴刻度含 5000，为极值标记预留） |

> 若要连历史极值标记也去掉、或把 Y 轴收紧到 4000，需同步改 `yt` 刻度数组与线性轴分母，
> 本轮未改。

### 12.3 校验
- `test_template_single.js`：新增 11 条断言（`drawTimeline` / `tl-dyn` / `hline2` / `hnow` /
  `2026 当前` / `2026.05` / `2026.2` / `2026 为项目快照` / `"timeline"` 全部清零、两处 1970–2025 标题、
  X 轴与阶段带末点为 2025）；**完整版区块哈希基线刷新**为
  `3154911ccdba9df3bbbe6f18e79f698603f2c199b11478661218b201ddc73360`
  （A1 文案经用户授权修改，基线随之更新）。
- `test_light_theme.js`：删掉失效的 `.hnow` 断言，改断言 `.hline` / `.hpeak` 白底深金。
- **全量 11/11 PASS**；`py_compile src/*.py` OK；`build_html.py` 连跑两次幂等（`"timeline"` 保持 0）；
  xlsx 11 sheet、无「价格时间轴」；HTTP 200；Chrome 截图确认图上无 2026 元素、曲线止于 2025。
- 备份：`~/.Trash/gold_data-before-timeline-clean-*.xlsx`、
  `~/.Trash/gold-terminal-before-2026-clean-*.html`。

---

## 十三、当前报盘卡片 · 当年月度金价小图（2026-11-15 16:09）

用户：基于 **Commodity Price Data（Pink Sheet）月度黄金参考价**做一张小的当年月度金价趋势图，
替换「当前报盘」大数字下面那两行文字。

### 13.1 数据源与口径
- 官方：World Bank Commodity Price Data (Pink Sheet) →
  `CMO-Historical-Data-Monthly.xlsx` → `Monthly Prices` sheet → **`Gold` 列（第 70 列）**，
  单位 `$/troy oz`，表更新于 2026-11-03。
- 口径（该文件 Description sheet）：`Gold, spot average of daily rates, from June 2025;
  previously (UK), 99.5% fine, London afternoon fixing, average of daily rates`
  → **日均价按月平均**，与实时现货价（gold-api）、年均价（Pink Sheet Annual）**均非同一口径**，
  卡片脚注已明确标注。
- 当年 2026 共 10 个月（1–10 月）：`4753 / 5020 / 4856 / 4721 / 4587 / 4228 / 4073 / 4411 / 4319 / 4105`。
  ⚠️ 这些是月度均价，与页面 `spot $4,379` 快照/刷新值 `$3,888` 不可直接比较。

### 13.2 管线（沿用三段式单向流）
```
CMO-Historical-Data-Monthly.xlsx（缓存 data/cmo_monthly_prices.xlsx）
        ↓ src/fetch_gold_monthly.py（找 Gold 列 → 取最新有值年份的全部月份）
data/gold_data.xlsx「黄金月度均价」sheet（12 个 sheet）
        ↓ src/build_html.py
GOLD_PANEL_DATA.goldMonthly
        ↓ 空 <svg id="goldMonthlyChart"> + IIFE
当前报盘卡片内的小图（折线 + 面积 + 每月圆点 + 月份轴 + 末月值徽章）
```
- 新增 `src/fetch_gold_monthly.py`，支持 `--dry-run` / `--force`（重下）/ `--file PATH`（离线）。
  年份**自动取最新有值年份**，跨年无需改代码。
- `config.py` 加 `CMO_MONTHLY_URL` / `CMO_MONTHLY_CACHE`；
  `schema.py` / `excelio.py` / `build_html.py` 各加一组常量、读写与注入。

### 13.3 页面改动
- 删除右侧 cell 的两行静态文字：`▲ 自 6 月低点 +8.6% · 8 月初回升至 $4,300 区间`、
  `上半年受「加息交易」与实际利率上行压制；<eventDate> 单日 <eventPct>，<eventText>。`
  → 替换为 `.spot-trend` 容器（标题 + 末月值徽章 + 空 SVG + 口径脚注）。
- 事件信息**未丢**：eventbar 仍绑定 `eventDate / eventText / eventSource / eventPct`。
- `reboundFromLow` 字段在页面已无绑定（xlsx 仍保留，未清理）；
  失效的 `.hero .chg` / `.chg.up` CSS 一并删除。
- 小图 `viewBox 460×108`，白底浅灰容器、深金主线 `rgba(154,107,0,.12)` 面积、
  白心深金圆点；X 轴隔月标注避免拥挤；空数据兜底显示「暂无月度数据 · 请跑 fetch_gold_monthly.py」。

### 13.4 校验
- 新增 `tools/test_gold_monthly.js`：数据块 10 个月同年份/升序/数值合法、旧文字已删、
  空 SVG 容器、口径标注、DOM-stub 实跑（10 点折线/10 圆点/月份标签/2026 标题/`$4,105` 徽章）、
  空数据兜底。
  ⚠️ stub 遍历脚本必须用精确 `<script>` 正则；用 `<script[^>]*>` 会把 `<script id="gold-panel-data">`
  数据块再执行一遍，覆盖掉「已删 goldMonthly」的自定义数据，空态永远测不到。
- `test_event_bar.js` 删掉失效的 HERO note 断言，改断言旧两行已删、eventText 仅剩 eventbar 一处。
- `verify_render.js` targets 加入 `goldMonthlyChart`。
- **全量 12/12 PASS**；`py_compile` OK；build_html 幂等；xlsx 12 sheet；HTTP 200；
  Chrome 截图确认两行文字消失、小图清晰、与刷新按钮/EVENT 条无重叠。
- 备份：`~/.Trash/gold_data-before-monthly-*.xlsx`、`~/.Trash/gold-terminal-before-monthly-*.html`。

### 13.5 小图视觉精简（2026-11-15 17:05）

用户五点微调，均已落地：

| 要求 | 处理 |
| --- | --- |
| 删口径注释行 | 删除 `.st-foot` 元素与其 CSS（年均价图的两处 `.hist-foot` 口径**未动**） |
| 删「5162 年度最大值」 | 删除 IIFE 里 `Math.round(mx)` 的 Y 轴上限文字；`mx/pad` 计算保留（用于折线缩放） |
| 删标题行「2026 年月度金价 · Pink Sheet（USD/oz）$4,105」 | 删除 `.st-head` 容器（`gmTitle` / `gmLast`）、CSS，以及 IIFE 里对 cap/val 的引用与写入 |
| 图尽量小 | `viewBox 460×108 → 460×80`；`PL=26, PR=10, PT=8, PB=16`；容器 padding `7px 9px 6px → 3px 6px`；标签字号 9 → 8.5px |
| 左侧竖排「2026月度」 | IIFE 里按字符逐个生成 `<text class="gm-vlabel">`，x 固定在 `PL-15`，y 在绘图区内均分；文案为 `年份（动态取 goldMonthly[0]）+ '月度'`，跨年自动变 |

- 图内折线末端的 `$4,105` 标签**保留**（删掉标题行后它是唯一数值标注，不再重复）。
- `__goldMonthlyStat` 仍含 `points / year / last / empty`，校验脚本不受影响。
- `tools/test_gold_monthly.js` 更新：断言 `gmTitle / gmLast / st-head / st-foot / Math.round(mx) / 口径行` 全部清零、
  `viewBox 460×80`、竖排 6 字符等于「年份+月度」、无 `5xxx` 类 Y 轴数字。
  ⚠️ 断言关键字要用精确串：`hist-cap` / `hist-foot` 含 `st-cap` / `st-foot` 子串，粗匹配会误报残留。
- **全量 12/12 PASS**；build_html 幂等；HTTP 200；截图确认五项到位、布局协调。
- 备份：`~/.Trash/gold-terminal-before-spark-tune-*.html`。

### 13.6 小图去边框 + 历史高点文字动态化（2026-11-15 17:30）

用户两点：① 月度金价小图不要边框，直接融入当前报盘卡片下半区；
② HERO「历史高点」那段静态文字（首次破 4,000 / 6-24 盘中低 3,959 / 回落 26%）要改成动态。

#### 需求①：小图去边框
`.hero .spot-trend` 的 `border / background / padding` 去掉（`border:0;background:transparent;padding:0;margin-top:6px`），图直接贴在「当前报盘」大数字下方。

#### 需求②：三锚动态描述（关键逻辑判断）
**用户原意「用最新日期价 + 最新月份价替换静态文字」不可直接照做**：那段里的 4,000 / 3,959 / 26% 都是已发生的历史事实，用实时价替换等于篡改历史；且现货价（刷新口径）、月均价（Pink Sheet）、盘中极值三种口径混说会误导。用户反例很准——$3,888 已低于 6-24 的 3,959，静态低点必然过时。
**硬约束**：数据层无全量日线，无法自动识别「新的盘中最低在哪天/多少」。
**方案（用户选「删低点留三锚」）**：把 note 改为 `#athNote`，由 `renderAthNote()` 用数据拼装：
`历史高点 <b>{D.ath}</b>（{athDate 月-日} 盘中）；当前 <b>{D.spot}</b>，较 ATH 回落 <b>{(ath−spot)/ath}</b>；最新月均 <b>{goldMonthly[-1].price}</b>（{末条月}月）。`
- 锚1 历史高点 + 日期来自 `GOLD_DATA`（静态历史事实，语义稳定）；
- 锚2 当前价来自 `D.spot`（刷新按钮会改）、回落% 由 `(ath−spot)/ath×100` 动态算（>0 显「回落」，<0 显「上涨」）；
- 锚3 最新月均取 `GOLD_PANEL_DATA.goldMonthly` 末条。
- **渲染函数挂进 `applyData()`**：刷新按钮改 `D.spot`、event 切换改 D 后都自动重算 → 价格跌破旧低点时文字自动更新，不再过时。
- 已删字段 `first4k / lowValue / lowDrop`（xlsx 与 GOLD_DATA 数据块里仍保留，页面不再绑定，同 `reboundFromLow` 处理）；
  分析正文第 608/622 行的同类字样属文章段落，**保留未动**。

#### 校验
- 新增 `tools/test_ath_note.js`：静态字段清零、DOM-stub 实跑三锚（21.7% 计算）、刷新联动（改 spot=3,888 → 回落 30.4%、不再出现 3,959）、空 goldMonthly 兜底。
  ⚠️ DOM stub 仍需 `viewBox` getter（别的内联脚本访问 `viewBox.baseVal`）。
- **全量 13/13 PASS**；build_html 幂等（186,219 字符）；HTTP 200；Chrome 截图确认文字与去边框效果。
- 备份：`~/.Trash/gold-terminal-before-noborder-*.html`、`~/.Trash/gold-terminal-before-athnote-*.html`。

### 13.7 EVENT 条移除涨跌幅显示 + 构建期脚本定时化（2026-11-15 18:20）

用户：「−0.40% 这块那天的金价涨跌不需要，直接删掉。event 构建期脚本定时跑。」

#### ① 移除页面涨跌幅显示
| 位置 | 处理 |
| --- | --- |
| HTML | 删 `.evpct` span（`data-field="eventPct"`） |
| CSS | 删 `.eventbar .evpct` 行；`.evdate` 由 `var(--up)` → `var(--txt-dim)`（不再按涨跌上色） |
| JS | 删 `tintEvent()` 函数 + 初始化调用 + `show()` 内调用；`show()` 不再写 `D.eventPct` |
| 数据层 | **保留** `GOLD_DATA.eventPct` 字段与 xlsx「黄金事件流」pct 列（供回溯，build_html 会重新注入，删了也会被重建） |

> ⚠️ 关键联动：`tintEvent()` 原本按 eventPct 正负给日期+百分比上色，删 pct 后必须一并删函数和两处调用，
> 否则 stub 实跑 `ReferenceError`；evdate 改为固定中性色。

#### ② 定时任务（automation）
- 新建 **「黄金 EVENT 条每日自动更新」**（id `46bd96fc-a1c0-4312-a004-985b8fe1f586`），
  `FREQ=DAILY;BYHOUR=8;BYMINUTE=0`，状态 ACTIVE，cwd = gold-analysis。
- prompt 自包含：跑 `fetch_event.py`（抓 RSS + GC=F 日线 → xlsx）→ 成功则跑 `build_html.py` 注入 HTML → 报告选中事件；
  无候选返回非 0 时不重建；不改 eventPct 显示逻辑、不 git push。
- 用户未指定时间，取默认每天 08:00（隔夜新闻 + 昨日日线收盘）；可按需调整。
- 创建前已 list 检查，无同类任务；试跑 `fetch_event.py --dry-run` 确认网络与脚本可用。

#### 校验
- `test_event_bar.js`：FIELDS 去掉 eventPct（改为 BACKFIELD 只校验数据块保留）、want 去掉 evpct、
  新增 5 条「页面无 evpct/tintEvent/样式、evdate 中性色」断言、删 eventPct 格式断言；EVENT 按钮切换逻辑仍全过。
- **全量 13/13 PASS**；`node --check` 全部内联脚本正常；build_html 幂等（185,537 字符）；HTTP 200；
  Chrome 截图确认右侧涨跌幅消失、日期中性色、其余元素布局正常。
- 备份：`~/.Trash/gold-terminal-before-evpct-del-*.html`。非 git，仅本地未推送（automation 为本机定时任务，非远程）。
