# 国际原油价格 · 五维度分析仪表盘

单文件 HTML 看板 + 一条可重跑的 ETL 流水线。看板围绕 **供给侧 / 需求侧 / 地缘政治 / 宏观金融 / 其他突发** 五个维度组织，代码与数据抓取按同样五个维度切分。

- 产物：`output/crude_oil_dashboard.html`（自包含，内嵌快照数据 + 本地 Chart.js）
- 本地预览：`python run.py serve` → <http://localhost:8000/>

---

## 快速开始

```bash
# 1) 日常刷新：抓线上数据 + 重新渲染（不需要任何第三方库）
python run.py build

# 2) 本地预览
python run.py serve

# 3) 仅当 data/raw 下新增了 <span style="color:#f97316">OPEC MOMR</span> 月报 PDF /
#                              OPEC WOO / IEA《Oil 20XX》/ EIA《AEO 20XX》长期展望 PDF / Baker Hughes Excel 时
python run.py extract    # 先重新解析离线文件
python run.py build
```

`run.py extract` 会自动挑一个**装了可选依赖、且同为 3.13.x** 的解释器来跑子进程，顺序是  
`$EXTRACT_PYTHON` → 项目内 `.venv/bin/python` → 当前解释器；三个都不带依赖时按缺依赖跳过。  
本机的 `.venv` 已软链到 `~/.workbuddy/binaries/python/envs/default`（Python 3.13.12，  
含 pdfplumber 0.11.10 / openpyxl 3.1.5）。换机器时重建：

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
# 或沿用已有的 venv：ln -s <venv 路径> .venv
```

> **Python 版本必须是 3.13.x。** 3.12+ 的 `sum()` 使用 Neumaier 补偿求和，而 3.13 与 3.14 对「int 混入 float 列表」的处理不一致，会让 `composite` 序列末位浮点数字漂移，产物 HTML 无法字节复现。仓库内已放 `.python-version`。

> **`pdfplumber` / `openpyxl` 是可选依赖**，只在 `run.py extract` 重新解析离线 PDF/Excel 时才需要（见 `src/common/deps.py`）。缺失时对应脚本会打印安装指引并以退出码 3 跳过，`run.py extract` 把它记为「跳过」而非失败，其余解析脚本与 `build` 链路照常运行。

---

## 目录结构

```
.
├── run.py              统一入口（extract / dataset / html / build / all / serve）
├── Makefile            常用命令的一层薄封装
├── requirements.txt    pdfplumber（PDF）+ openpyxl（Excel）
├── calendar/           财经发布日程 .ics 生成（make_ics.py 读官方 publishing schedule）
│   ├── make_ics.py     OPEC / EIA / IEA 三类发布的 UTC 事件生成（含巴黎 10H00 口径）
│   └── finance_calendar.ics  产物（finance_calendar / EIA 周报 / IEA 月报共 19 条）
│
├── src/                代码，按「公共层 / 五维抓取 / 打分 / 流水线」分层
│   ├── paths.py        全项目唯一路径定义（其余模块不得再写 HERE/dirname）
│   ├── config.py       API 凭据（env 优先）与阈值常量
│   ├── dataio.py       data/dataset/ 的域文件读写（GROUPS 决定字段顺序）
│   ├── common/
│   │   ├── http.py     FRED / EIA / Yahoo 抓取，失败返回空而不抛错
│   │   ├── series.py   对齐、收益率、滚动波动率、z-score、相关系数
│   │   └── deps.py     可选依赖（pdfplumber / openpyxl / pymupdf）的按需收口
│   ├── extract/        从 data/raw 原文件反查长期展望的提取器
│   │   ├── eia_aeo.py  EIA《AEO 20XX》Narrative Figures xlsx 逐年原值 → eiaAeoCons*
│   │   ├── eia_steo_price.py  EIA《STEO》各期 PDF 表 2 油价（Brent/WTI）→ eiaSteoPrice*（outlook8）
│   │   └── iea_oil.py  IEA《Oil 20XX》Total products 行 → ieaOutlook20XX*
│   ├── fetch/          按维度组织的抓取模块
│   │   ├── prices.py           价格基准（定义日度日期轴，被多维度共用）
│   │   ├── supply/             EIA 周报、OPEC 剩余产能/年度产量/月度产量、
│   │   │                       OECD 库存、美国 SPR、全球钻井数
│   │   ├── demand/             PMI + IMF《WEO》GDP 预期（WOE_VINTAGES）与油价基准假设（WOE_OIL_VINTAGES）两套期次矩阵、
│   │   │                       炼厂开工率、中国加工量/进口量
│   │   ├── geo/                OVX（Yahoo ^OVX）
│   │   ├── macro/              美元指数、联邦基金利率、10Y 国债
│   │   ├── shocks/             跳变事件与已实现波动率
│   │   └── news/
│   │       ├── argus.py        原油快讯整页完整抓取 → news.json 的 crudeNews（优先无头浏览器通道，回落 urllib + WAF 探测）
│   │       └── __init__.py
│   ├── tools/
│   │   └── fetch_argus_news.cjs  Node 无头浏览器渲染脚本（playwright-core + chromium-1217，绕过 AWS WAF）
│   ├── score/
│   │   ├── dims.py     五维压力分模型（0–100）与综合分
│   │   └── geo.py      地缘恐慌指数 I_geo（0–4），渲染期计算
│   ├── pipeline/
│   │   ├── build_dataset.py    ETL 编排：抓取 → 派生 → 打分 → 汇总 → 注入
│   │   └── build_html.py       渲染单文件 HTML
│   └── serve.py        本地服务器（含 FRED/EIA 反向代理，绕过 CORS）
│
├── data/
│   ├── raw/            原始下载件（MOMR / OMR / STEO / WOO /《Oil 20XX》/《AEO 20XX》PDF · AEO Narrative Figures xlsx、Rig Count Excel、中国原油 xlsx、制造业 PMI xlsx）—— 不可再生，务必保留；文件名不要手工改（管线按文件名解析期号）
│   ├── processed/      各抓取器解析后的中间产物，可由 raw 完全重算
│   └── dataset/        合并后的域数据，按主题分文件 —— build_html 的唯一输入
│       └── news.json   原油快讯（crudeNews + crudeNewsMeta），半手工域，baseDate=2026-10-14
│
├── assets/vendor/      前端库原件（Chart.js + ECharts），构建时复制到 output/vendor/
└── output/             发布产物（单文件 HTML + vendor），全部可重建，已 gitignore
```

---

## 数据流

pdfplumber

`build_dataset.py` 的六步（顺序不可随意调整）：

1. **价格基准** — Brent / WTI / 汽油价，并由此确定**日度日期轴**
2. **跨维派生** — 收益率、20 日年化波动率、裂解价差、BW 价差（其余四维都要引用）
3. **各维度抓取** — 供给侧 / 地缘 / 宏观 / 突发，各产出本维度序列与预警
4. **压力分** — `src/score/dims.py` 统一计算五维 0–100 与综合分
5. **汇总** — 预警合并、相关系数矩阵、KPI
6. **离线注入** — 读 `data/processed/*.json`，拼上无 API 的离线数据

---

## 五维度口径

| 维度         | 压力分来源              | 主要数据源                                                                                                         |
| ---------- | ------------------ | ------------------------------------------------------------------------------------------------------------- |
| 供给侧 supply | 裂解价差 z-score × 16  | EIA 周报（库存/产量/开工率）、<span style="color:rgb(248, 136, 37)">OPEC MOMR</span> 表 5-7、EIA STEO 剩余产能、Baker Hughes 钻井数 |
| 需求侧 demand | 汽油价 z-score × 13   | EIA 成品油供应量、制造业 PMI（中美欧）、IMF WEO GDP 预期、中国加工量/进口量                                                              |
| 地缘政治 geo   | 渲染期由 I_geo（0–4）归一化 | Yahoo ^OVX、Brent−WTI 价差、OPEC 剩余产能                                                                             |
| 宏观金融 macro | 美元指数 z-score × 17  | FRED：DTWEXBGS、DFF、DGS10（DFF 仅上图不入分：政策利率为阶梯序列，z-score 会退化）                                                     |
| 其他突发 other | 近 20 日跳变次数 × 26    | Brent 单日收益率、20 日年化波动率                                                                                         |

**I_geo（0–4）** = OVX 分项（>45 记 2，35–45 记 1）+ BW 价差分项（>7 记 1）+ 剩余产能分项（<2 Mb/d 记 1）。在渲染期计算并注入 SNAPSHOT，不落库——若日后改到 ETL 期落库，需把 `igeo` / `igeoBreak` 加进 `dataio.GROUPS`。

---

## 供给侧 / 需求侧 数据指标与数据源明细

> EIA 周度序列统一由 `src/fetch/supply/eia_weekly.py` 抓取，其余来自 <span style="color:rgb(248, 136, 37)">OPEC MOMR</span> PDF 提取、EIA STEO API、Baker Hughes Excel 或手工维护。
>
> 两份报告统计的都是**截至上周五**的那一周数据。 **遇到美国联邦假日会顺延，**&#x5F53;周的周一若是假日，EIA 周报通常延到周四同一时间，API 也跟着往后挪一天。确切日期以 EIA 官方公告的发布日程为准，市场以 EIA 为基准，API 只当提前一天的参考。
>
> | 报告     | 发布机构    | 美东时间     | UTC+8（夏令/冬令）     | 类型          |
> | ------ | ------- | -------- | ---------------- | ----------- |
> | API 周报 | 美国石油协会  | 周二 16:30 | 周三 04:30 / 05:30 | 民间调查，会员自愿提报 |
> | EIA 周报 | 美国能源资讯署 | 周三 10:30 | 周三 22:30 / 23:30 | 官方统计，法定强制申报 |

### 供给侧

维度 KPI 芯片另含：库欣库存 / 全美库存 / 美国产量 / 开工率 / OECD 原油库存 / 美国 SPR / OPEC 剩余产能。

| 指标                         | 单位 / 频率  | 原始数据源（序列号）                                                                                                                                                                                  | 抓取 / 维护脚本                         | 看板位置                                                                                                                                                                                                                                                                                                                    |
| -------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 美国原油产量                     | 百万桶/日，周度 | <span style="color:rgb(222, 60, 54)">EIA 周度石油周报</span> `PET.WCRFPUS2.W`                                                                                                                     | `src/fetch/supply/eia_weekly.py`  | 图表·产量与产能 / KPI「美国产量」                                                                                                                                                                                                                                                                                                    |
| OPEC 原油产量                  | 百万桶/日，月度 | EIA 短期能源展望（STEO）**API** `COPR_OPEC` ＋ OPEC 11 国分项 `COPR_SA/IZ/IR/KU/VE/NI/LY/AG/CF/EK/GB`（2026-10-16 起走 API；2026-10-11 换源为 STEO 表 3d 11 国，原为 <span style="color:rgb(248, 136, 37)">OPEC MOMR</span> 表 5-7 的 12 国口径，差阿联酋）                                                                                      | `src/fetch/supply/steo_monthly.py` | 图表·产量与产能                                                                                                                                                                                                                                                                                                                |
| OPEC 有效剩余产能                | 百万桶/日，月度 | EIA 短期能源展望（STEO）`COPS_OPEC_R05`（2026-03 起剩余产能实际降至 0，2027-04 起预测回升至 2.35）                                                                                                                    | `src/fetch/supply/opec_spare.py`  | 图表·OPEC 剩余产能缓冲（<b>柱状图</b>，蓝柱=实际值 / 橙柱=EIA 预测段）                                                                                                                                                                                                                                                                          |
| 库欣原油库存                     | 百万桶，周度   | <span style="color:rgb(222, 60, 54)">EIA 周度石油周报</span> `PET.W_EPC0_SAX_YCUOK_MBBL.W`（Cushing, OK Ending Stocks excluding SPR，约 22–30 百万桶）                                                                                                                     | `src/fetch/supply/eia_weekly.py`  | 库存NYMEX WTI 原油期货的实物交割地，反应的是 WTI 这张合约本身的交割状况。当库欣的储槽接近装满，卖方的交割压力会上升；反之，可交割的实物变少，近月合约容易被推高。<br />库存数据有相当固定的季节性倾向<br />**春季（约 2 至 4 月）**：炼油厂春季岁修，开工率下降，原油库存倾向上升。<br />**夏季（约 5 月底至 9 月初）**：美国的开车旺季，汽油需求上升，炼油厂开工率拉到全年高点，原油库存倾向下降。<br />**秋季（约 9 至 10 月）**：第二轮岁修，开工率再度下滑，原油库存倾向上升。<br />**冬季**：取暖需求推升馏分油的消耗，寒流会让柴油与取暖油库存快速下降。 |
| 全美商业原油库存                   | 百万桶，周度   | <span style="color:rgb(222, 60, 54)">EIA 周度石油周报</span> `PET.WCESTUS1.W`（U.S. Ending Stocks <b>excluding SPR</b>，约 425–430 百万桶）                                                                                                                     | `src/fetch/supply/eia_weekly.py`  | 全美商业库存反映整体供需，库存下降，可能是炼厂开工率提高了，原油加工量增加；也可能是进口减少；还可能是出口增加。                                                                                                                                                                                                                                                                |
| OECD 商业库存（原油 / 成品油）        | 百万桶，月度   | <span style="color:rgb(248, 136, 37)">OPEC MOMR</span> 表 9-1（IEA 编制、OPEC 转引）的 **Crude oil** 与 **Products** 两行：商业原油库存约 1,285–1,392、成品油库存（含石化产品）约 1,400–1,536（2023-09~2026-08，36 期，量级接近故同轴对照） | `src/fetch/supply/oecd_stocks.py` | 图表·库存指标「OECD 商业库存：原油 / 成品油」/ KPI「OECD 原油库存」                                                                                                                                                                                                                                                                             |
| 美国战略石油储备 （SPR）             | 百万桶，月度   | <span style="color:rgb(222, 60, 54)">EIA 周度石油周报</span> `PET.WCSSTUS1.W`（2026-10-07 换源，原为 <span style="color:rgb(248, 136, 37)">OPEC MOMR</span> 表 9-2，现仅作兜底）                                                                                                                                | `src/fetch/supply/us_spr.py`      | 定义：<span style="color:rgb(133, 133, 133)">是美国政府在国家安全和紧急情况下使用的石油储备，以应对突发事件，如石油供应中断或国际油价飙升。</span>                                                                                                                                                                                                                        |
| 全球旋转钻井平台数（World Rig Count） | 台，月度     | Baker Hughes Worldwide Rig Count Excel（<b>需手动下载</b>：官网 `rigcount.bakerhughes.com/intl-rig-count` 有 Akamai 403，脚本自动发现失败后会回退解析 `data/raw/rig_count/` 下最新期次的本地 xlsx）                           | `src/fetch/supply/rig_count.py`   | 图表·前瞻性指标。<br />⚠️ <b>口径断裂</b>：2024-01 起明细并入沙特 **Operating Rigs**（约 +263 台），官方 Worldwide = Active + Operating；此前仅 Active 口径，故 2023-12 = 1,739 → 2024-01 = 2,002（+15%）为口径台阶而非真实跳升，<b>前后两段不可直接比较</b>。图上已在 2024-01 处加「口径调整」竖线标注。                                                                                            |


| 美国炼厂开工率                    | %，周度最新   | <span style="color:rgb(222, 60, 54)">EIA 周度石油周报</span> `PET.WPULEUS3.W` | `src/fetch/supply/eia_weekly.py`  | 维度 KPI「开工率」（供给侧顶部）                                                                                                                                                                                                                                                                                                      |


### 需求侧

维度 KPI 芯片另含：裂解价差 / 汽油库存 / 美开工率 / 美PMI(ISM) / 全球GDP预期 / 美国汽油供应 / 中国原油进口。

| 指标                                         | 单位 / 频率        | 原始数据源（序列号）                                                                                                                                                                                                                                                                                                                                                 | 抓取 / 维护脚本                                                                                                                        | 看板位置                                                                                                                                                                                   |
| ------------------------------------------ | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 制造业 PMI（中 / 美 / 欧）                         | %，月度           | 美国 ISM / 中国国家统计局 / 欧元区 HCOB（S\&P Global），手工维护（`pmi_manufacturing.xlsx`）                                                                                                                                                                                                                                                                                    | `src/fetch/demand/pmi_gdp.py`                                                                                                    | 图表·宏观先行指标 / KPI「美PMI(ISM)」                                                                                                                                                             |
| 全球 GDP 增速预期                                | %，年度           | IMF《世界经济展望》（WEO，一年四期 1/4/7/10 月）。2026-10-13 起唯一事实源改为 **WOE_VINTAGES 期次矩阵**（**硬编码在脚本内，非 xlsx**）：2026 年四期对 2026/2027 的预测分别为 3.3/3.2（1月）、3.1/3.2（4月）、3.0/3.4（7月）、3.1/3.4（10月）；由它派生 gdp_expectation.json（最新期次快照，供 KPI）与 imf_woe.json（期次面板，供逐期修正图），页尾期次文案也由数据派生，不再另写一遍                                                                                                                                                                                                                                                                                                          | `src/fetch/demand/pmi_gdp.py`                                                                                                    | 图表·宏观先行指标 / KPI「全球GDP预期」                                                                                                                                                               |
| 裂解价差（Crack Spread）                         | $/bbl，月度均值     | EIA 美国常规汽油零售价 × 42 − WTI 实时价派生                                                                                                                                                                                                                                                                                                                             | `build_html.py` 渲染期计算（无独立脚本）                                                                                                     | **定义：**&#x70BC;油厂将原油加工为汽油、柴油等成品油后，成品油价格与原油价格之间的价差，反映炼油业者的毛利空间，并反映市场对成品油需求与供给的预期。<br />市场上最常用的裂解价差组合是「3-2-1 裂解价差」，假设以 3 桶原油裂解成 2 桶汽油与 1 桶柴油。<br />裂解价差的快速扩大可能表示市场对成品油的需求增加，反之则可能指示需求减少。 |
| 美国炼厂开工率（月度均值）/ 中国原油加工量                     | %，周度均值 / 万吨，月度 | EIA `PET.WPULEUS3.W` 月度均值 + 中国国家统计局（cn_crude_import and processing.xlsx（sheet 中国原油加工量）手动）                                                                                                                                                                                                                                                                                           | `src/fetch/demand/refinery.py`                                                                                                   | 原油被投入加工的比例，检修季会明显下降                                                                                                                                                                    |
| 美国汽油成品油供应量                                 | 百万桶/日，周度       | <span style="color:rgb(222, 60, 54)">EIA 周度石油周报</span> `PET.WGFUPUS2.W`                                                                                                                                                                                                                                                                                    | `src/fetch/supply/eia_weekly.py`                                                                                                 | 图表·表观消费指标 / KPI「美国汽油供应」                                                                                                                                                                |
| 中国原油进口量                                    | 万吨/月，月度（分年度）   | 中国原油进口量（cn_crude_import and processing.xlsx（sheet 中国原油进口量）手动）                                                                                                                                                                                                                                                                                                                           | `src/fetch/demand/refinery.py`                                                                                                   | 图表·表观消费指标 / KPI「中国原油进口」                                                                                                                                                                |
| 美国汽油库存                                     | 百万桶，周度         | <span style="color:rgb(222, 60, 54)">EIA 周度石油周报</span> `PET.WGTSTUS1.W`                                                                                                                                                                                                                                                                                    | `src/fetch/supply/eia_weekly.py`                                                                                                 | 维度 KPI「汽油库存」（未单独成图）                                                                                                                                                                    |
| 美开工率                                       | %，月度均值         | EIA `PET.WPULEUS3.W` 月度均值（同"美国炼厂开工率"序列）                                                                                                                                                                                                                                                                                                                    | `src/fetch/supply/eia_weekly.py`                                                                                                 | 维度 KPI「美开工率」（需求侧顶部）                                                                                                                                                                    |
| IEA 全球石油需求增速预测（逐月 OMR 修正）                  | 百万桶/日，年度同比增量   | IEA《Oil Market Report》各期 PDF（源文件原为 data/raw/iea_omr/，**2026-10-22 已清理出仓库**：该目录在 src/ 与 tools/ 中零引用，数值以下列手工维护文件为唯一事实源）：文末「Tables」章节的 **Table 2「Summary of Global Oil Demand」** 的 **World 行年度列**（⚠️ 不是 Table 1，Table 1 是「World Oil Supply and Demand」供需/库存总表；取两年年值相减得同比增量 Δ。最新 **10 月期（2026-10-14 发布）**：Δ2026 = **−2.62**、Δ2027 = **+2.0**（对应全球需求 2026 年 102.38、2027 年 104.38 mb/d；9 月期为 −2.5 / +2.6，即 2026 下调 120 kb/d、2027 下调 560 kb/d）。⚠️ 该页 Table 2 需订阅，10 月期数值取自报告 Highlights 正文「fall by 2.6 mb/d on average in 2026」「partial recovery of 2 mb/d」+ Argus 交叉校验（102.38 / 104.38），本地 `data/raw/iea_omr/` PDF 仅到 7 月期）                                                                                                                                 | 手工维护于 `data/dataset/iea_forecast.json`（`ieaOmr2026Demand` / `ieaOmr2027Demand`）；无独立 extract 脚本                                   | 图表·未来展望「IEA 全球石油需求增速预测（逐月 OMR 修正）」                                                                                                                                                     |
| OPEC 全球石油需求增速预测（逐月 MOMR 修正）                | 百万桶/日，年度同比增量   | OPEC《Monthly Oil Market Report》各期 PDF（源文件 data/raw/opec_momr/）：章节「World Oil Demand」的 **Table 4-1「World oil demand in 2026」/ Table 4-2「World oil demand in 2027」** 的 **Total World 行 Change 列**（表头 `2026/25`、`2027/26` 即同比增量；10 月期 0.18 与 2.55，见看板 0.2 / 2.6）                                                                                                | `原 opec_momr.py（已下线，口径见「已下线口径留档」）`（原解析脚本已于 2026-10-23 移出仓库，口径见「已下线口径留档」）+ 手工维护于 `data/dataset/opec_forecast.json`；无独立 extract 脚本        | 图表·未来展望「OPEC 全球石油需求增速预测（逐月 MOMR 修正）」                                                                                                                                                   |
| IEA《Oil 20XX》中期需求路径对比（至 2030）              | 百万桶/日，年度（多版次）  | IEA《Oil 2023 / 2024 / 2025》PDF（源文件 data/raw/iea_oil/）：各版「**Demand**」章的表「**Global / World oil demand by product**」（Oil 2023 表题为 Global、2024 起改 World）之 **Total products 行年度列**（⚠️ 同页另有一张「Growth in world oil demand by product」图，不含 Total products 行，勿取；各版按各自增长区间首年对齐到 2022–2030 窗口）                                                                        | `src/extract/iea_oil.py`（逐版扫描 PDF，可用 `--write` 回写）                                                                               | 图表·未来展望「IEA《Oil 20XX》中期需求路径对比（至 2030）」                                                                                                                                                 |
| OPEC《World Oil Outlook》长期需求路径对比（2025–2050） | 百万桶/日，年度（多版次）  | OPEC《World Oil Outlook 2023 / 2024 / 2025 / 2026》PDF（源文件 data/raw/opec_woo/）：第 3 章「**Demand**」的 **Table 3.2「Global oil demand by sector」** 之 **World 行年度列**（2026 版 2030–2050 = 113.3 / 119.0 / 121.7 / 123.1 / 124.1；⚠️ 旧版次 Table 3.2 表题不同——2023、2025 版为「Long-term oil demand by region」，2024 版为「Long-term oil demand in the Reference Case」，引用时需连同版次一起说明） | 手工维护于 `data/dataset/opec_forecast.json`（`opecWooDemand` / `opecWoo2025` / `opecWoo2024` / `opecWoo2023`）；无专用 extract 脚本          | 图表·未来展望「OPEC《World Oil Outlook》长期需求路径对比（2025–2050）」                                                                                                                                    |
| EIA 全球石油需求增速预测（逐月 STEO 修正）                 | 百万桶/日，年度同比增量   | EIA《Short-Term Energy Outlook》各期 PDF（源文件 data/raw/eia_steo/steo_jan26…sep26.pdf）：章节「Global Oil Markets」的 **Table 3e「World Petroleum and Other Liquid Fuels Consumption」** 的 **World total** 行年度列（2025 / 2026 / 2027 三年年值相减得同比增量 Δ；2026 年 −1.7、2027 年 +2.4，见 9 月期。注意口径是 Petroleum **and other liquid fuels**，含生物燃料等其他液体燃料，非纯原油）                             | 手工维护于 `data/dataset/eia_forecast.json`（`eiaSteo2026Demand` / `eiaSteo2027Demand`）；无独立 extract 脚本，逐期 PDF 由 `run.py html` 前的核对脚本复算 | 图表·未来展望「EIA 全球石油需求增速预测（逐月 STEO 修正）」                                                                                                                                                    |
| 美国液体燃料消费长期路径（至 2050）                       | 百万桶/日，年度（情景）   | EIA《AEO 2026》官方配套 `AEO2026_Narrative_Figures.xlsx`：sheet `14_RefinThruPut` 的 **U.S. total product supplied**（`PSD000:fa_Total`，11 情景，逐年原值）；图：淡扇面 = 宏观增长同一维度对称的高/低情形（High / Low Economic Growth），实线 = 基准 Counterfactual Baseline                                                                                                                            | `src/extract/eia_aeo.py` `--write`                                                                                               | 图表·未来展望「EIA《Annual Energy Outlook 2026》美国液体燃料消费路径（至 2050）」                                                                                                                             |
| IMF 油价基准假设（逐期 WEO 修正）                        | 美元/桶，年度（季度期次）  | IMF《World Economic Outlook》各期（源文件原为 data/raw/imf_weo/202601.pdf / 202604.pdf / 202607.pdf，**2026-10-22 已清理出仓库**：该目录零引用，油价面板的唯一事实源已是 pmi_gdp.py 的 `WOE_OIL_VINTAGES` 矩阵；**2025 辑四期无本地 PDF，取自官方发布报道 / WEO 数据库附录**）：「**全球假设**」中的石油价格基准值，口径 = **Brent / 迪拜法塔赫 / WTI 三品种简单平均**（⚠️ assumption 而非 forecast，由期货曲线推导；WEO 不做供需平衡）。**油价面板含 2025 辑 + 2026 辑共八期**：2025 辑四期对 2025/2026 的假设 = 69.76/67.96（1月）→ 66.94/62.38（4月）→ 68.18/64.33（7月）→ 68.92/65.84（10月）；2026 辑四期对 2026/2027 的假设 = 62.13/62.17（1月）→ 82.22/75.97（4月）→ 89.27/78.70（7月）→ **95.74/87.39**（10月）。⚠️ **按 WEO 辑（2025 / 2026）分组**，卡片右上角年份按钮切换各辑独立成图（2025 辑目标年 2025+2026、2026 辑目标年 2026+2027），2026 在 2025 辑为次年、2026 辑为当年，分属不同页面不撞线；2025 实际 **67.74** 作参考线 | 手工维护于 `src/fetch/demand/pmi_gdp.py` 的 `WOE_OIL_VINTAGES` 期次矩阵（**2025 四期 + 2026 四期；GDP 增速用独立 `WOE_VINTAGES` 矩阵，仅 2026 四期**，两套矩阵共用同一套期次轴）→ `data/processed/imf_woe_oil.json` → `data/dataset/imf_forecast.json` | 图表·未来展望「IMF 油价基准预测（逐期 WEO 修正）」 |
| EIA 油价基准预测（逐月 STEO 修正）                       | 美元/桶，年度（月度期次）  | EIA《Short-Term Energy Outlook》各期 PDF（源文件 data/raw/eia_steo/steo_jan26…oct26.pdf）数据表区 **Table 2「Energy Prices」** Crude Oil 段的 **Brent Spot Average** 行**年度列**（2025 / 2026 / 2027；⚠️ 同行的季度列 2025Q1–2027Q4 多数期次里已有历史值，读成"预测"会高估先见之明，故图只取年度列）。十期数值：2026 年 55.87 → 57.69 → 78.84 → 96.00 → 94.85 → 95.39 → 81.91 → 86.81 → 91.01 → **96.32**，2027 年 54.02 → 53.00 → 64.47 → 76.09 → 79.39 → 79.39 → 64.76 → 69.39 → 73.74 → **83.74**；2025 实际 **69.04** 作参考线 | `src/extract/eia_steo_price.py`（读 `data/raw/eia_steo/steo_*.pdf` 表 2）→ `data/processed/eia_steo_price.json` → `data/dataset/eia_forecast.json`（`eiaSteoPrice*`） | 图表·未来展望「EIA 油价基准预测（逐月 STEO 修正）」 |

> 注：美国炼厂开工率（`PET.WPULEUS3.W`）在供给侧 KPI 取**周度最新值**、在需求侧图表/KPI 取**月度均值**，属同源不同频；中国原油加工量/进口量、制造业 PMI 为手工录入（统计局 / 海关数值接口同源受限），统一维护在 `data/raw/` 的 xlsx 中。
>
> **手工维护数据（xlsx）与更新命令**
>
> | 数据                 | xlsx                                                             | 读取脚本                           | 更新命令                                  |
> | ------------------ | ---------------------------------------------------------------- | ------------------------------ | ------------------------------------- |
> | 制造业 PMI（中 / 美 / 欧） | `data/raw/pmi_manufacturing.xlsx`（sheet「制造业PMI」，2024-01~2026-08） | `src/fetch/demand/pmi_gdp.py`  | `python -m src.fetch.demand.pmi_gdp`  |
> | 中国原油加工量 / 进口量       | `data/raw/cn_crude_import and processing.xlsx`（sheet「中国原油加工量」/「中国原油进口量」） | `src/fetch/demand/refinery.py` | `python -m src.fetch.demand.refinery` |
>
> 改完 xlsx 后，需**先跑上表对应的 extract 命令**（把 xlsx 解析成 `data/processed/*.json`），再跑 `python run.py build` 渲染看板。**只跑 `run.py build` 不会刷新这三项** —— 它只重抓在线序列并合并已有的离线产物。xlsx 缺失或读取失败时，脚本会回退到内置的硬编码兜底序列。

### 未来展望

「未来展望」一个 tab 内按 **IEA / OPEC / EIA 三家 × 月度滚动 / 年度长期** 排成 6 张卡（左列月度、右列长期，<920px 回落单列），2026-10-14 起末尾追加第 4 组 **原油价格预测**（`grid2` 一行两图：outlook7 IMF + outlook8 EIA）。数据全部离线，不参与在线重抓。

> ⚠️ **油价预测全球只有 IMF 与 EIA 两家**（IEA OMR / OPEC MOMR / OPEC WOO 均只做需求预测，逐份 PDF 核实过），故第 4 组专收油价：
> - **outlook7（IMF）**：WEO「全球假设」中的油价基准值，口径 = Brent / Dubai Fateh / WTI **三品种简单平均**（由期货曲线推导的 **assumption**，非供需预测），**季度**频率（1/4/7/10 月四期）；
> - **outlook8（EIA）**：STEO 表 2 的 Brent 现货均价预测，**单一品种**口径，**月度**频率（本地 10 期 PDF）。
>
> 两家绝对值差 1~14 美元，**不可混线对照**，只比逐期修订路径（`eiaSteoPriceMeta.口径` 已写明）。

| 面板       | 报告                         | 序列键（`data/dataset/`）                                                                                           | 页尾文案键                      |
| -------- | -------------------------- | -------------------------------------------------------------------------------------------------------------- | -------------------------- |
| outlook1 | IEA《Oil Market Report》     | `iea_forecast.json`：`ieaOmrMonths` / `ieaOmr2026Demand` / `ieaOmr2027Demand` / `ieaOmrWarOnset`                | `ieaOmrMeta.omrSrc`        |
| outlook2 | IEA《Oil 20XX》              | `iea_forecast.json`：`ieaOutlookYears` / `ieaOutlook2023~2025`                                                  | `ieaOmrMeta.oilSrc`        |
| outlook3 | OPEC《MOMR》                 | `opec_forecast.json`：`opecMomrMonths` / `opecMomr2026Demand` / `opecMomr2027Demand` / `opecMomrWarOnset`       | `opecForecastMeta.momrSrc` |
| outlook4 | OPEC《World Oil Outlook》    | `opec_forecast.json`：`opecWooYears` / `opecWooDemand` / `opecWoo2025~2023`                                     | `opecForecastMeta.wooSrc`  |
| outlook5 | EIA《STEO》                  | `eia_forecast.json`：`eiaSteoMonths` / `eiaSteo2026Demand` / `eiaSteo2027Demand` / `eiaSteoWarOnset`            | `eiaForecastMeta.steoSrc`  |
| outlook6 | EIA《Annual Energy Outlook》 | `eia_forecast.json`：`eiaAeoYears` / `eiaAeoConsHigh` / `eiaAeoConsBase` / `eiaAeoConsLow`（情景名另见 `eiaAeoCase*`） | `eiaForecastMeta.aeoSrc`   |
| outlook7 | IMF《World Economic Outlook》 | `imf_forecast.json`：`imfOilEditions`（=["2025","2026"] 按钮顺序）/ `imfOilByEdition`（={辑年:{months,price,actual,meta}}，每辑独立成图） | `imfOilByEdition[...].meta.oilSrc` |
| outlook8 | EIA《STEO》表 2（油价）        | `eia_forecast.json`：`eiaSteoPriceMonths` / `eiaSteoBrent2026` / `eiaSteoBrent2027` / `eiaSteoBrentActual2025` / `eiaSteoPriceMeta` | `eiaSteoPriceMeta.steoSrc` |

**参考线口径（两张油价图不同，勿混）**：

- **outlook7（IMF）** = **本辑当年实际**（按辑取 `actual[edKey]`，口径同预测线，用于「WEO 逐期修订 vs 该年真实落点」）。2025 辑 → 2025 实际 **67.74**（WEO 披露的石油现货价格指数年均值）；2026 辑 → 需 2026 官方全年实际，而 2026 年尚未走完、`OIL_ACTUAL` 未收录 → **该辑暂无参考线**（不拿年内迄今值冒充全年实际）。待 WEO 披露后往 `OIL_ACTUAL` 加一行即自动出现。
  ⚠️ 2026-10-15 订正：此前 `actual` 是**全局**的、前端取「最新已实年份」，导致 2026 辑也画 2025 实际 67.74 —— 与该辑主题（2026/2027 假设）无关，属跨年串味；现改为按辑取当年。
- **outlook7（IMF）** = **本辑当年实际**（按辑取 `actual[edKey]`，口径同预测线，用于「WEO 逐期修订 vs 该年真实落点」）。2025 辑 → 2025 实际 **67.74**（WEO 披露的石油现货价格指数年均值）；2026 辑 → 需 2026 官方全年实际，而 2026 年尚未走完、`OIL_ACTUAL` 未收录 → **该辑暂无参考线**（不拿年内迄今值冒充全年实际）。待 WEO 披露后往 `OIL_ACTUAL` 加一行即自动出现。
  ⚠️ 2026-10-15 订正：此前 `actual` 是**全局**的、前端取「最新已实年份」，导致 2026 辑也画 2025 实际 67.74 —— 与该辑主题（2026/2027 假设）无关，属跨年串味；现改为按辑取当年。
- **outlook8（EIA）** = **当年（2026）实际**（与 outlook7 同一逻辑，按「当年」取而非「上年」）。2026 年未走完 → STEO 表 2 的 2026 年度 Brent 实际未出 → **暂无参考线**（原「2025 实际 69.04」线已于 2026-10-15 移除）。待 2026 实际出来后加进 `actual`（`eiaSteoBrentActual*`）即自动出现。
- ⚠️ 原「② 看板实测 Brent 当年年内日均」橙虚线已于 2026-10-14 应需求移除（两张油价图都不需要），相关 `brentYtdAverage()` 辅助函数一并删除。

**outlook8 的线型与配色**（2026-10-15 统一）：2026 / 2027 **两条都是实线**，且与 outlook7 的 **2026 辑同色** —— 2026 = `#dc2626`（红）、2027 = `#2563eb`（蓝）。原为 EIA 身份色（2026 琥珀 `#d97706`、2027 青 `#0891b2` 且为虚线），与 outlook7 同名的 2026/2027 线观感不一致。回归测试见 `tools/verify_eia_oil.js`。
- ⚠️ 原「② 看板实测 Brent 当年年内日均」橙虚线已于 2026-10-14 应需求移除（两张油价图都不需要），相关 `brentYtdAverage()` 辅助函数一并删除。

**页尾「数据：取自 …」六条文案的规范句式**（2026-10-06 统一，改文案请照此格式，不要退回 `<b>数据：</b>…（mb/d）` 那种写法）：

```
数据：取自 <报告简称>「<章节名>」章节 <Table 号>「<表标题>」的 <行名> 行 <列义>列（源文件 <path>/）。
```

| 面板       | 现文案（与看板页尾逐字一致）                                                                                                                                                     | 长度  |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --- |
| outlook1 | 数据：取自 OMR「Tables」章节 Table 2「Summary of Global Oil Demand」的 World 行年度列（源文件原 data/raw/iea_omr/，2026-10-22 已清理出仓库）。                                                                      | 93  |
| outlook2 | 数据：取自各版《Oil 20XX》「Demand」章节的「Global / World oil demand by product」表的 Total products 行年度列（Oil 2023 版表题为 Global、2024 起改 World；源文件 data/raw/iea_oil/）。                | 147 |
| outlook3 | 数据：取自 MOMR「World Oil Demand」章节 Table 4-1 / Table 4-2「World oil demand in 2026 / 2027」的 Total World 行 Change 列（源文件 data/raw/opec_momr/）。                            | 135 |
| outlook4 | 数据：取自《World Oil Outlook 2026》第 3 章「Demand」Table 3.2「Global oil demand by sector, 2025–2050」的 World 行年度列（旧版次表题不同；源文件 data/raw/opec_woo/）。                           | 136 |
| outlook5 | 数据：取自 STEO「Global Oil Markets」章节 Table 3e「World Petroleum and Other Liquid Fuels Consumption」的 World total 行年度列（源文件 data/raw/eia_steo/）。                           | 136 |
| outlook6 | 数据：取自《Annual Energy Outlook 2026》配套 AEO2026_Narrative_Figures.xlsx 的 sheet「14_RefinThruPut」中「U.S. total product supplied」系列（Series = PSD000:fa_Total，11 档情景）的行年度列。 | 162 |

> ⚠️ outlook1~6 的 `…Src` 文案**没有 extract 脚本写入**（`run.py extract` 只刷新数值键），所以直接改 `data/dataset/*.json` 再跑 `python run.py html` 即可，跑 extract 不会覆盖。
>   **outlook7 / outlook8 是例外**：`imfOilByEdition[...].meta.oilSrc` 由 `src/fetch/demand/pmi_gdp.py` 的 `WOE_OIL_VINTAGES` 期次矩阵派生写入、`eiaSteoPriceMeta.steoSrc` 由 `src/extract/eia_steo_price.py` 生成（都经 `data/processed/*.json` 中转），改文案要改对应脚本并重跑 `run.py extract`（outlook8 走 `run.py build` 亦可，build_dataset 的 `_offline_demand` 会一并带入）。
>
> ⚠️ 2026-10-14 修 `dataio.save_data`：改为**按域合并写**（磁盘上属于该域、且未被本次数据覆盖的键原样保留）。此前 `eia_forecast.json` 这类「手工维护键 + 脚本产出键」混居的域，只要脚本产出任一键，整域就被覆盖——当天 `eiaSteoMonths` / `eiaAeo*` / `eiaForecastMeta` 就是这么丢失的（已从事会话记录按 10-07 22:33 最后落盘状态恢复）。iea / opec 两域仍是纯手工维护（build_dataset 不产出它们的任何键，合并写等于不碰）。
>
> ⚠️ 月度图 2026-02 处的**竖线由 `*WarOnset` 键绘制**（代码内 markLine），文案里不再描述竖线。
>
> ⚠️ 长期图的多版次对照（outlook2 的 Oil 2023/2024/2025、outlook4 的 WOO 2023–2026）是**手工维护**的，改版次时页码/表题会变（典型：WOO 的 Table 3.2 在 2023/2025 版叫「Long-term oil demand by region」、2024 版叫「…in the Reference Case」），引用时须连同版次一起说明。

### 地缘政治

| 指标                           | 单位 / 频率     | 原始数据源                                            | 抓取脚本                          | 看板位置                                                                                        |
| ---------------------------- | ----------- | ------------------------------------------------ | ----------------------------- | ------------------------------------------------------------------------------------------- |
| OVX 原油波动率指数                  | 指数，日度       | Yahoo `^OVX`（curl + 浏览器 UA，query2 主 / query1 兜底） | `src/fetch/geo/ovx.py`        | 图表·OVX 副图 / I_geo 入分                                                                        |
| ICE 布伦特 投机净持仓（Managed Money） | 手，周度→日度前向填充 | CFTC 持仓报告（disaggregated）管理基金多头−空头                | `src/fetch/geo/cftc_cot.py`   | 图表·投机净持仓（仅观测，未计入 I_geo）                                                                     |
| Brent 12 个月期限结构（近月−远月）       | 美元/桶，日度     | Yahoo `BZ=F`（近月连续）与 `BZ{mc}{yy}.NYM`（远月合约）收盘价    | `src/fetch/geo/brent_term.py` | 图表·期限结构（与地缘维度其余图**同款画法**：维度色 #dc2626 实线 + 渐变填充；backwardation / contango 的方向语义在 tooltip 里给出） |

**期限结构的三条使用须知：**

1. **序列长度天然只有约 10–11 个月**，不是 2 年。Yahoo 只给未到期年份的合约留 2 年历史，而已到期年份的合约（如 2025 / 2026 各月）查不到。由于「远月 = 当日 + 12 个月」，能算出的最早日期受限于最早有行情的远月合约。看板 `RANGE=252` 的窗口起点（2026-10 时为 2026-01-25）刚好被完整覆盖，属可接受。
2. **远月合约列表按近月合约的实际交易日推导**，不写死年份区间。早期实现硬编码 5 个年份 × 12 个月 = 60 个合约，其中 40 个已摘牌，每次构建都发 40 个必败 404，容易触发 Yahoo 限流导致整批返回空。现已收敛到实际需要的约 25 个，并对批量失败加了逐合约兜底。
3. **抓取失败不会静默空图**：`fetch_with_status()` 回传 `ok / points / last / error / contracts / missing`，落库为 `brentTermMeta`；序列整段为 null 时卡内显示「本期未取到 Brent 期限结构数据…重跑 `python run.py dataset` 即可恢复」，构建日志同步打 ⚠️ 告警行。

### 宏观金融

维度 KPI 芯片另含：广义美元指数 / 10Y 美债收益率。**逻辑链&#x20;**：美元走强 + 利率上行 → 大宗商品承压，布伦特易走弱；美元走弱 + 流动性宽松 → 原油获得金融溢价

| 指标               | 单位 / 频率  | 原始数据源（序列号）      | 抓取 / 维护脚本                                  | 看板位置                                                                              |
| ---------------- | -------- | --------------- | ------------------------------------------ | --------------------------------------------------------------------------------- |
| 联邦基金有效利率（DFF）    | %，日度     | FRED `DFF`      | `src/fetch/macro/fred_macro.py`            | 图表·利率主图（阶梯线 `stepped`）                                                            |
| 10 年期美债收益率       | %，日度     | FRED `DGS10`    | `src/fetch/macro/fred_macro.py`            | 图表·利率主图（与 DFF **同轴**，两线之间填充 = 期限利差面积；利差另以**独立虚线**走右轴 bp——跌破零线即倒挂，该区间虚线转红，右轴零线为分界） |
| 广义美元指数（DTWEXBGS） | 指数，日度    | FRED `DTWEXBGS` | `src/fetch/macro/fred_macro.py`            | 图表·汇率图左轴（水平线）/ KPI「广义美元指数」/ **macro 维度压力分唯一入分序列**（z-score × 17）                   |
| 美元指数 5 日变动       | %，日度（派生） | 由 DTWEXBGS 派生   | `src/fetch/macro/fred_macro.py` `derive()` | 图表·汇率图右轴 / 触发「美元指数 5 日变动 ≥2%」预警                                                   |

> 注：DFF 为阶梯型政策利率（仅在议息日跳变，252 个交易日内通常只有个位数取值），因此**只上图、不入压力分** —— z-score 对阶梯序列会退化成「长期常数 + 议息日突刺」；利率端的连续代理由 10Y 美债承担。利率图两序列同为 %，故**同轴**而非左右双轴（同单位双轴会扭曲利差的视觉读数）。宏观金融两张图配置 `from:"2024-01"` **全窗口展示**（其余日度图仍走 RANGE=252 滚动窗口）。

---

## 预警规则

| 触发条件           | 维度   | 等级         |
| -------------- | ---- | ---------- |
| Brent 单日变动 ≥3% | 其他突发 | ≥5% 为 high |
| 20 日年化波动率 ≥45% | 地缘政治 | high       |
| 美元指数 5 日变动 ≥2% | 宏观金融 | mid        |
| 库欣库存周变动 ≥2 百万桶 | 供给侧  | ≥4 为 high  |

合并顺序固定为 **突发 → 地缘 → 宏观 → 供给侧**，再按日期倒序、截断至最近 60 条。改动任一环节都会改变页面渲染结果。

---

## 库欣 / 全美商业原油库存：序列口径订正（2026-10-08）

**现象**：「库欣原油库存」图上显示 ~427 百万桶、「全美商业原油库存」显示 ~711 百万桶 —— 两个都对不上标签。
库欣（Cushing, OK，WTI 交割地）真实库存只有 **22–30 百万桶**，与全美商业库存（~427）差一个数量级；
含 SPR 的原油总库存（711）= 全美商业(ex-SPR) + SPR。

| 图标题             | 订正前（错）                | 订正后（对）                          | 2026-09-25 实测   |
| --------------- | ------------------- | ----------------------------- | -------------- |
| 库欣原油库存         | `PET.WCESTUS1.W`（427） | `PET.W_EPC0_SAX_YCUOK_MBBL.W` | **24.301** 百万桶 |
| 全美商业原油库存       | `PET.WCRSTUS1.W`（711） | `PET.WCESTUS1.W`              | **427.320** 百万桶 |
| 含 SPR 原油总库存（派生） | 无（该 id 被误当作「全美商业」）  | `gross = total + spr`（恒等，不单独抓取） | **711.087** 百万桶 |

**怎么找到库欣的 seriesid**：EIA v2 只开放 `/v2/seriesid/{id}`，而库欣的 id **不在 `PET.WC*` 命名族里**
（`WCUSTUS1` / `WCESTUS2` / `WCSSTUS2` 等猜测全部 404）。真实 id 是 EIA 站点表格的列代码形式
`PET.W_EPC0_SAX_YCUOK_MBBL.W`（`duoarea=YCUOK`，product `EPC0` Crude Oil，process `SAX` Ending Stocks Excluding SPR），
与官网表格 `pet_stoc_wstk_dcu_ycuok_w.htm` / xls `W_EPC0_SAX_YCUOK_MBBLw` 同口径。
**探测技巧**：id 的最后一段是频率位，写错会得到「Invalid frequency 'W2'」而不是 404 —— 说明前缀合法、
前缀错才会 404，据此可区分「前缀不存在」与「频率写错」。

**三项连带修改**：

1. `gross` 作为**派生序列**（`EIA_weekly.DERIVED`）：含 SPR 总库存 = 全美商业 + SPR 是 EIA 官方恒等
   （711,087 = 427,320 + 283,767 千桶，逐周精确成立）。此前这个数被单独抓一份 `PET.WCRSTUS1.W` 再错标成
   「全美商业」；现在不再重复抓取，改为 `build_axes` 里换算成百万桶**之后**相加（前端 `fetchEIA` 同口径），
   并顺带用这个恒等做数据自校验。
2. 库欣预警阈值按真实分布重校准：库欣周变动 2004 年至今 1172 周，中位 0.72、p90 1.92、p95 2.50、p99 3.68 百万桶。
   旧值「≥4 mid / ≥8 high」是按 427 量级定的，换成真库欣后 **≥8 全历史 0 次命中**（死分支）；
   现改为 **≥2 mid（约 2.7% 的周）/ ≥4 high（约 0.8%）**。
3. 图卡补「读法」一行：库欣看交割地挤仓压力（22–30），全美商业看整体供需（425–430），两者不可互换解读。

**防线**：`tools/check_eia_series.js` 只校「id 表四处一致」，校不出「id 对了但值不是那个东西」，
所以新增 `tools/verify_stocks.js` 把**量级**也做成断言（库欣 15–45 / 全美商业 380–480 / gross == total+spr），
快照段与实时段（桩接口）都跑。

---

## 两张库存图叠加「周增减」柱（右轴，2026-10-08）

**需求**：绝对水平看不出周度抖动 —— 库欣 22–30 百万桶里相邻周差 0.5（相对 2%）、全美商业 425–430 里差 1–2（不到 0.5%）。
把**较上周的增减量**单独画成柱、走**右 Y 轴**，才读得出「这周是累库还是去库、幅度多大」。

**画法**：`src/pipeline/templates/dashboard.js` 的 `SUPPLY_RENDERERS.linebar`，**库欣 / 全美商业原油库存两张图**共用（`type:"linebar"`，都走 EIA 周度轴）。

- 左轴 = 库存水平（蓝线，与改动前完全一致）；右轴 `y1` = 逐周增减（百万桶）。
- ⚠️ 渲染器里线名取 `c.title.split(" ")[0]`：两张图共用，写死「库欣」会让全美商业图的 tooltip
  说出「库欣库存：427.3」这种错话。
- 变动量 = 折线**同一份**数组（`eiaAxis()` 返回的窗口化周度值）逐点差分，第 0 点无前值 → `null`
  （所以柱的非空点数恒比线少 1 —— 校验脚本里为这点踩过一次假 FAIL）。
- ⚠️ 柱与线必须取同一份数组：一边取 `eiaWeekly`、一边取日度前向填充数组会索引错位，
  实时拉取后柱子整体偏一周，看起来像「数据对不上」。
- 柱画在折线下层（Chart.js 按 `order` 升序绘制，柱 `order:1`、线 `order:2`），半透明；
  右轴照 `rate` 渲染器：只给 0 那根网格线着色，并用 `afterBuildTicks` 强制补 0 刻度
  （自动步长常跳过 0，0 线画不出来就没有「累/去」分界）。
- **配色：红柱 = 累库（+，库存增），绿柱 = 去库（−，库存减）**，沿用涨红跌绿。
  ⚠️ 与 `rate` 渲染器（正绿负红）相反 —— 那处的红色是「倒挂」的异常语义，不是涨跌幅语义。
  要整体对调只需改 `linebar` 里的 `barFill()`。
- 末值气泡两枚：库存水平走 `endTagFmt` 默认格式，周增减走数据集级 `endTagFmt`（带正负号）+
  `endTagColor`（中性灰）。`endTag` 插件为此加了两个**向后兼容**的能力：
  数据集级 `endTagColor` / `endTagFmt` 覆写，以及同 x 多气泡的竖向错开
  （否则两枚精确重叠、只能看见后画的那枚）。

**末值气泡避让右轴刻度**：气泡默认画在末点右侧，但右轴刻度文字在 `chartArea` **之外**，贴边的气泡会盖住右轴刻度
（双轴库存图的「+0.9」压住「0」）。`endTag` 插件判断翻转的可用右边界改为 `area.right + y1.width − 6`，
超出就翻到末点左侧；单轴图没有 `y1` → 宽度 0 → 判定退回流，行为与改动前一致。

**图卡页尾**：两张库存图的 `source` 都按 **数据源 / 注解 / 双轴** 三段逐行展示（每项一个 `<span class="sline">`，
CSS `.src .sline{display:block}` + `.sline+.sline{margin-top:5px}`）。以后给别的图加多条说明，
照抄这个 `.sline` 包一层即可自动换行，不用手工插 `<br>`。

**回归**：`tools/verify_stocks.js` 对两张库存图各跑 5 条叠加断言 —— 柱类型 / 绑右轴 / 柱值逐点等于折线差分 /
右轴在右侧且跨 0 含 0 刻度 / 页尾三段 `.sline`，快照段与实时段都跑（实时段专门抓「拉取后柱线错位」这条路径）。
另做全 tab 遍历：9 实例 0 空图 0 报错，`prod` 的 `niceY` 刻度与 `opec` 的既有双轴均未受
左轴抽取（`lineYAxis`）与 `endTag` 翻转改动影响。

---

## SPR 图改成双轴：右轴 = SPR 占原油总库存比重（2026-10-07）

**需求**：此前为「全美商业库存」图写过的派生序列 **gross**（含 SPR 原油总库存 = 全美商业库存 + SPR，EIA 口径逐周恒等）
一直只被 `verify_stocks.js` 当自校验用，没进过图。现在把 SPR 图改成双轴：左轴 = SPR 库存水平（百万桶），
右轴 = **SPR 占原油总库存比重（%）= spr ÷ gross**，用来看「战略储备在这一池原油里占多重的分量」。

**画法**：`SUPPLY_RENDERERS.linepct`（折线 + 派生占比折线），只有 SPR 一张图在用。

- 左轴 = SPR 库存（蓝线 + 面积，`c.level` 开关照旧）；右轴 `y1` = 占比（**琥珀 #d97706 虚线**，与 `rate` 渲染器
  「右轴派生量用虚线」的既有约定一致），刻度带 `%`。
- ⚠️ 右轴**先按折线画**（用户明确「暂时」是折线）；日后改柱只需把第二个数据集的 `type` 换成 `"bar"`
  并把 `backgroundColor` 换成静态色，其余不用动。
- ⚠️ 分子分母必须**同源同窗口**：`spr` 走 `eiaAxis(c.key, c)`、`gross` 走 `eiaGrossWeekly(c)`，
  两者都由 `eiaI0(c)` 决定起点；长度对不上就判「取不到」（返回 `null` → 右轴无值），
  **绝不让错位数据混进比值**。
- ⚠️ 派生序列只能取**周度**数组 `eiaWeekly.gross`：日度 `STATE.eia.gross` 的长度是日度轴长度，
  与周度折线索引对不上，拿它算比值会得到一串乱跳的百分比。
- `eiaGrossWeekly()` 里还留了「`total + spr` 现算」的兜底：python 与前端 `fetchEIA` 各算一份
  派生 gross，任一路漏算时右轴仍有值（理论上走不到）。
- 占比不需要强制 0 刻度（恒为正、40% 上下），所以 `y1` 不套 `linebar` 那套 `afterBuildTicks` 补 0；
  末值气泡两枚（库存 + `39.9%`），`endTag` 的右边界避让逻辑对 `y1` 同样生效。

**量级**：当前窗口（2024-01 起）占比 **39.9%–49.7%** —— 2024  SPR 回补期一度接近 50%，
之后随商业库存回升落到 40% 上下。末值 `283.767 / 711.087 = 39.92%`。

**图卡页尾**：同库存两图，按 **数据源 / 注解 / 双轴** 三段 `.sline` 分行，文案与用户指定的定稿逐字一致
（`tools/verify_spr_share.js` 里存了一份 `WANT_LINES` 做 JSON 级逐字比对，
以后改口径会在这里留下 FAIL 痕迹）。旧文案里「月度口径…供维度 KPI 芯片」那一尾巴随改造删掉；
「右轴暂按折线、改柱只需动渲染器第二个数据集的 type」这句从页尾撤下、只留在 `linepct` 的代码注释里。

**回归**：

- `tools/verify_spr_share.js` 快照段 21 条：双轴 2 数据集 / 右轴仍折线且绑 `y1` / 逐点 `share == spr ÷ gross` /
  占比非空且末值 == 39.92 / 右轴在右侧且刻度带 `%` / 左轴仍是百万桶 / 页尾三段且顺序、文案正确 /
  徽章仍在 + 全 tab 遍历无新报错、无空图。
- `tools/verify_spr_live.js` 实时段新增 2 条：**实时态**右轴占比数据集仍在且末值 == `spr ÷ gross`
  （快照态对得上不代表拉取后对得上），另保留 `--drop-spr` 缺序列回归实验路径。
- `tools/verify_spr.js`、`tools/verify_stocks.js`、`tools/check_eia_series.js` 全绿。

---

## OECD 商业库存图页尾三段式（2026-10-07）

`OECD 商业库存：原油 / 成品油 (百万桶, 月度)`（MOMR 表 9-1，IEA 口径，2023-09 → 2026-07 共 35 个月）
页尾同样改成 **数据源 / 注解 / 同轴** 三段 `.sline`。

- 第三段标签取 **同轴** 而非**双轴**：原油 ~1,310 与成品油 ~1,450 百万桶**量级接近**（成品油≈原油 1.1 倍、
  占合计 52.5%），`SUPPLY_RENDERERS.oecdCrude` 注释里就写明「同轴即可，不需要左右双轴」，
  所以第三段如实写「同轴：…同轴即可读，不需要右轴」，避免名不副实。
- 口径提醒写进注解：这是 OECD **合计**的商业库存（含原油 + 成品油、不含战略储备），
  成品油行含石化产品、本身不含原油；与上面两张美国 EIA 商业库存**区域与归类都不同，不可直接比较**，
  只能互证方向。合计 = crude + products，末值 2,763（2026-07），较 2025-09 峰值 2,863 去库 100 百万桶，
  但近 3 个月合计仅 +7（成品油 +22、原油 −14），去库在放缓。

**通用页尾守门**：新增 `tools/verify_footers.js`，对库存四张图（cushing / total / oecd / usspr）各跑 5 条断言 ——
页尾恰好 3 段 `.sline` / 段首标签依次为 数据源·注解·(双轴|同轴) / 数据源段点明 EIA 序列 id /
**无 markdown 星号残留** / 与 `WANT_LINES` 逐字全等。以后改任何一张库存图的页尾措辞，
都必须同步改这个脚本里的定稿文案（刻意做成会 FAIL），否则口径会被改得静悄悄。
（`**…**` 在 HTML 里只会被原样显示成两个星号 —— 这次写页尾就不小心留了一处，
被 `verify_footers.js` 的星号断言当场抓出来。）

---

## 最新值 + 数据截止日标注（2026-10-07）

供给侧 / 需求侧每张图表卡片的标题右侧带一枚徽章 `值 · 截至日期`，图内末点画圆点 + 数值气泡；维度 KPI 芯片在数值下方补一行截止日小字。三个口径约定：

1. **截止日 = 该序列最后一个非空值对应的日期**，不是今天、也不是官方发布日。EIA 周度标 `26/09/25`，OPEC 月度标 `26/08`，OECD 标 `26/07`，Rig 标 `26/09` —— 同屏可见各自的滞后程度。
2. **值数组与日期数组按尾部对齐**（`off = d.length - v.length`）：`eiaDates` 从 1982-08 起 2296 条而 `eia.cushing` 只有窗口化 1007 条，按下标 0 对齐会标成 `02/01/11` 这种错误日期。
3. **末点是预测值的用「预测至」**：OPEC 剩余产能（EIA 18 个月滚动预测）与全球 GDP 预期（WEO 到 2027）。

未标注的三类：多序列合成图只标日期不标值（`refinery` 美开工率 + 中国加工量）；多序列图徽章加前缀消歧（OPEC `合计 25.11`、OECD `原油 1,313`、PMI `美 54.5`）；ECharts 图（Rig、PMI）只加徽章不加图内气泡。

**顶部「数据截至 X」= 页首那一行，与卡内徽章不同源**：它取 `kpis.latest_date`，即 **Brent 最后一个真实观测日**。日期轴是 Brent / WTI / GAS / DGS10 / DFF 各序列的并集，而 10Y 美债（`DGS10`）常比油价晚 1–3 个交易日发布，轴尾会留下「只有 DGS10 有数、Brent 只是前向填充重复」的补尾日（2026-09-30 ~ 10-05）。原 Python 侧写法 `latest = len(brent)-1` 直接取 `dates[-1]`，会把「截至」虚报成 10-05；而前端 `loadLive()` 会裁掉尾部 Brent 为空的日子，于是**同一张看板静态预览写 10-05、localhost 实时拉取写 09-29**（2026-10-07 修：Python 侧改为取 `max(raw_prices["brent"])`，两路统一到 Brent 最后真实观测日）。

另注意：**Brent 12M 期限结构走 yfinance（远月合约），比 FRED 现货序列更靠前**，它的卡内徽章标 `截至 26/10/05` 而顶部写 `09/29` 是正常现象 —— 卡内徽章按各自序列的最后一个非空值算。

---

## OPEC 月度产量图：双轴 + 线型 + 末端标注（2026-10-07）

**问题**：OPEC 合计 ≈24 百万桶/日 与五国（1.9–7.3）共用 0–30 单轴，五国末点被压在绘图区底部 40px 内（画布 614×280，绘图区高 227，实测末点 y 206–246），线型无从读起；六条线只靠颜色区分，灰度 Print / 色觉障碍下不可读。

**三项修改（代码在 `SUPPLY_RENDERERS.opecMonthly`）**：

1. **拆轴**：合计走右轴 `y2` 0–30，五国走左轴 `y` 0–10.5。右轴只保留 `0` / `30` 两个刻度（`ticks.callback` 过滤），把宽度让给末端标注；轴上方补一行灰色「合计(右轴)」。拆轴后五国末点铺开到 y 86–225（117px），扇出有足够空间。
2. **线型**：五国各配一种 `borderDash`（沙特 `9,4` 粗虚线 / 伊拉克 `2,3` 点线 / 伊朗 `7,3,2,3` 长虚点线 / 阿联酋 `12,3,2,3` 长点线 / 科威特 `1,3` 细点线），线宽 1.2 → 1.8。灰度下仍可按线型区分，颜色退为辅助。
3. **末端标注**：取消图例，国名 + 最新值（用中文短名，如「阿联酋 3.83」，tooltip 仍是全称）用引线牵到绘图区右侧标注槽；按 y 升序做扇出（相邻标签至少 13.5px，自底回推防顶出画布），末点画白心圆点；引线为 `点 → 斜段 → 水平肩` 三段，颜色取序列色。合计线量级读不到左轴，故在其末点左侧放一枚气泡「合计 24.08」。

**两个坑**：

- ⚠️ **绘制插件必须包 try/catch**：Chart.js 的 `afterDatasetsDraw` 抛异常会打断 rAF 动画帧循环，元素坐标被**永久冻结在动画中途** —— 实测整张图的所有曲线塌到底部 0–2.5 区间、标签完全不画，而 `scales.y.min/max` 看着一切正常，极易误判成数据错。本次即因 `items.push` 漏存 `v` 触发 `it.v.toFixed` 而中招。
- ⚠️ **校验脚本读坐标前要 `c.update('none')`**：默认动画下 `meta.data[i].y` 是动画中间值，直接读会得到"线全塌在底部"的假象。

校验脚本 `tools/verify_opec_tail.js`：量双轴 min/max/位置、各序列 `yAxisID`/`borderDash`、扇出后标签的最小间距与溢出、图例开关、pageerror 栈。实测 `labelCount=5 / minGap=14 / overlaps=0 / spill=0 / ERRORS=0`。

> **2026-10-08 更新**：国别线 5 国 → **9 国**（见下一节），本节的实测数字已随之上移
> （`labelCount=9 / minGap=12 / overlaps=0 / spill=0`）。

---

## OPEC 月度产量图：5 国 → 9 国（2026-10-08）

补入 **利比亚 / 尼日利亚 / 委内瑞拉 / 阿尔及利亚** 四国，现在图上 = 合计粗线（右轴）+ 9 条国别细线（左轴）。

**关键事实：数据层从来都是 12 国全量**。`原 opec_momr.py（已下线，口径见「已下线口径留档」）` 的 `COUNTRIES`
本来就列了 12 个成员国，`data/processed/opec_monthly.json（存档，2026-10-23 已移出仓库）` 的 `countries` 里 12 国 × 34 月
（2023-11 ~ 2026-08）一条不缺；此前只是 `dashboard.js` 的 `major` 数组只画了 5 国。
所以这次**没有动解析脚本**，只改了前端：

- `major` 追加四项（英文名必须与 json 键一字不差）：`Libya 利比亚 #7c3aed [4,3]` /
  `Nigeria 尼日利亚 #db2777 [5,2,2,2]` / `Venezuela 委内瑞拉 #0d9488 [8,3]` /
  `Algeria 阿尔及利亚 #65a30d [2,2,6,2]`。四色四线型均与原五国不重。
- **GUT 76 → 100**：末端标注槽的可用宽 = GUT − 18，原来 58px；最长标签
  「阿尔及利亚 1.00」（5 个汉字 + 值）实测约 75px，会被画布裁掉。画布宽 614 → 绘图区 514。
- **GAP 13.5 → 12.5**：9 条标签扇出需 8×GAP 连续空间，收一点更稳（10px 字号下 12.5px 仍可读）。
- 图卡 `source` 改为三段式（数据源 / 口径 / 自洽），写明「12 国分项之和 == Total OPEC（逐月，maxAbs 0.002）」。

**自洽恒等（校验断言用）**：12 国分项之和 == `Total OPEC`（逐月，容差 0.05，实测 maxAbs = 0.002）。
四个新国的末点（2026-08，mb/d）：利比亚 1.355 / 尼日利亚 1.573 / 委内瑞拉 1.145 / 阿尔及利亚 0.999。

**解析覆盖**：`data/raw/opec_momr/` 共 32 期 PDF 全部解析，唯一跳过的是
`momr-january-2024.pdf`（该期找不到表 5-7 页）——不影响结果：2023-11/12/2024-01 三个月由
`momr-february-2024.pdf` 覆盖，序列起点仍是 2023-11。

校验：`tools/verify_opec_tail.js`（9 条线齐全 + 四新国末点值逐一对上 + `overlaps===0` +
`spill===0` + 图例关闭 + 无 pageerror），实测 **ALL OK**；
`verify_world_quarterly` / `verify_footers` / `check_eia_series` 回归均 0 错。

> **2026-10-09 再改造（删合计线 + 右轴、改实线、加内联末端标签）**：见下节。

---

## OPEC 月度产量图：删合计线+右轴、改实线、加内联末端标签（2026-10-09）

用户要求与 Non-OPEC DoC 图一致：① 删「OPEC 合计」粗线（合计值由卡头徽章承载；
全球图 2026-10-10 起为 STEO 月度口径、其 OPEC 线=11 国 ≠ MOMR 12 国合计），**右轴 `y2` 随之移除**；② 九国线由虚线改**实线**
（删 `borderDash`）③ 九国各加一枚**内联末端标签**（白心圆点 + 短引线 + **仅最新值**，不显示国名；绘图区内、
贴末点**左侧**右对齐防溢出，复用 `makeInlineTailPlugin`，与 nonopecdoc 同款）④ 右侧标注槽不再需要。
图现为**单左轴 0–10.5**，无右 padding（`GUT` 删除）；顶部启用 Chart.js 图例，中文短名、颜色与折线一致，可点击切换显示/隐藏。

**口径不变**：12 国（沙特/伊拉克/伊朗/阿联酋/科威特/利比亚/尼日利亚/委内瑞拉/阿尔及利亚/刚果（布）/赤道几内亚/加蓬），
单位 mb/d，原油口径不含 NGL；12 国分项之和 == Total OPEC 的恒等仍在 data 层校验，仅图内不画合计线。
x 轴仍走 `STATE.opecMonths`（34 月，2023-11 起）。

**校验**：`tools/verify_opec_tail.js` 重写断言——`y2Exists:false` / 9 国均 `borderDash==='solid'` /
末点九值与 `EXPECT` 逐一对上 / 末端内联标签只显示数值、`spill:0`、无重叠 `overlaps:0`、最小间距 `minGap:12` /
图例开（中文标签/颜色匹配/可点击切换）/ 无 pageerror → **ALL OK**；与 `verify_nonopec_doc` /
`verify_world_quarterly` / `check_eia_series` / `verify_footers` 一并回归全绿。

> **2026-10-10 再改造（改 ECharts 双格：上格沙特 / 下格其余八国，共享 x 轴）**：见下节。

---

## OPEC 月度产量图：改 ECharts 双格（上格沙特 / 下格十一国，2026-10-10）

与 nonopecdoc 同款处理。单左轴 0–10.5 时沙特 6.76–10.11 独自占满上半区，其余十一国
（赤道几内亚 0.05 ~ 伊拉克 4.32）被压在底部约 40% 内。改为 **ECharts 两个 grid 上下叠放**：
**上格 = 沙特**（Y **6.5–10.25**），**下格 = 其余十一国**（Y **0–4.5**），两条 `xAxis` 共用同一份 34 月，
`axisPointer.link:[{xAxisIndex:'all'}]` 十字线上下贯穿。末点标签用 ECharts 原生 `series.endLabel`（仅数值）。

**⚠️ 下格 11 条线末值密集，必须开标签避叠**：末点 3.835 / 3.378 / 2.086 / 1.894 / 1.573 / 1.355 /
1.145 / 0.999 / 0.275 / 0.217 / 0.047，**最小相邻差仅 0.070**（加蓬 0.217 vs 刚果（布）0.275），
换算到 0–4.5 轴不足 4px，必然叠字；（赤道几内亚 0.047 与加蓬 0.217 之间也仅 0.17）。
故每条 series 带 `labelLayout:{moveOverlap:'shiftY',hideOverlap:false}`（ECharts 原生纵向避叠，
等价于原 Chart.js 版 `makeInlineTailPlugin` 的扇出，**但没有引线**）。
⚠️ 这与 nonopecdoc 不同：后者下格只有 3 条线、在 0–2 轴上天然分开，**不需要**避叠。

**版式对齐（2026-10-10 追加）**：两图**并排显示在同一行**，grid 版式与总高必须**逐像素一致**
（用户要求 y 轴上下对齐、整轴高度一样）——已抽成共享常量 **`EC2_H=400`** 与 **`ec2Grid()`**
（定义在 `dashboard.js` 的 `moveSource` 之后），两个渲染器都从它取值，不许再各自手写 grid。
当前签名（两图**完全相同**）：

```js
const EC2_H=400;
const ec2Grid=function(){
  return [{left:52,right:64,top:44,height:145},{left:52,right:64,top:207,bottom:48}]
         .map(function(g){return Object.assign({},g);});
};
```

即 **上下两格等高 145px**（400 − 图例 44 − 下边距 48 = 308，中间留 18px 间隙 → 308/2 − 9 ≈ 145）。
上格 `top:44` 是给 OPEC 两行图例预留的，Non-OPEC 单行图例多出的留白是对齐的代价；
`grid` 数组每次渲染都经 `ec2Grid()` **深拷贝**，避免两个 ECharts 实例共享同一引用、
被 `setOption` 归一化时互相污染。`verify_nonopec_doc.js` 已加交叉断言
（`gridsAligned`：两图 grid 签名 `[left,right,top,height,bottom]` 逐项相等；两图 `boxH` 相等；
**`gridHeightDiff<=4`**：同一图内上下两格像素高之差 ≤4）→ 实测 `145 / 145`、`opecH 400`、ERRORS=0。
轴步长同样取 **0.25**。

**校验**：`tools/verify_opec_tail.js` 按 ECharts 重写（读 `ecCharts`）→ 2 grid / 两 xAxis 同 34 月且
`gridIndex` 显式 / 上格 6.5–10.25、下格 0–4.5 / 9 条 series 归属（沙特→grid0、其余→grid1）、颜色、
末值、`endLabel` 开启、**`moveOverlap==='shiftY'`** / 图例 9 中文项 / `axisPointer.link` 已配 /
无 pageerror → **ALL OK**。
⚠️ `verify_world_quarterly` 里「OPEC 12 国月度图仍在」的断言原读 `charts[...]`，
图换 ECharts 后需改成 `charts[...] || ecCharts[...]`（已修）。

---

## OPEC 原油产量图换源：MOMR 12 国 → STEO 表 3d 11 国（2026-10-11）

用户在 STEO base tables（`oct26_base.xlsx` / `3dtab`）里看到 `OPEC total` 段的 11 国列表
（阿尔及利亚/刚果/赤道几内亚/加蓬/伊朗/伊拉克/科威特/利比亚/尼日利亚/沙特/委内瑞拉），
问"这是不是标准的 OPEC 不含阿联酋的数据，对的话就把『OPEC 原油产量』图换成这个源"。

**核实结论：是，且证据链完整**：
- **官方脚注 (c)**（`steo_oct26.pdf` p36，表 3d 页脚原文）：
  `OPEC = Organization of the Petroleum Exporting Countries: Algeria, Congo (Brazzaville),
  Equatorial Guinea, Gabon, Iran, Iraq, Kuwait, Libya, Nigeria, Saudi Arabia, and Venezuela.`
  —— **11 国、不含阿联酋**（UAE 在 STEO 口径里不算 OPEC 产量分组成员；用户截图里的 "(a)"
  是另一张表的脚注字母，同一份国家清单）。
- **恒等**：11 国之和 == `copr_opec`（3d）逐月相等（maxAbs 0.0000，72 月 0 违例）；
  3d 的 `copr_opec` 与 3a 的 `copr_opec` **逐月同值**（maxAbs 0.0000）→ 与全球图完全同源。
- 末个历史月 2026-09：沙特 8.10 / 伊拉克 3.70 / 伊朗 1.90 / 科威特 1.62 / 尼日利亚 1.49 /
  利比亚 1.27 / 委内瑞拉 1.21 / 阿尔及利亚 0.98 / 刚果 0.27 / 加蓬 0.22 / 赤道几内亚 0.04，
  合计 20.80（≠ MOMR 12 国的 24.08，差的就是阿联酋 ~3.3）。

**换源内容**（`SUPPLY_RENDERERS.opecMonthly` 整体重写）：
- **数据链**：`steo_monthly.py` 新增 `OPEC_MEMBERS`（11 组 `copr_*` 代码，⚠️ 大小写不统一：
  `copr_IR`/`copr_ag`）+ `extract_opec_members()`（解析 `3dtab`，脚本内自验 11 国恒等）→
  `steo_world_monthly.json` 的 `opecMembers`（{中文名: [72 值]}）→ `build_dataset` 注入
  `steoOpecMembers` / `steoOpecMembersMeta`（归 `world.json` 域）。
- **轴**：分国行**只有历史段有值**（2026-10 起预测月为 null，STEO 不提供分国预测）→
  x 轴截到 `steoLastHistorical`（2026-09），**57 月 2022-01~2026-09**；合计的预测段不在此图
  （全球图已有）。
- **国家增删**：**−阿联酋**（STEO 11 国口径），其余不变；`major` 数组键由英文改**中文名**
  （json 键即中文名），按末点产量降序排列。
- **双格**：布局沿用——上格沙特（数据驱动 6.25–11.25，沙特全史 6.46–11.00）、
  下格十国（0–4.75，伊拉克最高 4.58），`endLabel` 末点数值 + `moveOverlap:'shiftY'` 避叠。
- **徽章**：`STAT_MAP.opecMonthly` 重接 `{v/d: steoHistCut(steoOpecMonthly/steoMonths)}`
  → 「合计 20.80 · 截至 26/09」（旧为 MOMR「合计 24.08 · 截至 26/08」，两口径不可直接对比）。
- **页尾**：三段 `.sline` → **单段**（数据源 STEO 表 3d + 脚注 c 11 国清单 + 不含阿联酋 +
  分国无预测说明 + 提取脚本路径），与全球图页尾风格一致。
- **旧 MOMR OPEC 键移除**：`opecMonths` / `opecMonthly` / `opecMonthlyCountries` /
  `opecMonthlyMeta` 从 build_dataset / dataio（opec.json 域）/ dashboard.js（computeDerived）
  一并摘除；同时清掉引用它们的**死代码**（`cfg.fourth` / `renderOpecMonthlyChart`，
  `cfg.fourth` 早已无 DIM 使用）。当时 `opec_momr.py` 文件保留（仍产出 DoC 10 国键，
  Non-OPEC DoC 图不受影响）；该脚本已于 2026-10-23 移出仓库。

**校验**：`tools/verify_opec_tail.js` 整体重写——2 grid / 双 xAxis 57 月（2022-01~2026-09）/
11 条 series 归属+颜色+末值（沙特 8.10 等，index 56）/ endLabel+shiftY / 图例 11 项且
**无「阿联酋」** / 徽章 `合计 20.80 · 截至 26/09` 且不含旧值 24.08 / 页尾无 `secondary sources`
与 `原 opec_momr.py（已下线，口径见「已下线口径留档」）` 残留 / axisPointer.link / 无报错。`run.py dataset`（10 域文件）→
`run.py html` → 5 脚本回归（world_monthly / nonopec_doc / opec_tail / eia_series / footers）
全 **ALL OK**。截图 `output/_shot_opec_11.png`。

> **2026-10-11 追加（同日两处小修）**：
> ① **图例颜色与折线不匹配**（用户发现）：根因是 ECharts 的**图例标记取 `series.itemStyle.color`**，
>   两张双格图只设了 `lineStyle.color` → 图例回落**默认调色盘**（#5470c6/#91cc75/#fac858/#ee6666…），
>   与折线配色完全对不上。修法：series 补 `itemStyle:{color:与折线同色}`（OPEC 与 Non-OPEC DoC
>   两图同款同修；其余 ECharts 图都走 `line()` 工厂、本就带 itemStyle，无此问题）。
>   校验两脚本各新增断言：series `itemStyle==lineStyle` + **从 zr 渲染层取图例 path 填充色逐项
>   == 折线色**（防再次回落）。
> ② **「刚果（布）」简写为「刚果」**（用户要求）：改 `steo_monthly.py OPEC_MEMBERS`（json 键）
>   → `dashboard.js major` → DIMS 页尾与校验 EXPECT 键。⚠️ 键名变更须**重跑 extract**；
>   README 的 MOMR 时期历史节（12 国记录）保留旧称不动。

> **2026-10-11 追加（B86）**：用户反馈 OPEC 图图例太长，要求**字体调小一号**。修法：
> `dashboard.js` 中 `opecMonthly` 与 `nonOpecDoCTotal` 渲染器的 `legend.textStyle.fontSize`
> 从 `10` 调为 `9`；颜色/字重/图例项内容不变。重渲染后两 verify 脚本仍 ALL OK；截图
> `output/_shot_opec_legend.png` / `output/_shot_nonopecdoc_legend.png` 确认生效。

> **2026-10-11 追加（B87）**：两张图页尾数据源描述**简化为单段**（对齐全球图 10-08/10-11 的简化风格）。
> OPEC 图 `source` 整段替换为 `数据源：EIA 短期能源展望（STEO）base tables Excel 表 3d 的 OPEC 11 国分项· 提取脚本 src/fetch/supply/steo_monthly.py`；
> Non-OPEC DoC 图替换为 `数据源：EIA 短期能源展望（STEO）base tables Excel 表 3d 的 OPEC+ 非 OPEC 参与国（DoC）10 国分项与合计· 提取脚本 src/fetch/supply/steo_monthly.py`。
> 保留 `<b>数据源：</b>` 加粗前缀；删除脚注 c / 不含阿联酋 / other participants 国别清单等长文案。两 verify 脚本断言同步更新（改要求「OPEC 11 国分项」/「OPEC+ 非 OPEC 参与国」并禁旧特征词），仍 ALL OK。

> **2026-10-11 追加（B88）**：用户在看到俄罗斯 2022-04 下挫后，要求在 Non-OPEC DoC 图上标记「俄乌冲突」与「欧盟对俄海运原油禁运」两个历史事件，并询问竖线/灰区哪种更好。**推荐并采用「竖线」**：两点事件为离散时点，竖线更精确且不遮蔽；灰区更适合表示时段/体制，若罩 2022-02–2022-12 会暗示整个窗口均受扰动，与 6 月已修复的数据矛盾。
> 修法：在 `dashboard.js` 的 `nonOpecDoCTotal` 渲染器中，仅给俄罗斯序列（上格 grid 0）加 `markLine`：两条灰色虚线分别位于 2022-02（俄乌冲突 22/02）与 2022-12（欧盟禁运 22/12），颜色 `#64748b`，dashed，宽 1.4，标签在顶部左右，不与居中图例重叠。用户指出事件完全是俄罗斯的，下格那 9 国不应画线，随后去掉了 grid 1 的竖线。
> `verify_nonopec_doc.js` 新增俄罗斯序列 markLine 数量/名称断言，并断言下格（grid 1）不应出现该竖线。`node --check` → `run.py html` → OPEC verify / DoC verify / footers verify 均 ALL OK；截图 `output/_shot_nonopecdoc_legend.png` 确认效果。OPEC 图与页脚无变化（非污染）。

> **2026-10-11 追加（B89）**：用户在分析俄罗斯 2022→2026 持续下行原因后，要求把「OPEC+ 自愿减产」同样标注到 Non-OPEC DoC 图（俄罗斯面板）。选取 **2023-11** 作为标记点，对应 2023-11 宣布的 2.2 mb/d 集团自愿减产（2024 起生效），正好是 2023→2024 俄罗斯产量台阶下行的主因。
> 修法：`dashboard.js` 的 `nonOpecDoCTotal` 俄罗斯序列 `markLine.data` 增加 `{xAxis:"2023-11",name:"OPEC+ 自愿减产 23/11"}`；三条灰色虚线标签并排于上格顶部，互不重叠。`verify_nonopec_doc.js` 断言由 2 条升级为 3 条。`node --check` → `run.py html` → DoC verify / OPEC verify 均 ALL OK；截图 `output/_shot_nonopecdoc_legend.png` 确认三条竖线均位于俄罗斯面板。

> **2026-10-11 追加（B90）**：用户看到 OPEC 原油产量图 2026-02 后突然全线崩塌（沙特 10.5→7.3、伊拉克 4.4→1.6、科威特 2.56→1.15，跌幅 38%–78%；尼日利亚不动、伊朗缓降），要求同样标注历史事件竖线，**并明确「事件若影响整个 OPEC，上下 grid 都要加竖线」**。
> 根因（EIA 检索确认）：2026-02-28 中东军事行动（伊朗冲突）+ 霍尔木兹海峡事实性关闭，中东多国（沙特/伊拉克/科威特/阿联酋）关停原油生产 → OPEC 全线供给冲击；Brent 1Q26 自 $61 冲至 $118，2026-06-18 美伊 MOU 重开海峡后回补。此事件属全 OPEC 范围，故上下两格都画竖线。
> 修法：`dashboard.js` 的 `opecMonthly` 渲染器（双格：上格=沙特、下格=其余十国）series 改用 `.map(function(m,idx){…})`，加 `if(isTop||idx===1)` 条件——`isTop`（沙特，上格）带标签 `霍尔木兹关闭 26/02`，`idx===1`（伊拉克，下格首序列）仅画线不重复标签；其余下格序列不画。`verify_opec_tail.js` 新增断言：沙特序列 markLine === 1 条且含「霍尔木兹关闭 26/02」、下格（grid 1）必须出现竖线。
> `node --check` → `run.py html`（807081→807633 bytes）→ OPEC verify（ALL OK，沙特/伊拉克均带 marks、其余下格空）与 Non-OPEC DoC verify（ALL OK，3 条竖线无回归）均通过；截图 `output/_shot_opec_11.png`。

> **2026-10-11 追加（B91）**：用户要求把「全球原油产量」图的 **Non-OPEC 线一分为二**为 `Non-OPEC DoC` + `Others`（Others = Non-OPEC − Non-OPEC DoC，元素级相减），即四线 World / OPEC / Non-OPEC DoC / Others（均为 STEO 表 3a/3d 的 **Crude oil** 口径，Others 含阿联酋——按本看板 OPEC=11 国 ex-UAE 口径，且 UAE 自 2026-05 已非 OPEC+，落在 Others 合规）。
> 修法：`dashboard.js` 的 `steoWorld` 渲染器——`const doc=STATE.steoDoCTotal`（72 月含预测）、`others=n.map((v,i)=> v!=null&&doc[i]!=null ? v-doc[i] : null)`；datasets 由 3 条（World/OPEC/Non-OPEC）改为 4 条（World 蓝 `#2563eb` 2.6 / OPEC 红 `#dc2626` / Non-OPEC DoC 琥珀 `#d97706` / Others 紫 `#7c3aed`，后三者 1.9）；`all` 数组纳入 doc+others 做 y 轴自适应。DIMS `worldq` 页尾数据源改为「表 3a 三条 Crude oil 行 ＋ 表 3d 的 Non-OPEC DoC 10 国合计」。
> 校验：新建 `tools/verify_world.js`（playwright + `Chart.getChart`）——断言 4 序列齐全、无「Non-OPEC」单线、2026-09 恒等式 `World(75.97) = OPEC(20.80) + DoC(14.05) + Others(41.12)`、Others 全 72 月非负、颜色互异、无 JS 报错。`node --check` → `run.py html`（807633→808248 bytes）→ `verify_world.js` / `verify_opec_tail.js` / `verify_nonopec_doc.js` 均 ALL OK（无回归）；截图 `output/_shot_world_4line.png`。

## Non-OPEC DoC 图同步换源：MOMR → STEO 表 3d 10 国（2026-10-11）

紧接 OPEC 图换源，用户要求把「Non-OPEC DoC 原油产量」也换成 `3dtab` 的
**`OPEC+ other participants total`** 段（截图给出：Azerbaijan/Bahrain/Brunei/Kazakhstan/
Malaysia/Mexico/Oman/Russia/South Sudan/Sudan）。

**核实结论：与现行 MOMR DoC 是同一份 10 国清单**（STEO 表 3d 脚注 (b) 后半句逐字可证），
且证据链完整：
- **恒等**：10 国之和 == `copr_opecplus_other`（maxAbs 0.0000，历史段 57 月 0 违例）。
- **量级互证**：STE 2026-08 合计 **13.94** vs MOMR 2026-08 **13.97**（差 0.03，
  二手来源 vs EIA 自估的正常差异）；2026-09 = **14.05**。
- ⚠️ 分国行**只有历史段**（2026-10 起预测月全空格）；合计行含预测段（2027-12 = 16.11 量级）。
- 俄罗斯全史 **8.72–10.07**（MOMR 31 月只有 8.7–9.5；2022 年 >10 的头部是换源后新增可见区间）
  → 上格 y 轴由 8.5–9.75 变为 **8.5–10.25**（数据驱动取整）。

**换源内容**（`SUPPLY_RENDERERS.nonOpecDoCTotal` 重写，镜像 OPEC 图换源）：
- **数据链**：`steo_monthly.py` 新增 `DOC_MEMBERS`（10 组 `copr_*` 代码）+
  `DOC_TOTAL_CODE=copr_opecplus_other` + `extract_doc_members()`（脚本内自验恒等）→
  json `docMembers` / `docTotal` → `build_dataset` 注入 `steoDocMembers` / `steoDoCTotal` /
  `steoDoCMeta`（归 `world.json` 域）。
- **轴**：截到 `steoLastHistorical` → **57 月 2022-01~2026-09**（比 MOMR 版早 26 个月、晚 1 个月）。
- **布局/色板不变**：上格俄罗斯 / 下格九国、`endLabel`+`shiftY`、axisPointer.link、
  与 OPEC 双格图并排等高（grid 逐像素对齐断言保留）。
- **徽章**：`STAT_MAP.nonOpecDoCTotal` 重接 `{v/d: steoHistCut(steoDoCTotal/steoMonths)}`
  → 「合计 14.05 · 截至 26/09」（旧为 MOMR「合计 13.97 · 截至 26/08」）。
- **页尾**：三段 `.sline` → 单段（数据源 STEO 表 3d + other participants 10 国清单 +
  「不是 OPEC+ 22 国合计」提示 + 分国无预测说明 + 脚本路径）。
- **旧 MOMR DoC 键移除**：`nonOpecDoCMonths` / `nonOpecDoCTotal` / `nonOpecDoCCountries` /
  `nonOpecDoCMeta` 从 build_dataset / dataio / computeDerived 一并摘除；
  `opec_momr.py` 摘出 `run.py EXTRACTORS`（`opec_monthly.json` 存档已于 2026-10-23 移出仓库）。
  至此 opec.json 域只剩剩余产能 + OPEC 年度序列 + Brent 月均价。

**校验**：`tools/verify_nonopec_doc.js` 整体重写——双 xAxis 57 月 / 10 条 series 归属+颜色+
末值（俄罗斯 8.77 等，index 56）/ endLabel+shiftY / 图例 10 项 / 徽章 `合计 14.05 · 截至 26/09`
且不含旧值 13.97 / 页尾无 `secondary sources` 与 `原 opec_momr.py（已下线，口径见「已下线口径留档」）` / **恒等 10 国==合计
（nChecked=57，maxAbs 0.0000）** / 与 OPEC 双格图 grid 逐像素对齐 / 等高 / 无报错。
5 脚本回归全 **ALL OK**。截图 `output/_shot_nonopec_steo.png`。

---

## OPEC 月度产量图：9 国 → 12 国（2026-10-10）

用户："把 Congo / Equatorial Guinea / Gabon 三个国家的数据补全，这样 OPEC 所有成员国都有了。
虽然 UAE 退出 OPEC，但它的数据在 MOMR 里还是在 OPEC 部分出现，那么在我的这张图里也把他当 OPEC 的来处理。"

**核查结论：数据层本来就有这 3 国**。`原 opec_momr.py（已下线，口径见「已下线口径留档」）` 的 `COUNTRIES` 自一开始就列全 12 个成员国，
`data/processed/opec_monthly.json（存档，2026-10-23 已移出仓库）` 的 `countries` 里 **Congo / Equatorial Guinea / Gabon 已是 34 月完整序列**
（2023-11 ~ 2026-08；末点 mb/d：刚果（布）0.275 / 赤道几内亚 0.047 / 加蓬 0.217）。
此前只是前端 `opecMonthly` 的 `major` 数组只列了 9 国——属**纯前端补齐**，无需重跑 extract。

**三处改动**：
- `dashboard.js` `opecMonthly.major` 追加三项（英文名须与 json 键一字不差）：
  `Congo 刚果（布） #2563eb` / `Equatorial Guinea 赤道几内亚 #facc15` / `Gabon 加蓬 #f43f5e`。
  三色与既有 9 色不重；三者均落入**下格**（TOP 只含沙特，故非沙特全归 grid1）。
- UAE 已在原 9 国之列（键 `UAE`、中文「阿联酋」），按用户要求**维持 OPEC 处理**，无需改动。
- `tools/verify_opec_tail.js`：`EXPECT` 增 3 项、series 数 `9→12`、图例数 `9→12`、避叠说明改"下格 11 线"。

**校验**：`run.py html` 重建 → `verify_opec_tail.js` → 12 条 series 全在（3 新国度 grid1、颜色/末值对上）、
下格 Y 0–4.5、ERR0RS=0 → **ALL OK**；`verify_opec_tail` / `verify_world_quarterly` /
`check_eia_series` / `verify_footers` 回归全绿。仅本地未 push。

> ⚠️ 三小国产油量极低（赤道几内亚 ~0.05、加蓬 ~0.22、刚果 ~0.28 mb/d），在 0–4.5 下格里贴底；
> `moveOverlap:'shiftY'` 只让**末点标签**纵向错开，折线本身仍贴近基线，属数据真实分布，非渲染问题。

---

## 新增图：「Non-OPEC DoC 原油产量 (百万桶/日, 月度)」（2026-10-08，终态命名 10-09）

> **2026-10-09 再改名（终态）**：曾叫「OPEC+ 非 OPEC 参与国原油产量」，10-08 晚一度改成
> 「OPEC+ 原油产量」，**那是错的**——数据只有 10 个非 OPEC 参与国，不是 22 国全联盟。
> 现定为 **「Non-OPEC DoC 原油产量 (百万桶/日, 月度)」**（当时仍含粗线「Non-OPEC DoC 合计」+ 右轴，
> 后于同日「再改造」中删除，见下），与图2 里那条 `Non-OPEC DoC` **同名同口径**，两张图可互相印证。
> ⚠️ 这条线仍是 `Total Non-OPEC DoC`（**10 个非 OPEC 参与国**，2026-08 = 13.97），
> **不是** 22 国的 `Total DoC`（38.06）。卡内页尾「本图不是 OPEC+ 22 国合计…」**保留**。
> 若真要做 22 国的 OPEC+ 图：换 `Total DoC` + 右轴改 0–40，并把 `Total DoC` 解析加回来
> （注意先排除同页散文行 `Total DoC crude oil production averaged…`）。
> （右轴 `y2` 0–15 为后续改造前的过渡态——合计线删除后右轴整体移除，下方副作用随之消失。）
> 原右轴 0–15 的副作用：合计实际区间 13.782~14.669，落在轴高 **92%~98%**，0.89 mb/d 的波动
> 只占约 13px，粗线看起来几乎是平的——仅作历史留档，当前图已无此轴。

> **2026-10-09 再改造（删合计线 + 右轴、改实线、加内联末端标签）**：用户要求把图简化——
> ① 删掉「Non-OPEC DoC 合计」粗线（合计值由卡头徽章承载；全球图 2026-10-10 月度化时已移除
> DoC/Others 拆分线），**右轴 `y2` 随之移除**；② 四国细线由虚线改**实线**
> （删 `borderDash`）；③ 四国各加一枚**内联末端标签**（白心圆点 + 短引线 + **仅最新值**，不显示国名；
> 绘图区内、贴末点**左侧**右对齐，防溢出）；④ 右侧标注槽不再需要（`makeInlineTailPlugin`
> 替代 `makeOpecTailPlugin`）。图现为**单左轴 0–10.5**，无右 padding；顶部启用 Chart.js 图例，
> 中文短名、颜色与折线一致，可点击切换显示/隐藏。
> ⚠️ 此前「右轴 0–15 让合计线几乎平直」的副作用也一并消失。

> **2026-10-10 再改造（改 ECharts 双格：上格俄罗斯 / 下格其余九国，共享 x 轴）**：
> 单左轴 0–10.5 时俄罗斯 8.72–9.48 占满上半区，而哈萨克斯坦 1.18–1.90 / 墨西哥 1.45–1.63 /
> 阿曼 0.75–0.93 全被压在底部约 18% 的高度内，线型无从读起。改为 **ECharts 两个 grid 上下叠放**：
> 上格只画俄罗斯（Y **8.5–9.75**），下格画其余九国（Y **0–2.0**），两条 xAxis 共用同一份 31 月，
> `axisPointer.link:[{xAxisIndex:'all'}]` 让十字准线上下贯穿。
> ⚠️ **下格起点取 0**（2026-10-10 再改）：九国里有苏丹 0.021 / 巴林 0.065 / 文莱 0.090 这种 0.02–0.1 量级，
> 0 基线压掉 0–0.5 会把它们整条裁掉；故下界取 0（与 OPEC 图下格 0–4.5 一致）。
> 贴底的苏丹/巴林/文莱/南苏丹是真实量级，靠 `labelLayout:{moveOverlap:'shiftY'}` 让末点标签错开避免叠字。
> 末点标签改用 ECharts 原生 `series.endLabel`（只显示数值，国名交给顶部图例）——分格后三条低位线
> 在 0–2 轴上天然分开（末点 1.81 / 1.45 / 0.92），不再需要 `makeInlineTailPlugin` 的扇出逻辑。
> ⚠️ **`grid` / `xAxis` / `yAxis` 必须显式写 `gridIndex`**：多 grid 时省略它，ECharts 会在
> `setOption` 阶段抛 `Cannot read properties of undefined (reading 'type')` 导致**整图白屏**
> （与 `rigWorld` 双格图同一个坑）。ECharts 未加载时回落 Chart.js 单轴版，不白屏。
> ⚠️ 轴步长取 **0.25**：取 0.5 会把上格上界从 9.75 顶到 10、下格从 2.0 顶到 2.5，线又被压扁一半。

供给侧「产量与产能」组在 OPEC 12 国图之后并列一张 **`nonopecdoc`**，现为 **ECharts 双格**
（**上格俄罗斯 / 下格其余九国，共享 x 轴；合计线已删除**）。**合计口径经用户确认取
`Total Non-OPEC DoC`（10 个非 OPEC 参与国，2026-08 = 13.97 mb/d），不是 `Total DoC`
（OPEC+ 22 国，38.06）** —— 后者才是字面意义的 "OPEC+ 合计"，已明确不用；该合计现仅由
本图卡头徽章承载（图2 全球图 2026-10-10 月度化时已移除 DoC 线），本图不单列。
国别细线四条（均为实线）：俄罗斯（8.72）/ 哈萨克斯坦（1.81）/ 墨西哥（1.45）/ 阿曼（0.92）。

**解析侧（`原 opec_momr.py（已下线，口径见「已下线口径留档」）`）**：新增 `NON_DOC_COUNTRIES`（10 国全解析，
不只画的那 4 个——多解析 6 个是为了做恒等校验）与 `NON_DOC_TOTAL` 行。判名顺序
`Total Non-OPEC DoC` → `Total OPEC` → OPEC 12 国 → 非 OPEC 10 国。
输出 `opec_monthly.json` 新增三键：`nonOpecDoCMonths` / `nonOpecDoCTotal` /
`nonOpecDoCCountries`。

**四个口径坑（改这块必读）**：

1. **起始月晚 3 个月，x 轴绝不能共用**。`Total Non-OPEC DoC` 与 10 国国别行是 OPEC
   **2024 年 5 月 MOMR 才加进表 5-7** 的（实测 2024-02 / 2024-04 两期只有 `Total OPEC`），
   所以覆盖 **2024-02 ~ 2026-08（31 月）**，比 OPEC 12 国的 34 月短 3 个月。
   挂到 `opecMonths` 轴上前 3 个点全是空值。校验脚本专门断言
   `nonOpecDoCMonths.length !== opecMonths.length` 防两轴被混。
2. **散文行陷阱**：表 5-7 页里有一句 `Total DoC crude oil production averaged 38.05 mb/d...`
   的正文，同样以 "Total DoC" 开头。本脚本**不解析 `Total DoC`**，且所有行都过
   `len(nums) >= N+1` 的数值个数闸门，散文行被自然滤掉；日后若要启用 `Total DoC`
   必须先排除散文行，否则会把正文当数据。
3. **South Sudan / Sudan 前缀不互踩**：`"South Sudan".startswith("Sudan")` 为 False，
   逐国 `startswith` 判名安全；但**新增国名时必须复查前缀关系**（如假想的 "Sudanese Republic"）。
4. **`Total Non-OPEC` 会前缀命中 `Total Non-OPEC DoC`**：判名必须用完整行名
   `Total Non-OPEC DoC`，不能只写 `Total Non-OPEC`。

**前端（`dashboard.js`）**：
- **末端标注**：**nonopecdoc 自 2026-10-10 起改走 ECharts 原生 `series.endLabel`**（只显示数值，
  国名交给顶部图例），不再用 `makeInlineTailPlugin`——双格后九条低位线里，哈/墨/阿曼在 0.9–1.8 段天然分开，
  但苏丹/巴林/文莱/南苏丹贴底（0.02–0.13），靠 `labelLayout:{moveOverlap:'shiftY'}` 自动错开避免叠字。
  OPEC 12 国图**同样已改 ECharts 双格**（上格沙特 / 下格十一国），走同一套 `series.endLabel`；
  `makeInlineTailPlugin`（绘图区内联、无右侧槽、标签贴末点**左侧**右对齐防溢出）现只在
  **ECharts 未加载时的回落分支**里被 OPEC 图调用，Non-OPEC 图已完全不用。
  `makeOpecTailPlugin`（右侧标注槽 + 扇出 + 合计气泡）已不再被调用，暂留作可复用工具。
  两个 Chart.js 插件都是顶层公共函数（⚠️ **函数声明不能写进 `SUPPLY_RENDERERS` 对象字面量** ——
  对象属性必须是 `key: value`，裸 `function f(){}` 是语法错误，实测整页 `Unexpected identifier`
  导致**所有图**都不渲染）。各传不同 `pluginId`（`opecTail` / `nonDocTail`）——
  Chart.js 按 id 注册插件，同 id 互相覆盖。
- **ECharts 双格要点**：`grid` 两项取自共享 `ec2Grid()`（上格 `top:44,height:145` /
  下格 `top:207,bottom:48` → 两格均 **145px**），`xAxis`/`yAxis` 各两项且
  **必须显式 `gridIndex`**；`axisPointer.link:[{xAxisIndex:'all'}]` 贯穿两格；
  ⚠️ **有 `height` 的 grid 不能用 `H−top−bottom` 反推像素高**（校验脚本曾把 145 算成 314），
  必须先判 `g.height != null`。
  顶部 `legend` 4 个中文项、`icon:'circle'` 与 Chart.js 的 `usePointStyle` 视觉一致；
  实例挂 `ecCharts[id]`（不是 `charts[id]`），重绘前 `dispose()`；`!window.echarts` 时回落 Chart.js。
- 图卡 `nonopecdoc` 在 `prodcap` 组里排在 `opec` 之后、`worldq` 之前。
- `STAT_MAP.nonOpecDoCTotal` / `SUPPLY_RENDERERS.nonOpecDoCTotal` /
  `computeDerived` + SNAPSHOT 回落四处登记（漏 `computeDerived` 只在「拉取实时」后暴露）。
- **双格轴界**（不再有单左轴 0–10.5）：上格俄罗斯 **8.5–9.75**、下格九国 **0–2.0**（下界取 0，
  因九国里有苏丹 0.021 这种贴底量级，压掉 0–0.5 会裁掉它们），步长均 0.25。
  合计线删除后不再需要第二轴，右轴 `y2` **已移除**。

**自洽恒等（校验断言用）**：10 国分项之和 == `Total Non-OPEC DoC`（逐月，容差 0.05，
实测 maxAbs = 0.002，31/31 月全覆盖无缺月）。

校验：`tools/verify_nonopec_doc.js` —— 2026-10-10 已按 ECharts 双格重写（实例读 `ecCharts`）：
2 个 `grid` / 2 条 `xAxis` 同 31 月且 `gridIndex` 显式 / 上格 Y 8.5–9.75、**下格 Y 0–2.0**（下界取 0，含 0.02 量级小国）且两格上下界不同 / **上下两格像素高之差 ≤4（实测 145 vs 145）** /
10 条 series 的归属（俄罗斯→grid0，其余→grid1）、颜色、末值、`endLabel` 开启 /**下格九线均 `moveOverlap:'shiftY'`** /
图例 10 个中文项 / `axisPointer.link` 已配 / **`gridsAligned`**（与 OPEC 图 grid 签名逐项相等）+ 两图 `boxH` 均 400 /
10 国恒等 maxAbs 0.002 / 无 pageerror → **ALL OK**；
`verify_opec_tail`（9 国图：无右轴 / 9 国实线 / 内联标签只显示数值且无溢出）回归 **ALL OK**、
`verify_world_quarterly` / `verify_footers` / `check_eia_series` 均 0 错。

---

## Brent 期限结构图空白：根因是 run.py 选错了解释器（2026-10-07）

**现象**：地缘 tab「Brent 12 个月期限结构（近月−远月）」整张空白，卡内只剩一句「本期未取到 Brent 期限结构数据」；
`data/dataset/prices.json` 里 `brentTermMeta.error = "缺少依赖 yfinance/pandas"`，`brentTerm` 全为 `null`。

**排查（否掉两条假线索）**：
- 不是 Yahoo 限流：直连 `query1/query2.finance.yahoo.com` 拿 `BZ=F`，在**装了依赖的 `.venv` 里**直跑 `fetch_with_status()`，
  一次返回 232 个交易日、末值 `+16.46 $/bbl` —— 数据源与 `brent_term.py` 逻辑都是好的。
  （顺带发现裸 urllib 直连会吃 429，但那只是测试路径，不是流水线路径。）
- 不是渲染 bug：`term_geo` 的空数据来自 `prices.json`，是数据层先空了。

**真因**：`run.py` 的 `cmd_dataset()` / `cmd_html()` 硬用 `sys.executable`。日常直接从终端敲 `python run.py ...` 时，
PATH 里的 `python` 是**系统 3.14.3**，它没装 yfinance / pandas；而项目自带的 `.venv`（**3.13.12**）里五个依赖齐全。
于是 `brent_term._require_deps()` 判定缺依赖、优雅降级为空 —— 脚本没报错、流水线继续跑完，只在页面上留一句提示，
属于「静默空图」。

**修法（一次改在 run.py 层，三条命令都吃）**：
1. 新增 `DATASET_DEPS = ("yfinance", "pandas")`，把原有的 `_has_deps(python, deps=EXTRACT_DEPS)` 通用化（加 `deps` 参数）。
2. 新增 `_dataset_python()`，候选顺序 `$DATASET_PYTHON > .venv/bin/python > sys.executable`，返回**第一个真正能 `import` 这些包**的解释器。
3. `cmd_dataset` / `cmd_html` / `cmd_build` 全部改走 `_dataset_python()`，**build 两步共用同一个解释器** ——
   只让 dataset 换 3.13、html 仍用 3.14 会出现「数据来自 3.13、渲染结果来自 3.14」的浮点漂移，产物就不是字节可复现的了。

**两个附加收益**：`.venv` 是 3.13.12，正好满足 `EXPECTED_PY=(3,13)` 的字节复现前提；以后再往 `.venv` 补任何刷新期依赖，run.py 会自动认领，不用再改命令。

**验证**：`python run.py build`（用系统 3.14 启动）日志首行即 `build 使用解释器: .../.venv/bin/python (python 3.13.12)`，
随后 `[term] Brent 12M 期限结构：232 个交易日，最新 2026-10-06 -> +16.46 $/bbl（远月合约命中 11/25）`；
`brentTermMeta` 变 `ok:true / points:232 / error:null`；Playwright 打开页面切地缘 tab，
`term_geo` 单数据集非空 **252** 点、末值 **15.87**、`placeholder:false`、pageerror **0**。

**坑**：`_require_deps()` 返回 `None` 时 `brent_term` 是**优雅降级**而不是抛错 —— 这类"缺依赖"故障永远不会在流水线里报错，
只能靠 `brentTermMeta.ok` 和页面点检发现。以后遇到某张图莫名空白，先看 `data/dataset/prices.json` 里对应 `*Meta` 的 `error` 字段。

---

## OPEC 剩余产能图改成双轴：叠加 Brent 月均价（2026-10-07）

**需求**：在「OPEC 有效剩余产能 (百万桶/日, 月度)」图上叠一条 Brent 价格折线，走右轴。

**先看数据对不对齐**：这张图 x 轴是 **2015-01 → 2027-12（156 个月，含 EIA 预测段）**，而看板里那个日度 `brent`
（FRED `DCOILBRENTEU`）的抓取起点是 `config.START_DATE = "2024-01-01"` —— 直接拿来按月聚合只能覆盖右侧 1/4，
所以选择**单独再拉一份 2015 起的 Brent**，而不是放宽 `START_DATE`。

**数据层（四处改动）**：
1. `config.py` 新增 `BRENT_MONTHLY_START = "2015-01-01"`，注释里写明「绝不能并进日度日期轴」。
2. `src/fetch/prices.py::fetch_brent_monthly()` → `{YYYY-MM: v}`，取 FRED `DCOILBRENTEU` 日度后按 `date[:7]`
   分桶求均值。⚠️ FRED 的 `series/observations` 接口**不接受 `frequency=monthly`**（实测 400 Invalid value），
   所以月均只能自己算。
3. `dataio.GROUPS` 把 `brentMonthly` 归到 **opec.json 域**（不是 prices.json）—— 它只服务这一张图，
   归到价格基准域会被误当成"价格"再被别处引用。
4. `build_dataset.py` 在 `[1/6]` 单独取数（`prices.fetch_brent_monthly()`），**不进 `raw_prices`**，
   否则整屏日度图的横轴都会被拉到 2015。

**前端**：`opecSpare` 渲染器加第二个数据集 —— `type:"line"` + `yAxisID:"y1"`；`order` 柱 1、线 2（Chart.js 按
序号升序绘制，序号大的画在上，所以折线盖在柱子上面）；配色 `#7c3aed` 紫，刻意避开柱子蓝与**预测段橙**
（别把两种橙色语义搅在一起）；`endTag:{on:true,n:2}` 让柱与线各画一枚末值气泡（插件自带竖向避让）。
`computeDerived` 里也补了 `brentMonthly` —— 对象型静态键同样要「GROUPS + computeDerived」双登记，
否则开页自动拉取后 STATE 被整体替换、右轴折线整条消失。

**渲染前的一个坑**：`scales.y1.ticks:{font:{size:10}}` 这段末尾必须写 **6 个右括号**（font / ticks / y1 / scales /
options / 图表配置对象）。写成 5 个时 `node --check` 报 `Unexpected token ')'`，
而 `build_html.py` 只是把模板当文本塞进 HTML —— **构建照常成功、产物照常生成**，
错误要到浏览器里整段脚本解析失败才暴露（页面一堆空图、控制台一条 pageerror）。
以后加/改渲染器，改完先 `cp src/pipeline/templates/dashboard.js /tmp/d.js && node --check /tmp/d.js`。

**校验**：`tools/verify_spare_price.js`（22 条）：两个数据集的 `yAxisID`/`type`、price 逐点等于
`STATE.brentMonthly[同月键]`、141 点覆盖、末点 2026-09 = 114.08 **早于**末月（价格止于 2026-09 而柱排到 2027-12，
这是预期不是错位）、量级 18–123、右轴右侧+标题美元/桶+刻度为数字、页尾三段逐字全等、全 tab 回归、无空图。

**口径提醒（写在页尾里）**：这条线是 **FRED Brent 现货月均**（`DCOILBRENTEU`），**不是期货**。
看板里唯一的期货口径是地缘 tab 的「Brent 12M 期限结构」（Yahoo `BZ=F` 近月连续 减 远月合约）。
真要换成近月期货月均，得新接一条 yfinance 序列再按月聚合，别和现货混标。

---

## Brent / WTI 价格换源：FRED → EIA 日度现货（2026-10-08）

**为什么换**：FRED 的 `DCOILBRENTEU` / `DCOILWTICO` 是 EIA 这两条序列的**转载** —— 抽样 12/12 个
交易日的值**完全相同（差 0.00）**，所以换源是**零口径风险的平移，不是换口径**。换的是更新速度：

- FRED 平台**每周批量补更一次**：2026-10-07 22:36 只到 09-29，次日 07:33 才补齐到 10-06，
  日常最长滞后 7 个自然日；EIA 直连是 **T+1**。
- 代价实例：10-02 Brent 从 114.82 跳到 **135.51（+18.9%）**，而快照停在 09-29 的 113.96 ——
  整根暴涨在跳变事件流、20 日波动率与压力分里全部缺失。

**改动**：`src/fetch/prices.py` 的 brent/wti 改走 EIA 日度 `PET.RBRTE.D` / `PET.RWTC.D`；gas 仍走
FRED（周度，唯一源）；`fetch_brent_monthly` 底层同步换成 EIA（避免"同一事实抄两处"）。
EIA 任一条拿不到就**两条一起**回落 FRED（只回落一条会让 BW 价差变成"新 vs 旧"的假价差）。

**⚠️ 两个实施要点（改这块必读）**：

1. **必须本地按 `START_DATE` 过滤**：EIA v2 的 `seriesid` 接口实测**不认 `start`/`end`**
   （传了仍从 2006 年起返回）。不过滤会把日度轴从 2024 一路拉回 2006。
   只能靠 `length` 限流 + 本地过滤，两者缺一不可。
2. **日度价格绝不能进 `EIA_SERIES`（周度表）**：`fetchEIA()` 用那张表的 period 并集生成「周轴」，
   混入日点会让周轴从约 2297 个周点膨胀到几千个日点，所有周度图 x 轴整片塌掉。
   所以日度油价走**独立注入**的 `EIA_PRICE_IDS`，`EIA_SERIES` 原样不动。

**影响（数据变真实，属预期不是 bug）**：`latest_date` 09-29→10-06；brent 113.96→125.44；
**vol20 35.82→78.45**（尾部不再是平坦填充）；spread_bw 17.80→29.20；跳变事件 165→167。

**顺带修掉的性能退化**：换源后「拉取实时」实测 **43.2s** —— 多了一个 EIA 请求，默认拉 5000 个
观测（2006 年起），而 `serve.py` 是单线程串行。给 `/api/eia` 加了 `length` 限流
（`EIA_DAILY_LENGTH=1500`）后降到 **13.1s**。

**校验**：新增 `tools/verify_price_live.js`（真实链路，非桩，守"状态栏出现『油价EIA日度』+ 周轴
未膨胀 + 日轴未拉长"）；`tools/check_eia_series.js` 加 4 条断言（含"周度表不得出现 brent/wti"
的反向守卫）。改动价���源后这两个都要跑。

---

## 全球原油产量：世界合计从哪来 / 美国与 OPEC 占比（2026-10-08）

**先看板数据缺什么**：`data/dataset/` 只有 **EIA 美国周度产量**（`eia.prod`，总液体口径）与
**OPEC 12 国月度产量**（`opecMonthly`，MOMR 表 5-7），**没有世界合计** —— 所以"美国 / OPEC 占全球
多少"凭看板算不出来。世界合计**只能取 EIA STEO 表 3d**（`World Crude Oil Production`）；
MOMR 表 5-7 只列 DoC 各国、**没有世界行**（实测确认，别再去那里找）。

核对脚本：`tools/probe_world_production.py`（只读，不进构建链路），
`PYTHONPATH=. .venv/bin/python tools/probe_world_production.py`。

> 本节原先只讲**年度/单季度**的 3d 口径。**2026-10-08 起已有更完整的季度世界产量图**
> （`世界 / OPEC / 非 OPEC` 三条 Crude oil，2025Q1~2027Q4，来源 STEO 表 3a，见下一节），
> 本节的 3d 数字（美国 / OPEC 占比、逐国拆分）继续作为**地区层面**的补充口径保留。

**结论（EIA STEO 2026-09 表 3d，单位 mb/d，原油口径）**：

| 口径 | 世界合计 | 美国 | 占全球 | OPEC* | 占全球 | OPEC+ | 占全球 |
|---|---|---|---|---|---|---|---|
| 2025 年均 | 78.99 | 13.66 | **17.3%** | 24.63 | **31.2%** | 33.32 | 42.2% |
| 2026 年均（估） | 74.78 | 13.83 | 18.5% | 19.92 | 26.6% | 28.95 | 38.7% |
| 2026 Q3 | 74.55 | 13.88 | 18.6% | 19.44 | 26.1% | 28.59 | 38.4% |

\* EIA 脚注 (c) 的 OPEC 只有 **11 国、不含阿联酋**（UAE 被归到 "Other Asia"）。
按 OPEC 自口径（12 国含 UAE，MOMR 表 5-7 2025 年 25.11 mb/d）算，占全球 = 25.11/78.99 = **31.8%**，
与上表 31.2% 只差阿联酋一国，量级一致。2026 年低位是情景里的中东非计划停产（STEO 记
OPEC 非计划停产 2026 Q2 达 10.71 mb/d），不是统计误差。

**OPEC 之外的地区（2025，占全球原油）**：俄罗斯 9.12（11.5%）、伊拉克 4.33（5.5%，OPEC）、
伊朗 3.38（4.3%，OPEC）、哈萨克斯坦 1.75、科威特 2.49（3.2%，OPEC）、阿联酋 ≈3.1（3.9%，OPEC 自口径）、
墨西哥 1.43、尼日利亚 1.41、利比亚 1.29、委内瑞拉 0.94、阿尔及利亚 0.93、阿曼 0.77。

**四个口径坑（改这块必读）**：

1. **分母口径**：表 3d 是 **crude oil**（原油+凝析油）；表 3c 是 **total petroleum and other
   liquids**（含 NGL / 炼厂原料 / 生物燃料）。美国 NGL 占比高，所以美国在总液体口径占 22%、在
   原油口径只有 17%。两个数不能混着比。
2. **OPEC 成员数**：EIA 算 11 国（不含阿联酋），OPEC 自己算 12 国（含）。同一份"OPEC 占比"
   因此有 31% / 35% 两种答案，取决于用谁的口径 —— 引用时必须写明是哪国口径。
3. **同名行取错**：表 3d 一页里有 4 行都带 "OPEC total"（产量 / 产能 / 备用产能 / 非计划停产），
   而且**粗油产量的那行没有点线分隔符**（`OPEC total (c) 24.04 ...`），其他行有。只按点线劈、
   或不看行名就取第一个，都会取到"产能"27.95 那组。探针里用"标签前缀匹配 + 只存首现"规避。
4. **别用一个大正则**：`(\s*-?[\d,]+){6,}$` 这种嵌套量词碰到 "World index, 2015 Q1 = 100 ..."
   那行长会指数级回溯，实测进程被 OOM-kill（exit 137）。已改成"标签前缀 + tokenizer"。

---

## 全球原油产量（月度，EIA STEO base tables 表 3a）（2026-10-10 月度化）

> **2026-10-10 月度化（整体换源）**：数据源由 STEO 月报 PDF 的**季度**列，换成 STEO
> **base tables Excel**（`data/raw/eia_steo/oct26_base.xlsx` / `3atab` sheet）的**月度**列 ——
> **72 个月 2022-01~2027-12**，分辨率远高于季度。此前「世界合计没有月度」的结论被推翻：
> **PDF 版式里确实没有月度列，但 base tables Excel 有**（月度才是 STEO 的原始分辨率）。
> - **三条线**：World / OPEC / Non-OPEC 的 **Crude oil** 行（原油，不含 NGL）。
>   旧季度口径的 `Non-OPEC DoC` / `Others` 两条拆分线**随季度键一并移除**（它们依赖 MOMR，
>   与月度口径不同源；DoC 明细仍保留在独立的「Non-OPEC DoC 月度图」里）。
> - **预测边界**：取自 Dates sheet 的 `Last Historical Month`（= 2026-09），**2026-10 起为
>   STEO 预测段**；三条线同源同表，**三者**的预测段都画虚线（首虚线段 = 段 56，即 2026-09→2026-10）。
> - **y 轴**：数据驱动非 0 起点 —— 三条线实际跨度 **OPEC 16.41（2026-05 深坑，STEO 情景里的
>   中东非计划停产）~ World 83.03（2027-11）**，按 min/max 向 5 的整数倍取整 → **15–85**，
>   并加 `baseNote`「轴起点 15（非 0）」虚线基线。⚠️ 别按 2022 年的 OPEC（23.79）估计下界，
>   2026-05 的深坑会把 min 拉到 16.41。
> - **x 轴**：月份键 `YYYY-MM` 经 `fmtX` 渲染为 `22/01` 式；72 个点、刻度上限显式压到 12
>   （约每半年一个），不压会糊成一片。
> - **徽章**：2026-10-11 起标**最新实际值**「75.97 · 截至 26/09」（经 `steoHistCut` 截断到
>   末个历史月 2026-09；末月经 `fmtX` 渲染为 YY/MM）；此前是预测末点「82.97 · 预测至 27/12」。
> - **恒等**：OPEC + Non-OPEC == World 逐月成立（源表 72 个月 0 违例，容差 0.05）。
> - 旧季度键 `steoQuarters / steoWorld / steoOpec / steoNonOpec / nonOpecDoCQuarter / othersQuarter`
>   已从 build_dataset / dataio 一并移除；季度脚本 `steo_world.py` 废弃不再调用
>   （也不再登记进 run.py 的 EXTRACTORS，月度脚本已登记；脚本已于 2026-10-23 移出仓库）。

> **2026-10-11 徽章改实际值 + 页尾再精简**：
> ① **徽章**由预测末点「82.97 · 预测至 27/12」改为**最新实际值**「**75.97 · 截至 26/09**」——
>   新增 `steoHistCut()`（dashboard.js），把 `STAT_MAP.steoWorld` 的 v/d 都**截断到
>   `steoLastHistorical`（2026-09）**，`statText` 取"最后一个非空值"自然落在末个历史月上；
>   `prep` 走默认「截至」不写「预测至」。图上的预测段照画不误，只是徽章不再指向预测值。
> ② **页尾**由三段 `.sline` 精简为**单段**，只留数据源描述（逐字）：
>   `数据源：EIA 短期能源展望（STEO）base tables Excel 表 3a 的三条 Crude oil· 提取脚本
>   src/fetch/supply/steo_monthly.py`（口径说明由 2026-10-10 节与本 README 承载，不再挤在页尾）。

> **2026-10-08 晚间改名**：标题「全球原油产量：世界 / OPEC / 非 OPEC (百万桶/日, 季度)」
> → **「全球原油产量 (百万桶/日, 季度)」**；图例改为英文短名 **World / OPEC / Non-OPEC**；
> 页尾从三段（数据源/口径/注意）精简为**单行**
> `数据源：EIA 短期能源展望（STEO）月报表 3a Production 段的 Crude oil 行 · 提取脚本
> 原 steo_world.py（已下线，口径见「已下线口径留档」）`。
>
> **2026-10-10 改**：
> ① x 轴标签从 `25Q1` 改为参考图1 的**季度首日日期格式** `25/01/01`
> （`2025Q1` → `2025-01-01` → `fmtX` → `25/01/01`）；
> ② **World / OPEC 预测段折线改虚线** `borderDash:[6,4]` + `segment.borderDash`。
>   ⚠️ **虚线起点是 2026Q3，不是 2026Q1**：STEO（2026-09 版，数据截止 ~2026-09-03）里
>   2025Q1~2026Q2 是**历史实际值**（PDF p45 脚注：historical vs forecast 分界），
>   自发布月当季（2026Q3）起才是预测/估计值 —— 2026Q1、2026Q2 都是实际值，保持实线。
> ③ **y 轴沿用「美国原油产量」图的 `level:true` 标准**：启用 `baseNote` 插件，在 y 轴非 0 起点
>   处画一条**虚线基线**并标注「轴起点 10（非 0）」，避免读者把曲线下方误读为面积/量级。
> Non-OPEC DoC / Others 为 MOMR 月度聚合（止于 2026Q2）已实现实线，不虚化。
> **数据、口径、恒等校验均未动**——仍是完整季度键 `2025Q1` 按 index 取值；
> 卡内徽章仍是「82.85 · 预测至 2027Q4」（全季键，未随轴缩短）。

> **2026-10-09 Non-OPEC 拆分**：原「Non-OPEC」一条线拆成两根——
> **`Non-OPEC DoC`**（= OPEC+ 里的 10 个非 OPEC 参与国，即 MOMR 表 5-7 的
> `Total Non-OPEC DoC`，月度→季度日均，琥珀点线）和 **`Others`**（= Non-OPEC − DoC，
> 残差，青点线）。恒等式变为 **OPEC + DoC + Others = World**（逐季，maxAbs 0.010）。
> **三个限制（改这块必读）**：
> 1. **止于 2026Q2**：MOMR 月度只到 2026-08，凑不出 2026Q3 的完整季（缺 9 月），
>    所以 DoC/Others 只有 6 个点（2025Q1~2026Q2），2026Q3 起为 null——**不补零、不外推**；
>    World/OPEC 仍是 12 点（含 STEO 预测段）。
> 2. **季度聚合只取完整季**：`原 opec_momr.py（已下线，口径见「已下线口径留档」）` 里 3 个月齐全才平均，缺月的季度一律不产出
>    （EIA 的季度值是"该季度日均"，拿 2 个月均值冒充会偏）。月度终点随月报更新而变，
>    完整季度数不写死。
> 3. **Others 是残差**：EIA 的 Non-OPEC（季度、含预测段口径）减 MOMR 的 DoC（月度二手来源），
>    跨源误差全被吸进 Others。量级可靠（≈40 mb/d，含阿联酋/美国/巴西…），别当精确值引用。
>    新键：`nonOpecDoCQuarter`（`{label,quarter}`）+ `othersQuarter`（`{label,quarter}`），
>    归 `world.json` 域；校验 `tools/verify_world_quarterly.js` 的 nn 断言是 `[12,12,6,6]`。

> **2026-10-09 视觉对齐「美国原油产量」图**：① 去掉蓝色面积填充（`fill:false`）
> ② 去掉折线上的圆点（`pointRadius:0`）③ 四条线全部改实线（删 `borderDash`）。
> 参照物是 `SUPPLY_RENDERERS.__default__`——美国图因 `level:true` 天然 `fill:false`、
> `pointRadius:0`、无虚线，本图照抄这套。**代价：四条线只能靠颜色区分了**（原来还可靠
> 虚线/点线），所以刻意保留线宽层级——World 2.6 当主线、其余 1.9——四条线不至于糊成一片。
> `fillFn` / 卡片上的 `fillAlpha:0.2` 自此不再使用。校验加了三条断言：
> `fill===false && hasBg===false`、`pointRadius===0`、`borderDash===null`（四条全过）。

供给侧「产量与产能」组现有三张并列图：

| 图 | key | 数据行 | 覆盖 | 说明 |
|---|---|---|---|---|
| OPEC 原油产量 (百万桶/日, 月度) | `opecMonthly` | STEO base tables Excel **表 3d 的 OPEC 11 国分项**（脚注 c，**不含阿联酋**；合计 `copr_opec` 仅卡头徽章/自洽用，图内不画） | 2022-01 ~ 2026-09（57 月历史段；STEO 分国无预测） | **ECharts 双格**：上格沙特（Y 6.25–11.25）/ 下格十国（Y 0–4.75），两格各 **145px**、总高 400，共享 x 轴、末点仅数值且自动避叠（`moveOverlap:'shiftY'`）；合计线已删；2026-10-11 由 MOMR 12 国换源（见下方专节） |
| **Non-OPEC DoC 原油产量 (百万桶/日, 月度)** | `nonOpecDoCTotal` | STEO base tables Excel **表 3d 的 `OPEC+ other participants` 段**（脚注 b 后半句 10 国；合计 `copr_opecplus_other` 仅卡头徽章/自洽用，图内不画） | 2022-01 ~ 2026-09（57 月历史段；分国无预测，合计含预测段） | **ECharts 双格**：上格俄罗斯（Y 8.5–10.25）/ 下格九国（Y **0–2.0**，下界取 0 含 0.03 量级小国），两格各 **145px**、总高 400，共享 x 轴、末点仅数值、`moveOverlap:'shiftY'` 避叠；合计线已删、右轴已移除；2026-10-11 由 MOMR 换源（见下方专节） |
| **全球原油产量 (百万桶/日, 月度)** | `steoWorld` | STEO base tables Excel `3atab` 三条 **Crude oil** 行（`copr_world` / `copr_opec` / `copr_nonopec`）+ `3dtab` 的 Non-OPEC DoC 10 国合计 | 2022-01 ~ 2027-12（72 月；2022-01~2026-09 实际值、2026-10 起预测） | 无填充/无圆点：World / OPEC / Non-OPEC DoC / Others（Others = Non-OPEC − DoC，元素级相减，含阿联酋）；**四线 2026-10 起预测段虚线**；x 轴 `22/01` 式月份标签（12 刻度上限）；y 轴数据驱动 + `baseNote`「轴起点（非 0）」虚线基线 |

**口径（改这块必读）**：

1. **「世界合计没有月度」已被推翻（2026-10-10）**：2026-10-08 实测的「四条路全堵死」
   （STEO 9 期 PDF 无月度列 / EIA international WL 全 0 / 路径式返回整库默认行 / MOMR 无
   World supply 表）**只对 PDF 与 API 成立**；STEO 的 **base tables Excel**（月报页
   Supplementary data 里的 `*_*_base.xlsx`）的 `3atab` 就是表 3a 的**月度原始表**，
   72 个月、分辨率高于季度。缺的是"找到这个文件"，不是"数据不存在"。
   （当年的四条实测记录保留在下方历史块里，勿删——它解释了当初为什么只能做季度。）
2. **单位是 mb/d 日均速率**。月值就是"该月日均"，**不得做任何月度加总/平均换算**；
   与 MOMR 12 国口径（现仅存于 DoC 10 国图）只能并列、不能合并。
3. **OPEC = 表 3a 脚注 (b) 的 11 国（不含阿联酋）**；表 3d 的国别分项同此口径（脚注 c），
   2026-10-11 起「OPEC 原油产量」图即用这组分项（见上方换源专节）。
4. **预测边界 2026-10**：`Dates` sheet 的 `Last Historical Month = 202609` 是权威口径，
   预测起点 = 末个历史月的**下一月**（不要靠"报告发布月"去猜）；换新一期 base 表时该值会顺移。
5. **逐月恒等校验**：`OPEC 原油 + 非 OPEC 原油 = 世界原油`（`steo_monthly.py:main()` 对
   crude 与 total 两套口径各验一遍，容差 0.05，实测 72 个月 0 违例），取错行会当场 FAIL。

**落地链路（2026-10-16 起：xlsx 手工下载 → EIA STEO 官方 API）**：
`src/fetch/supply/steo_monthly.py` 一次请求批量拉 25 条序列（`/v2/steo/data/?frequency=monthly`，
与周度 WPSR 同为 EIA v2、同一把 `EIA_KEY`；起点按 `WINDOW_START=2022-01` 截断，API 实际
从 1993-01 起）→ 预测边界由**分国行最后非空月**反推（分国行只有历史段有值，= `lastHistorical`，
次月即 `forecastStart`）→ `data/processed/steo_world_monthly.json`。
⚠️ **已从 `run.py` 的 `EXTRACTORS` 摘除**，改由 `build_dataset` 在 **dataset 步骤**调用
`steo_monthly.fetch()`（挂在 extract 步骤时 `run.py build` 不会刷新，等于每月要手动跑一次）；
API 失败/返回空时回落上次快照，流水线不中断。
→ `build_dataset._offline_supply()` 注入 `steoMonths` / `steoWorldMonthly` / `steoOpecMonthly` /
`steoNonOpecMonthly` / `steoForecastStart` / `steoForecastIndex` / `steoLastHistorical` →
域 `dataio.GROUPS["world.json"]`（漏登记会 `KeyError: 未归入任何域文件的 key`）
→ `dashboard.js` 的 `SUPPLY_RENDERERS.steoWorld` + `STAT_MAP.steoWorld` + `computeDerived` 三处登记
（漏 `computeDerived` 只在「拉取实时」后才暴露，STATE 被整体替换后图会整条消失；
⚠️ 标量键判空必须用 `!=null` —— `forecastIndex` 若为 0，`(S.x||...)` 会把 0 吞掉）。
旧季度脚本 `steo_world.py` 此前已不在链路里，2026-10-23 移出仓库（口径要点见「已下线口径留档」）。

**已下线（勿回退）**：2026-10-08 曾按 MOMR 表 5-7 的 `Total DoC` / `Total Non-OPEC DoC`
做过一张「OPEC+ 原油产量（月度）」图（`opecDoc` / `opecDocMonths` / `opecNonOpecDoc` 三键 +
`SUPPLY_RENDERERS.opecDoc` + `tools/verify_opec_doc.js`），**已按用户裁定全部删除**：
`getElementById` 相关的月度图、非 OPEC 月度数据、解析分支、校验脚本（已 `mv` 到
`~/.Trash/verify_opec_doc_20261008.js`，废纸篓可恢复）。原 `opec_momr.py` 文件头曾留档
两行为何不复用（`Total DoC` 只有 2024-02 起 31 个月——OPEC 2024 年 5 月才加进表 5-7，
与 `Total OPEC` 起始月不同；且它是原油+凝析油口径，≠ STEO 表 3c/3d 的 "OPEC+ total"。

**校验**：`node tools/verify_world_monthly.js`（NODE_PATH 指向 huashu-design/node_modules）。
断言：三条线各 72 个非空点、x 轴 72 个月（2022-01~2027-12，`YYYY-MM` 格式）、
三条线**首虚线段 = 56（2026-09→2026-10，预测起点 index 57）**、末个历史月 2026-09（世界 75.97）/ 预测首月 2026-10 有值、
逐月恒等、**baseNote 启用 + y 轴数据驱动 15–85（不再落到 10）**、末点 82.97 / 25.17 / 57.81、
**徽章 = 最新实际值（"75.97 · 截至 26/09"，且不再含 "27/12"）**、
**页尾 source 无 `.sline` 分段且文案逐字 == 单段定稿**、无 `.nodata` 占位、
旧 `supply_prodcap_opecdoc` 确已下线、既有 `supply_prodcap_opec` 仍在、无 console 报错。
（旧校验脚本 `verify_world_quarterly.js` 已删除，由本文件取代。）

---

## 首屏改版：新增「Crude Oil News」卡，风险贡献并入整体风险概览（2026-10-15）

原首屏 `.risk` 三卡中的「各维度风险贡献（当前）」（独占一卡、`#riskbar` 画布 158px）已取消：

- **缩小合并**：该图以 `.riskmini` 容器（104px）并入左侧「整体风险概览」卡（仪表盘下方、虚线分隔），
  画幅变窄后同步收紧字体（x/y 轴 9–10px）与圆角；`.risk` 首列由 240px 放宽到 272px，以放下五个维度标签。
- **空出的卡位**改为 **Crude Oil News**：渲染 `data/dataset/news.json` 的 `crudeNews`，
  **只输出「标题 + 超链接」**（`target="_blank"` + `rel="noopener noreferrer"`），**按日期倒序（最新在前）**。
  高度与同排卡片对齐：`.newscard` 为 flex 列、`.newslist` 取 `flex:1;min-height:0;overflow-y:auto`，
  **填满整张卡的剩余高度后再内部滚动**（不是写死 `max-height`，避免半截留白）。
- **首屏三卡等高（2026-10-15）**：`整体风险概览` / `Crude Oil News` / `异常预警（实时规则）` 并排（`.risk` 三列网格），
  高度以「整体风险概览」卡的**自然高度**为准——`.gaugewrap{align-self:start}` 取其真实所需高度，
  `syncRiskHeights()` 把该高度钉到另两卡，二者内容超出时内部滚动；窄屏（单列）自动放开各自自然高度。
- 交互不变：`#riskbar` 点击任一维度仍跳转到对应 tab。

### 存储选型：用 JSON，不用 xlsx

新建 `data/dataset/news.json`（`crudeNewsMeta` + `crudeNews[]`），没走 Excel，理由：

1. `data/dataset/*.json` 是本项目的**唯一事实源**，经 `src/dataio.py` 的 `GROUPS`
   注册（`"news.json": ["crudeNews","crudeNewsMeta"]`）后**自动注入**看板，零额外管线；
   xlsx 则还要再写一个解析/导出环节。
2. 本域是**机器产出**：需要「按 URL 去重 → 区间过滤 → 按日期排序 → 合并写回」，
   这些操作在 Python 里对 list[dict] 是几行，在 Excel 里要自己造查询逻辑。
3. 字段是平的（`title` / `url` / `date` / `source`），用不到 Excel 的表格能力；
   且新闻标题常含逗号、引号、emoji，写 CSV/xlsx 反而是转义负担。

`crudeNewsMeta.baseDate = 2026-10-14`（用户指定的时间基线）：文件为空时，
增量抓取的起点回落到它，而不是从 1970 抓。

### Fetch 按钮：`/api/news` 增量抓取

卡片右上角 `↻ Fetch` → `fetchNews()` → `GET /api/news` → `src/fetch/news/argus.py:run()`。

**抓取规则（2026-10-15 改：整页完整 feed，不再按 last_date 增量）**：

| 项 | 取值 |
|---|---|
| 新闻源 | Argus「filtered 完整 feed」第一页：`latest-market-news?filter_language=en-gb&filter_commodity=crude:crude+oil,condensate&page=1`（最近 ~27 条），**不是** `/en/commodities/crude` 的 5 条精选 widget |
| 抓取范围 | **整页**解析（不再用 `last_date` 做下界过滤——否则只会保留当日条、漏掉同日其余快讯）；`until` 仅挡未来日期 |
| 去重 | 按 `url` 全量去重，已存在的不重复写入 |
| 落盘 | 合并后**按 date 倒序**写回，并更新 `crudeNewsMeta.lastFetched` |
| 收敛 | 页内都是最近窗口，news.json 自然收敛到「最近 ~27 条」，不会无限膨胀 |
| 前端 | 成功后 `STATE.crudeNews = res.items` 并重渲染；状态行显示「新增 N 条 · 区间 A → B」或「已是最新」 |

⚠️ **「fetch 永远只有 5 条」的根因**：早期默认源是 `/en/commodities/crude` 的「Latest crude oil news」**5 条精选 widget**，无论怎么增量都超不过 5 条、且会系统性漏掉同日其余快讯。现已把默认源改为 filtered 完整 feed，fetch 解析整页（实测 27 条），不再有此上限。

CLI 同款：`python -m src.fetch.news.argus [--until 2026-10-15] [--from-file page.html] [--dry-run]`。

⚠️ **使用前提**

1. **必须经 `python run.py serve` 打开本页**才有 `/api/news`；直接双击静态 HTML 会 404
   （与首屏「拉取实时」按钮同一限制），此时状态行会提示「请用 python run.py serve 打开本页」。
2. **Argus 有 AWS WAF 挑战**：非浏览器请求（curl / urllib）对任何 Argus 页一律返回
   **HTTP 202 + `window.gokuProps` 挑战页**（`Server: CloudFront`、`x-cache: Error from cloudfront`）。
   —— 这一点已通过**无头浏览器通道（路径 B）**解决，见下。若浏览器通道也失效（指纹被识破），
   仍会如实返回 `{"ok":false,"blocked":true,"reason":"waf"}`，前端显示橙色 warn，**不假装成功**。

解析器 `parse_html()` 已按页面结构写好，可用 `--from-file` 拿真实 HTML 离线验证。
⚠️ **归属窗口是坑**：同一页里 N 条新闻是连续 HTML 块，若在「锚点 ±600 字符」固定窗口里取
标题/日期，会**跨块误取下一条**（实测两条新闻 title 全变成第二条）。实现上把取值窗口严格
限定为 `[上一条锚点结束, 下一条锚点开始)`：日期先取锚点前的最后一个 `DD/MM/YY`、没有再取
锚点后的第一个；标题优先取 Argus 的稳定 QA 钩子（`qa-combinedfeed-item-title` 用于 commodities 页，
`qa-item-title` 用于 filtered 列表页——两种版式都认，不受 CSS hash 类名影响）；取不到再剥标签截
`(Argus)` dateline，再不行用 URL slug 兜底；同一 URL 页内多次出现（图片链接 + 文本链接）时保留
**有真实锚文本**的那次。日期在 filtered 列表页是「City, 14 October (Argus)」月名写法（用 `_MONTHS`
映射成数字），commodities 页是 `DD/MM/YY` 徽标。

### 路径 B 已实现：无头浏览器自动抓取（2026-10-15）

Fetch 按钮现在能**真正抓到 Argus 新闻**——不再只是「人工填 JSON」的占位。

- **渲染通道**：`tools/fetch_argus_news.cjs`（Node）用**已安装的** `playwright-core`
  （`/Users/sto1/.workbuddy/binaries/node/workspace/node_modules/playwright-core`）+ Chromium
  `chromium-1217`（`~/Library/Caches/ms-playwright/`，Playwright 默认缓存目录）无头渲染
  `LIST_URL`（默认 = filtered 完整 feed，可用环境变量 `ARGUS_LIST_URL` 覆盖），等 `>=5` 个新闻锚点
  出现后回传渲染后的 HTML（JSON）。**复用既有资产，没再装 Python playwright、也没再下浏览器**。
  可执行文件自动探测顺序：环境变量 `ARGUS_CHROME_BIN` → `chromium-1217` → 系统 Google Chrome。
- **Python 侧**：`argus.py` 的 `run()` 优先走 `fetch_html_browser()`（subprocess 调 node，超时 90s）；
  浏览器返回的 HTML 若仍带 `gokuProps`→判 WAF 回落；浏览器通道不可用（无 node / playwright /
  chromium）→ 自动回落 urllib 直连并据结果判 WAF。解析与整页合并仍在 Python，已充分单测。
- **serve 改多线程**：`src/serve.py` 的 `HTTPServer` 换成 `ThreadingHTTPServer`（并设
  `Handler.timeout=120`），否则浏览器渲染那几秒会卡住整页。
- **实测**：`python run.py serve` 起服务后 `curl /api/news` 返回
  `{"ok":true,"blocked":false,"parsed":27,"added":22,"total":27}`（27 条来自 filtered 完整 feed 实时渲染，
  与本地已存 5 条 URL 去重 → 新增 22）；无头 Chromium 能过 AWS WAF，不再返回挑战页。

⚠️ 手动兜底仍可用：直接改 `data/dataset/news.json` 后跑 `python run.py html`
（`run.py extract` 不会覆盖它，同 iea / opec 手工域）。CLI 同款：
`python -m src.fetch.news.argus [--until 2026-10-15] [--from-file page.html] [--dry-run]`。

- 默认入口 = **filtered 完整 feed**（`…/latest-market-news?filter_commodity=crude…`）；早期曾用
  `/en/commodities/crude` 的 5 条精选 widget，会系统性漏条——已弃用。两版页面结构不同
  （commodities 用 `qa-combinedfeed-item-*`，filtered 用 `qa-item-title` + 月名 dateline），解析器
  两种都认。`ARGUS_LIST_URL` 可覆盖默认源。
- 回归测试：
  - `node tools/verify_news.js`（**35/35**，渲染 + 倒序 + Fetch 按钮 + 四种返回路径 + 样式）
  - `.venv/bin/python tools/verify_argus_parse.py`（**21/21**，解析归属 + 区间合并 + 去重）

## 供给侧三张图换源：STEO base tables xlsx → EIA STEO 官方 API（2026-10-16）

**需求**：「全球原油产量 / Non-OPEC DoC 原油产量 / OPEC 原油产量」三张月度图，此前依赖
**手工下载** STEO base tables Excel（`3atab` / `3dtab`）再离线解析——每月更新都要人工跑一趟。
EIA 既有周度 WPSR 的官方 API，那么 STEO 是否也有？有则直接换源，月度自动更新。

**核实结论（可行）**：
1. **STEO 确有官方 API**：`/v2/steo/data/`（月度，531,924 行，与周报同为 EIA v2、同一把 key）。
2. **序列口径** `COPR_*` = Crude Oil Production（**仅原油**，mb/d），与图标题「**原油**产量」一致；
   ⚠️ 勿混用 `COPC_*`（产能）与 `PAPR_*`（总液体，含 NGL）。
   - 世界 `COPR_WORLD` / OPEC `COPR_OPEC` / 非 OPEC `COPR_NONOPEC`
   - OPEC 11 国分项（脚注 c，**不含阿联酋**）`COPR_SA/IZ/IR/KU/VE/NI/LY/AG/CF/EK/GB`
   - DoC 10 国分项 `COPR_RS/KZ/MX/MU/AJ/MY/OD/BX/BA/SU` + 合计 `COPR_OPECPLUS_OTHER`
3. **数值可复刻**：`@2026-09` 逐项与 xlsx 一致（世界 75.97159343 / OPEC 20.8 / 非 OPEC 55.17159343 /
   DoC 14.0496786，21 国分项亦在 1e-6 内）；差异仅 API 自身末位舍入（~1e-8 mb/d，图形无感）。
4. **⚠️ API 没有 vintage 维度**（无 vintage 字段、一期一月一行、`facets[vintage][]` 直接 400）
   → **outlook8「EIA 油价基准预测」必须继续用 PDF**（那张画的是逐期修订路径）；
   本三图只需「最新一期的历史+预测」，换源无影响。
5. **预测边界不再依赖 `Dates` 表**：分国行只有历史段有值 → 其最后非空月即 `lastHistorical`
   （2026-09），次月 `forecastStart`（2026-10 / index 57），由 `BOUNDARY_PROBE=COPR_SA` 反推。

**改动**：
- `src/fetch/supply/steo_monthly.py` 整体重写为 API 抓取（25 序列**一次批量请求**）；
  新增**预测守卫**：API 若不给预测数据，`forecastStart/Index` 置 `None` 并把月份轴与全部数组
  **截断到末个历史月**（用户明确要求「没有预测就直接把预测删除」）。
- `build_dataset` 改在 **dataset 步骤**调 `steo_monthly.fetch()`（try/except + 回落上次快照）；
  `run.py` 的 `EXTRACTORS` 摘除该条目（否则 `run.py build` 不刷新）。
- 三图页尾改成与周报同款的简洁样式：
  `数据源：EIA STEO 月度 API（序列 COPR_WORLD / COPR_OPEC / COPR_NONOPEC）· 实时抓取脚本 src/fetch/supply/steo_monthly.py`
  （另两张分别写 `COPR_OPECPLUS_OTHER ＋ DoC 10 国分项` 与 `COPR_OPEC ＋ OPEC 11 国分项`）。

**回归**：
- `PYTHONPATH=. .venv/bin/python tools/verify_steo_forecast_guard.py` —— 新增，离线造数验
  「有预测（72 月 / 2026-10 起）」与「无预测（截断 57 月）」两分支。
  ⚠️ 它当场抓出一个真缺陷：无预测时 `fc_i=None` 但 `forecastStart` 仍残留 `2026-10`，
  与截断后的月份轴矛盾 —— 已修（`fc_i is None ⇒ fc = None`）。
- `verify_world_monthly` / `verify_world` / `verify_opec_tail` / `verify_nonopec_doc` 全绿
  （前两者的 3 线时代旧断言本次一并更到 4 线：World / OPEC / Non-OPEC DoC / Others，
  恒等式同步改为 OPEC+DoC+Others=世界，y 轴下界随 DoC 线由 15 变 10）。
- `run.py html` 两次字节一致（md5 `712d73170bac1bd6c6191590e475d176`，896,730 B）。

## 已下线口径留档（2026-10-23）

两条解析链路已彻底下线：MOMR 表 5-7 的**月度**解析器与 STEO 表 3a 的**季度**解析器
（二者原为 `src/fetch/supply/` 下的 `opec_momr` 与 `steo_world` 两个模块），连同它们各自的
产出 JSON **已移出仓库（废纸篓可恢复）**。删的理由是它们早已不在 `run.py EXTRACTORS`
与 `build_dataset` 的链路上（OPEC / Non-OPEC DoC 月产图走 EIA STEO 表 3d 月度、
全球三图走 EIA STEO 实时 API）；但下列口径陷阱**无法从数据反推**，故在此留档 ——
若日后要重新启用 MOMR 或季度口径，先读完本节。

### MOMR 表 5-7（secondary sources，二手来源）

- **起点不一致**：`Total DoC` 与 `Total Non-OPEC DoC` 两行是 OPEC **2024 年 5 月 MOMR
  才加进表 5-7** 的（实测 2024-02 / 2024-04 两期只有 `Total OPEC`），序列起点比
  `Total OPEC` 晚 3 个月（DoC 10 国 2024-02 起 31 个月 vs OPEC 12 国 2023-11 起），
  **x 轴绝不能共用月份键**，必须各用各的月份键。
- **口径不同、不可相减**：`Total DoC` 是**原油 + 凝析油**口径（不含 NGL），
  ≠ STEO 表 3c/3d 的 "OPEC+ total"（总液体且含预测段）。
- **散文行陷阱**：表 5-7 里有一句以 `Total DoC` 开头的散文
  （`Total DoC crude oil production averaged 38.05 mb/d in August...`）。旧脚本靠
  「数值个数闸门 `len(nums) >= N+1`」自然滤掉；重新启用时必须显式排除散文行。
- **22 国 vs 10 国**：`Total DoC` = 38.06 mb/d（22 国）≠ `Total Non-OPEC DoC`
  = 13.97 mb/d（10 国，2026-08）。看板取的是后者，勿混用。
- 判名顺序曾为：`Total Non-OPEC DoC` → `Total OPEC` → OPEC 12 国 → 非 OPEC 10 国。
- 数据层从来都是 **12 国全量**（`COUNTRIES` 自始列全 12 个成员国），早期图上只画 5 国
  是前端 `major` 数组的显示选择，不是数据缺失。

### EIA STEO 表 3a（季度）

- **必须取 `Crude oil` 行**：表结构是「World total / OPEC total / Non-OPEC total」三个
  **总液体合计**各自下面挂一行 `Crude oil` + 一行 `Other liquids`；取错行量级差约 26 mb/d。
- **单位是日均速率**：季度值就是该季度日均，**不能除以 3 去月化**。
- **该表只有季度、没有月度**（9 期 STEO 全量扫描确认，任何表都没有月度列）。
- 自带恒等校验：OPEC 原油 + 非 OPEC 原油 ≈ 世界原油（24.04 + 53.20 = 77.24 vs 77.25）。
- 旧季度聚合**只取完整季**（3 个月齐全才平均，缺月的季度不产出）——拿 2 个月均值
  冒充季度日均会偏。

## 已知约束

- **默认 API Key 会随渲染注入 HTML**，仅适合本地/内网看板，公开部署前请用环境变量覆盖 `EIA_KEY` / `FRED_KEY`。
- **`src/serve.py` 已改为 `ThreadingHTTPServer`**（2026-10-15，配合 `/api/news` 的无头浏览器渲染）。若有浏览器保持 keep-alive 不释放，仍可能阻塞后续请求（页面一直转圈、curl 返回 000/超时）。调试时先关掉残留的 headless Chrome 与旧服务进程。
- **`/api/news`（Crude Oil News 的 Fetch 按钮）走无头浏览器通道**：服务端经 `tools/fetch_argus_news.cjs`（playwright-core + 已装的 `chromium-1217`）渲染 Argus 页，能过 AWS WAF 拿到真实新闻。若浏览器指纹日后被识破、返回仍是 `gokuProps` 挑战页，按钮会如实显示「Argus 返回 AWS WAF 挑战页」而非假装有新数据——此时需更新浏览器指纹或退回人工维护 `news.json`。该通道依赖 `playwright-core` 与 `chromium-1217` 两个既有资产，未写入 `requirements.txt`（避免给纯数据刷新强加浏览器依赖）。
- OPEC 年度产量（FRED 国别序列）只覆盖 7 个成员国，属**部分合计**，不能与 MOMR 表 5-7 的 12 国合计混用。
- **Brent 12M 期限结构依赖 yfinance + pandas**（全项目唯一用到 yfinance 的模块），二者已写入 `requirements.txt` 的「刷新期依赖」段：缺失时该图空白并在卡内给出提示，但不会中断流水线。
  自 2026-10-07 起 `run.py` 的 `dataset` / `html` / `build` 都会经 `_dataset_python()` 优先挑项目内 `.venv`（带这两个包），所以**直接敲 `python run.py build` 也能拿到数据**，不必再手动指定解释器。
- 中国原油加工量 / 进口量、制造业 PMI 为**手工录入**（统计局 / 海关数值接口同源受限），维护在 `data/raw/` 的两个 xlsx 里（`cn_crude_import and processing.xlsx`【含「中国原油加工量」「中国原油进口量」两个 sheet】/ `pmi_manufacturing.xlsx`）；脚本内的硬编码序列仅作 xlsx 不可用时的兜底。全球 GDP 增速预期目前仍硬编码在 `src/fetch/demand/pmi_gdp.py`，尚未 xlsx 化。IMF《WEO》的 **GDP 增速预期与油价基准假设**同源，都硬编码为 `pmi_gdp.py` 里的**期次矩阵**：GDP 面板用 `WOE_VINTAGES`（仅 2026 辑四期，每行值 = 该期对 2026/2027 的增速 %）；油价面板用 `WOE_OIL_VINTAGES`（2025 辑四期 + 2026 辑四期，每行值 = 该期对 2025/2026/2027 的油价 $/桶）。两套矩阵共用同一套期次轴。⚠️ 油价面板**按 WEO 辑分组**（2025 辑 / 2026 辑，各辑独立成图、卡片右上角年份按钮切换），每辑目标年由该辑行自身决定（2025 辑=2025/2026、2026 辑=2026/2027），2026 在 2025 辑为次年、2026 辑为当年、分属不同页面不撞线；新增一期只需在对应矩阵末尾追加一行、按钮自动多出一项，数值、页尾文案、修正图全部随之派生。
