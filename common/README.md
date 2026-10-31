# common/ — 跨看板通用能力

本目录只放**泛型**工具，不含任何项目数据/品牌，供各子看板（china-coal / china-mobile /
china-telecom / china-unicom / cosco-shipping …）共用。项目间仍保持严格隔离：指标语义、
卡片结构、配色由各看板本地决定。

| 文件 | 作用 |
|---|---|
| `svg_charts.py` | SVG 图表库：`make_line_svg` / `make_line_svg_wide` / `make_stacked_bar_svg` / `make_pct_stacked_bar_svg` / `make_placeholder`（canonical 780×300） |
| `charts.js` | 前端：sparkline 渲染、趋势图模态框、`__CHARTS__` 内联注入（`CommonCharts`） |
| `ha_premium.py` | **H/A 溢价率（日频）**：取数 → 合成 → CSV 快照 → 趋势图/sparkline/JSON/内嵌数据块 |
| `ha-premium.js` | **H/A 溢价率卡片内嵌图**：读内嵌 JSON 渲染 SVG，并在「刷新行情」后同步更新末点 |
| `reinject_svgs.py` | 把 `svg/*.svg` 按文件名写回 HTML 的 `var __CHARTS__` |
| `embed_svgs_phase3.py` / `verify_phase3.py` / `jsdom_check_phase3.cjs` | Phase 3 迁移与校验脚本（历史用途） |

---

## `ha_premium.py` — H/A 溢价率（日频）

任意 A+H 双重上市标的，一条命令产出「H/A 溢价率日频序列」与配套 SVG。

### 口径（与 `worker/index.js` 的 `decorate()` 完全一致）

```
premium = H股收盘价(港元) × HKD/CNY ÷ A股收盘价 − 1
```

- 负值 = **H 股相对 A 股折价**；正值 = H 股溢价。
- 这是 **H/A 溢价率**，不是「AH 溢价」（后者 = A/H − 1，方向相反、符号相反）。
- 必须用**未复权**收盘价。前复权（`qfq`）会按 A 股分红调整历史价，使历史溢价率失真。

### 数据源（免费、无需 key）

| 数据 | 源 | 说明 |
|---|---|---|
| A/H 日线 | 腾讯 gtimg `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | 不传 fq 参数即未复权；单次最多约 **800 根（≈3.3 年）** |
| HKD/CNY | frankfurter.dev（ECB 日参考价，主） | JSON，默认源 |
| HKD/CNY | ECB 官方 `eurofxref-hist.zip`（备） | `CNY/HKD` 交叉汇率算出，可回溯至 1999，主源失败自动回退 |

> 东财 `push2his` 的 `133.HKDCNH` 曾经可用，2026-10 实测间歇性返回空，**未采用为主/备源**。
> ECB 参考价截至前一日 16:00 CET；**当日盘中值以看板「刷新行情」（Worker 实时汇率）为准**，
> 因此快照最后一点与行情条之间可能有 ±0.02~0.05pp 的差异，属正常。

### 命令行

```bash
# 联网取数 + 写快照 + 出两张图（在项目根执行）
python common/ha_premium.py \
  --a sh601898 --h hk01898 \
  --title "中煤能源 H/A 溢价率（日频）" \
  --csv  china-coal/数据源/ha_premium_601898.csv \
  --trend china-coal/svg/trend_ha_premium.svg \
  --spark china-coal/svg/spark_ha_premium.svg

# 代码可省略市场前缀：601898 → sh601898，01898 → hk01898
python common/ha_premium.py --a 601898 --h 01898 --bars 400

# 离线重绘（完全不联网，保证 SVG 逐字节可重建；适合上线前回归）
python common/ha_premium.py --offline --csv 数据源/ha_premium_601898.csv \
  --trend svg/trend_ha_premium.svg --no-fill
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--bars N` | 日线根数，默认 400，上限 800（超出自动截断并告警） |
| `--start/--end` | 截取区间 `YYYY-MM-DD` |
| `--fx auto\|frankfurter\|ecb` | 汇率源，默认 auto（依次回退） |
| `--months-every N` | x 轴每几个月标一次，默认 2 |
| `--embed-html F` | 把序列写入看板 HTML 的 `script#haPremiumData`（卡片内嵌图用，幂等） |
| `--color / --no-fill / --json` | 线色、关闭面积、导出前端用 JSON |

### 作为库调用

```python
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common.ha_premium import build_series, render_trend_svg, render_spark_svg, save_csv

rows, meta = build_series("sh601898", "hk01898", bars=400)   # [{date,a,h,fx,pct}, ...]
save_csv("数据源/ha_premium_601898.csv", rows, meta)          # 快照（可离线重建）
svg = render_trend_svg(rows, "中煤能源 H/A 溢价率（日频）")
```

### 接入一个新看板（4 步）

1. **取数出图**：跑上面的 CLI，SVG 落在 `<看板>/svg/`（若只要卡片内嵌图，可省略 `--trend/--spark`，
   改用 `--embed-html` 直接写序列）。
2. **加占位**：卡片内放
   ```html
   <div class="hachart" data-ha-key="601898">
     <div class="hachart-hd">
       <span class="hachart-tt">H/A 溢价率 · 日频</span>
       <span class="hachart-sub" data-ha-sub></span>
       <span class="hachart-val" data-ha-latest>—</span>
       <span class="hachart-chg" data-ha-chg></span>
     </div>
     <div class="hachart-body"><div class="ha-tip"></div><div class="ha-svg"></div></div>
   </div>
   ```
   并引入 `<script src="../common/ha-premium.js" defer></script>`。
   `data-ha-key` 必须与数据块里的键一致（默认取 A 代码的 6 位数字）。
3. **写数据与文字**：`python common/ha_premium.py ... --embed-html <dashboard>.html --embed-key 601898`
   会写入/更新 `<script id="haPremiumData" type="application/json">`（幂等，多标的可共存同一个块）。
4. **卡片实时值**（可选）：行情条里加 `<span class="ql">H/A溢价率</span>`，
   `quote-live.js` 会自动按 `__premium__` 填充。

> 若还需模态趋势图，再补 `data-img` / `data-chart` 占位 + `common/reinject_svgs.py` 写回。

### `ha-premium.js` — 卡片内嵌图与行情联动

- **渲染**：读 `script#haPremiumData` → 按容器实际宽度生成 SVG（1:1 像素，文字不随宽度缩放），
  窗口 resize 后 150ms 防抖重绘；鼠标悬停显示十字线与当日数值。
- **联动**：`quote-live.js` 每次成功刷新会在 `document` 上派发 `quote:updated`
  （`detail = { bar, data }`，`data.premium` 为小数比例），本模块收到后按下列规则更新：
  | 情形 | 行为 |
  |---|---|
  | 末点日期 == 今天 | 就地改写末点数值（保留盘中标记） |
  | 末点日期 < 今天且为工作日 | 追加「盘中」点（空心圆标识，副标题加「含盘中」） |
  | 末点日期 < 今天且为周末 | 只按最新汇率重算末点（周末行情仍是上周五收盘，不新增点） |
  | 末点日期 > 今天 | 忽略（历史快照不回改） |
- **样式**：`.hachart*` 与 `.ha-tip` 由各看板 CSS 提供（见 china-coal 内联样式），模块不注入样式。
- **降级**：无数据块 / 老浏览器不支持 `CustomEvent` 时静默跳过，不影响卡片其余内容。

### 注意事项 / 已知坑

- **除权日台阶**：A、H 除息日不同步，未复权序列在除息日会出现 1–3pp 的瞬时台阶（例如招商银行
  2026-07 的凹陷）。这是真实价差而非数据错误；若要剔除，需引入分红数据做同步调整，当前不处理。
- **交易日取交集**：A/H 假期不同（如佛诞、国庆），只保留两市均开市的日期；汇率缺失日按前值填充，
  早于汇率覆盖起点的日期直接跳过并在 `meta.skipped` 中记录。
- **停牌**：长期停牌会让序列出现长平台，图表按观测点等距绘制，不体现日历空缺。
- **可复现**：`--offline` 只读 CSV，重绘结果与联网时逐字节一致（已用 md5 验证）。
- **不在本模块做的事**：不写 xlsx、不碰 HTML 结构、不定义配色语义——这些由各看板自行决定。
