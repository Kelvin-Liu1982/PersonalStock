# china-coal/src — 看板构建脚本

中煤能源（601898.SH / 01898.HK）看板 `../china-coal-dashboard.html` 的全部构建脚本。
产物目录：`../svg/`（64 张 SVG）、`../数据源/`（5 个 xlsx）、`../china-coal-dashboard.html`。

---

## 0. 运行前提

```bash
# 任意目录执行均可——每个脚本顶部都注入了「路径基准」，会自动 chdir 到项目根 china-coal/
python /path/to/china-coal/src/<script>.py
```

依赖：`openpyxl`（全部）；`pandas / numpy / akshare / requests`（仅 `build_finance_card.py`、`build_monitor_excel.py`）。

> **路径基准**（10 个脚本统一注入，勿删）：
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

| # | 脚本 | 读（输入） | 写（输出） | 联网 | 写回 xlsx |
|---|------|-----------|-----------|:---:|:---:|
| 1 | `build_monitor_excel.py` | 新浪财经（akshare） | `数据源/中煤能源_业务追踪数据.xlsx`（7 sheet） | ✅ | ✅（重建） |
| 2 | `build_volume_svg.py` | `数据源/中煤能源_产销数据.xlsx`<br>`数据源/中煤能源_价格和成本.xlsx` | `svg/trend_selfprod_q/_y`、`totalsales_q/_y`、`structure_q/_y`、`capacity_y`、`reserves_y`、`avgprice_y`、`unitcost_y`、`unitgm_y`<br>+ 同名 `spark_*.svg` | ❌ | ❌ |
| 3 | `build_finance_svg.py` | `数据源/中煤能源_业务追踪数据.xlsx`<br>（`财务指标(季度)` / `财务指标(年度)`） | `svg/trend_{revenue,profit,cash,debt,roe,bps}_{y,q}.svg`<br>+ `svg/spark_{…}.svg` | ❌ | ❌ |
| 4 | `build_business_svg.py` | `数据源/中煤能源_业务结构.xlsx`（6 sheet） | `svg/trend_biz_{chem,equip,elec}[_gm]_y.svg`<br>+ `svg/spark_biz_*.svg` | ❌ | ❌ |
| 5 | `build_monthly_svg.py` | `数据源/中煤能源_月度经营数据.xlsx` | `svg/trend_m_{prod,sales,selfsales,equip,chem}.svg`<br>+ `svg/spark_m_*.svg` | ❌ | ❌ |
| 6 | `build_coal_price.py` | `数据源/中煤能源_价格和成本.xlsx`<br>（`秦皇岛5500周度` sheet） | `svg/trend_qhd5500_weekly.svg`、`svg/spark_qhd5500.svg`<br>**并 patch `china-coal-dashboard.html`** | ❌ | ❌ |
| 7 | `build_finance_card.py` | 新浪财经三表 + `数据源/中煤能源_业务追踪数据.xlsx` | `svg/trend_revenue_profit.svg`、`svg/trend_ratios.svg`、`svg/spark_*.svg`<br>**并 patch `china-coal-dashboard.html` Card 4**<br>**并写回 xlsx「财务表现」sheet** | ✅ | ✅ |
| 8 | `build_cycle_svg.py` | `数据源/煤炭行业周期历史煤价.xlsx`<br>（`年度均价` / `周期阶段`） | `svg/煤炭周期复盘.svg`（1240×460） | ❌ | ❌ |
| 9 | `move_cycle_to_trend.py` | `svg/煤炭周期复盘.svg` | **patch `china-coal-dashboard.html`**：<br>① 删末尾「煤炭行业周期」章节 ② 换 `.cycle-chart` CSS<br>③ 写 `__CHARTS__["cycle_coal_price"]` ④ 插「长期趋势专区」第 7 项 | ❌ | ❌ |
| 10 | `reinject_svgs.py` | `svg/*.svg` + `china-coal-dashboard.html` | **patch `china-coal-dashboard.html`**：按 key（=svg 文件名去扩展名）把重生成 svg 写回 `__CHARTS__` | ❌ | ❌ |

> 第 6/7/9/10 号脚本会改 HTML；第 1/7 号会改 xlsx。**其余一律只读输入、只写产物。**

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

### C. 财报季更新（需要联网）

```bash
python src/build_monitor_excel.py  # 重建 业务追踪数据.xlsx（7 sheet 全量）
python src/build_finance_svg.py    # 财务趋势图
python src/build_finance_card.py   # Card 4 数值 + 「财务表现」sheet + sparkline
```

> `build_finance_card.py` 会输出两张**看板当前未引用**的 SVG（`trend_revenue_profit.svg`、`trend_ratios.svg`）。
> 这是 2026-08-23 把组合图拆成 10 张单图之后的历史遗留，脚本自身会打印
> 「⚠️ HTML 长期趋势专区未引用趋势图 SVG」告警，暂保留。

---

## 3. 幂等性 / 安全性

- 第 2–6、8 号：**只读 xlsx、只写 SVG**，可反复重跑，产物 byte-identical。
- 第 9 号 `move_cycle_to_trend.py`：靠 4 组标记去重（`BEGIN/END 煤炭行业周期`、`CSS_MARK`、
  `__CHARTS__` key、`<!-- 7 煤炭行业周期 -->`），重复运行不改变文件内容。
- 第 7 号 `build_finance_card.py`：会 `wb.save(EXCEL)`。写回后**必查**
  `xl/styles.xml` 有无空 `<fill/>`（openpyxl 已知缺陷，会导致 Excel 打不开）。
- 第 1 号 `build_monitor_excel.py`：会**整体重建** `业务追踪数据.xlsx`，仅在财报季执行。

---

## 4. 产物落点速查

```
china-coal/
├─ china-coal-dashboard.html   看板（自包含；__CHARTS__ 内联 62 个 key）
├─ src/                        本目录（10 个 py）
├─ svg/                        64 张 SVG = 61 张与 __CHARTS__ key 同名
│                                        + 煤炭周期复盘.svg（key 名 cycle_coal_price）
│                                        + 2 张历史遗留未引用
└─ 数据源/
   ├─ 中煤能源_业务追踪数据.xlsx       ← build_monitor_excel / build_finance_card（写）
   ├─ 中煤能源_产销数据.xlsx            ← 手工维护（只读）
   ├─ 中煤能源_价格和成本.xlsx          ← 手工维护（只读，含秦皇岛5500周度）
   ├─ 中煤能源_业务结构.xlsx            ← 手工维护（只读）
   ├─ 中煤能源_月度经营数据.xlsx        ← 手工维护（只读）
   └─ 煤炭行业周期历史煤价.xlsx         ← 手工维护（只读）
```
