# china-coal/src — 看板构建脚本

中煤能源（601898.SH / 01898.HK）看板 `../china-coal-dashboard.html` 的全部构建脚本。
产物目录：`../svg/`（62 张 SVG）、`../数据源/`（5 个 xlsx）、`../china-coal-dashboard.html`。

---

## 0. 运行前提

```bash
# 任意目录执行均可——每个脚本顶部都注入了「路径基准」，会自动 chdir 到项目根 china-coal/
python /path/to/china-coal/src/<script>.py
```

依赖：`openpyxl`（全部脚本）；`pandas / numpy` 仅 `build_business_svg.py` 等少数图表脚本按需使用。

> **路径基准**（8 个脚本统一注入，勿删）：
> ```python
> import os as _os
> _os.chdir(_os.path.dirname(_os.path.dirname(os.path.abspath(__file__))))
> ```
> 删除后「数据源/…」「svg/…」等相对路径会解析到 `src/` 下而报错。
>
> **`__CHARTS__` 正则坑**：内联 SVG 含 `\"` 转义，任何「旧值清除」正则必须写 `(?:[^"\\]|\\.)*`，
> 不能用 `[^"]*`——后者会在第一个 `\"` 处截断，只删半条并留下孤儿文本（JS SyntaxError）。

---

## 1. 脚本清单（输入 → 输出）

| # | 脚本 | 读（输入） | 写（输出） |
|---|------|-----------|-----------|
| 1 | `build_volume_svg.py` | `数据源/中煤能源_产销数据.xlsx`<br>`数据源/中煤能源_价格和成本.xlsx` | `svg/trend_selfprod_q/_y`、`totalsales_q/_y`、`structure_q/_y`、`capacity_y`、`reserves_y`、`avgprice_y`、`unitcost_y`、`unitgm_y`<br>+ 同名 `spark_*.svg` |
| 2 | `build_finance_svg.py` | `数据源/中煤能源_业务追踪数据.xlsx`<br>（`财务指标(季度)` / `财务指标(年度)`） | `svg/trend_{revenue,profit,cash,debt,roe,bps}_{y,q}.svg`<br>+ `svg/spark_{…}.svg` |
| 3 | `build_business_svg.py` | `数据源/中煤能源_业务结构.xlsx`（6 sheet） | `svg/trend_biz_{chem,equip,elec}[_gm]_y.svg`<br>+ `svg/spark_biz_*.svg` |
| 4 | `build_monthly_svg.py` | `数据源/中煤能源_月度经营数据.xlsx` | `svg/trend_m_{prod,sales,selfsales,equip,chem}.svg`<br>+ `svg/spark_m_*.svg` |
| 5 | `build_coal_price.py` | `数据源/中煤能源_价格和成本.xlsx`<br>（`秦皇岛5500周度` sheet） | `svg/trend_qhd5500_weekly.svg`、`svg/spark_qhd5500.svg`<br>**并 patch `china-coal-dashboard.html`** |
| 6 | `build_cycle_svg.py` | `数据源/煤炭行业周期历史煤价.xlsx`<br>（`年度均价` / `周期阶段`） | `svg/煤炭周期复盘.svg`（1240×460） |
| 7 | `move_cycle_to_trend.py` | `svg/煤炭周期复盘.svg` | **patch `china-coal-dashboard.html`**：<br>① 删末尾「煤炭行业周期」章节 ② 换 `.cycle-chart` CSS<br>③ 写 `__CHARTS__["cycle_coal_price"]` ④ 插「长期趋势专区」第 7 项 |
| 8 | `reinject_svgs.py` | `svg/*.svg` + `china-coal-dashboard.html` | **patch `china-coal-dashboard.html`**：按 key（=svg 文件名去扩展名）把重生成 svg 写回 `__CHARTS__` |

> 第 5/7/8 号脚本会改 HTML。其余一律只读输入、只写产物。

---

## 2. 调用顺序

### A. 日常刷新（改了 xlsx 想重新出图）

```bash
python src/build_volume_svg.py     # 产销 / 储量 / 价格 / 成本 / 结构
python src/build_finance_svg.py    # 财务年度+季度趋势
python src/build_business_svg.py   # 业务结构三板块
python src/build_monthly_svg.py    # 月度经营数据
python src/build_coal_price.py     # Q5500 周价 + 卡片名称着色
python src/build_cycle_svg.py      # 周期复盘图
python src/move_cycle_to_trend.py  # 周期图注入看板第 7 项
```

### B. 只改了生成器样式、不想重跑全链

```bash
# 在 china-coal/ 目录执行：按 key(=文件名去扩展名) 把 svg/*.svg 写回 __CHARTS__
python src/reinject_svgs.py china-coal-dashboard.html svg
# 再补跑一次（reinject 不认「煤炭周期复盘.svg」这个中文名）
python src/move_cycle_to_trend.py
```

### C. 财报季更新（手工管线）

```bash
# ① 按官方季报 PDF，用 sheet-agent / 本地编辑 更新 数据源/中煤能源_业务追踪数据.xlsx
#    的 4 张季度表 + 财务指标(季度)（含资产负债率），以及 中煤能源_产销数据.xlsx 的 Q3 行
# ② 重跑财务图 + reinject
python src/build_finance_svg.py
python src/reinject_svgs.py china-coal-dashboard.html svg
```

> **Card4 数据链路**（2026-10-24 固化）：六项年度值 + 6 张 sparkline + 12 张趋势图（6 指标 × 季度+年度）
> 全部由 `财务指标(季度)/(年度)` 驱动，**不依赖任何联网脚本**。看板为自包含静态站，无实时 API。

---

## 3. 幂等性 / 安全性

- 第 1–6 号：**只读 xlsx、只写 SVG**，可反复重跑，产物 byte-identical。
- 第 7 号 `move_cycle_to_trend.py`：靠 4 组标记去重（`BEGIN/END 煤炭行业周期`、`CSS_MARK`、
  `__CHARTS__` key、`<!-- 7 煤炭行业周期 -->`），重复运行不改变文件内容。
- 第 8 号 `reinject_svgs.py`：按 key 写回，跳过的文件 = `svg/` 中存在但 `__CHARTS__` 无同名 key 者
  （目前仅 `煤炭周期复盘.svg`，由第 7 号单独处理）。

---

## 4. 产物落点速查

```
china-coal/
├─ china-coal-dashboard.html   看板（自包含；__CHARTS__ 内联 62 个 key）
├─ src/                        本目录（8 个 py 构建脚本）
├─ svg/                        62 张 SVG，文件名(去扩展名)=__CHARTS__ key
│                                        = 35 趋势 + 26 sparkline + 1 cycle_coal_price
└─ 数据源/
   ├─ 中煤能源_业务追踪数据.xlsx       ← 手工/sheet-agent 维护（只读；8 sheet）
   ├─ 中煤能源_产销数据.xlsx            ← 手工维护（只读）
   ├─ 中煤能源_价格和成本.xlsx          ← 手工维护（只读，含秦皇岛5500周度）
   ├─ 中煤能源_业务结构.xlsx            ← 手工维护（只读）
   ├─ 中煤能源_月度经营数据.xlsx        ← 手工维护（只读）
   └─ 煤炭行业周期历史煤价.xlsx         ← 手工维护（只读）
```

> 数据源 xlsx 均为手工/sheet-agent 维护的**只读输入**，构建脚本不写回 xlsx（历史上曾用
> `build_finance_card.py` / `build_monitor_excel.py` 联网写回，已于 2026-10-24 删除——前者
> 写入的「财务表现」sheet 与 `财务指标(季度)/(年度)` 完全重复且口径有偏差，后者重建结构与当前
> 文件不符）。
