# -*- coding: utf-8 -*-
"""数据源配置：端点、FRED 序列、鉴权。

FRED key 读取优先级：环境变量 FRED_API_KEY > src/_keys_local.py（已 gitignore）> 空。
未配置 key 时，fetch 脚本跳过 FRED 相关序列并保留 Excel 中的快照值（优雅回退）。
"""
import os

# ---------- 实时行情 ----------
GOLD_API = "https://api.gold-api.com/price/XAU"
REQUEST_TIMEOUT = 8
USER_AGENT = "Mozilla/5.0"

# 网络重试：FRED 对新建连接偶发 SSL 握手重置，首次请求常失败、重试即成功。
# HTTP 4xx/5xx 属确定性错误，不重试。
HTTP_RETRIES = 4
HTTP_RETRY_DELAY = 0.6  # 退避基数：0.6s / 1.2s / 1.8s

# ---------- FRED ----------
# 申请地址：https://fred.stlouisfed.org/docs/api/api_key.html
# 凭据读取优先级：环境变量 FRED_API_KEY > src/_keys_local.py（已 gitignore）> 空。
# 仓库内不保存真实 key；未配置时 fetch 跳过 FRED 序列并沿用 Excel 快照值。
def _local_fred_key():
    try:
        from . import _keys_local as _k
    except Exception:
        try:
            import _keys_local as _k
        except Exception:
            return ""
    return str(getattr(_k, "FRED_API_KEY", "") or "").strip()


FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip() or _local_fred_key()
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# ---------- 美元指数 ----------
# FRED 没有 ICE DXY（页面用的口径，量级 ~98），只有广义美元指数 DTWEXBGS（量级 ~120）。
# 若你有可用的 ICE DXY 接口，填在下面，fetch 会直接覆盖 tickerDxy；
# 留空则只把 DTWEXBGS 写入参考字段 dxyBroad，tickerDxy 保持人工维护。
DXY_API = ""

# FRED 序列 ID
FRED_SERIES = {
    # 10Y 美债收益率（日）—— 页面 TICKER「10Y UST」
    "tickerUst": "DGS10",
    # 广义美元指数（日）—— 页面 TICKER「DXY」；FRED 无 ICE DXY，用广义美元指数近似
    "tickerDxy": "DTWEXBGS",
    # 联邦债务 / GDP（年）—— 页面 TICKER「WORLD DEBT/GDP」与债务面板
    "worldDebt": "GFDGDPA188S",
    # 联邦净利息支出 / GDP（年）—— 债务面板「利息/GDP」
    "interestGdp": "FYOIGDA188S",
}

# ---------- IMF IFS：央行购金「货币黄金变动」官方口径 ----------
# 源文件：IMF International Financial Statistics，Changes in Monetary Gold（月度+年度两个 sheet）。
# 放在 data/ 目录随项目保存，文件名带 as-of 日期；fetch 时取最新覆盖的当年数据。
IFS_XLSX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "Changes_latest_as_of_Nov2026_IFS.xlsx")
IFS_SOURCE_LABEL = "IMF IFS 官方储备变动"

# 需要从汇总中剔除的行（正则，匹配源表 Country 列），原因写在注释里：
IFS_EXCLUDE = [
    (r"^Euro Area", "ECB 口径，仅在年初一次性披露年度变动，不是月度流量"),
    (r"^Türkiye", "土耳其 gross（总额）口径重复序列，含银行体系流动性黄金"),
    (r"^Turkey\*$", "部分版本用 * 标记 gross 总额口径（与 Türkiye 同一序列），净额口径以 Turkey 为准"),
    (r"^State Oil Fund", "阿塞拜疆国家石油基金，主权财富基金而非央行"),
]

# 图 1「各央行净购金量对比」的取数规则：截止今年当月，净买入前 N + 净卖出前 N
IFS_TOP_BUYERS = 10
IFS_TOP_SELLERS = 5

# ---------- WGC《Gold Demand Trends》季度表：全球黄金供需 ----------
# 源文件为 WGC 每季度发布的表格包，Gold Balance sheet 含年度 + 季度两块。
GDT_XLSX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "GDT_Tables_Q326.xlsx")
# 图表展示的季度数：0 = 全量（源表 2010Q1–2026Q3 共 67 个季度）；
# 若只想画最近若干季，改成数字即可（数据仍按全量存 Excel，窗口只影响图表）。
GDT_QUARTERS = 0
# 来源标注
GDT_SOURCE = "WGC《Gold Demand Trends》Gold Balance（Metals Focus / Refinitiv GFMS / ICSG）"

# ---------- 世界银行 Pink Sheet：月度黄金参考价 ----------
# 官方页 https://www.worldbank.org/en/research/commodity-markets → "Monthly prices"
# Gold 列口径（Description sheet）：spot average of daily rates（2025-06 前为 London PM fixing
# 99.5% fine 的日均价），按月平均，单位 USD/troy oz；与实时现货价不是同一口径。
# ⚠️ URL 里的 doc id 含版本，若失效请到上述官方页复制最新 "Monthly prices" 链接。
CMO_MONTHLY_URL = ("https://thedocs.worldbank.org/en/doc/"
                   "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
                   "CMO-Historical-Data-Monthly.xlsx")
CMO_MONTHLY_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "data", "cmo_monthly_prices.xlsx")

# ---------- A 模块宏观因子（方案 2：现值徽章 + mini sparkline）----------
# 五个因子全部走「本地 fetch -> xlsx -> build_html 注入」；浏览器端不抓（FRED/Yahoo/GPR 均无 CORS）。
# 实测可用（2026-11-05），详见 数据fetch方案.md 第八节。
FRED_SERIES_MACRO = {
    # A2：10Y TIPS 收益率 = 市场口径实际利率（日频）
    "A2": "DFII10",
    # A7：10Y 盈亏平衡通胀率（名义 − 通胀保值债隐含），衡量市场通胀预期。
    # 此前仅作 A2 口径对照；现升格为独立因子 A7（力矩阵「推涨②通胀预期」状态灯）。
    "A7": "T10YIE",
    # A6 分母：WTI 现货（日频，美元/桶）
    "oil": "DCOILWTICO",
}
FRED_MACRO_START_MONTHS = 13   # 拉最近 13 个月，再降采样到 52 周
FRED_MACRO_LIMIT = 2000

# Yahoo chart 日线（免费无 key）：A3 ICE DXY + A6 分子金价 + A8 VIX
YAHOO_SYM = {"gold": "GC=F", "dxy": "DX-Y.NYB", "vix": "^VIX"}
YAHOO_RANGE_MACRO = "1y"
# ⚠️ 口径：GC=F 是 COMEX 期货、DCOILWTICO 是 WTI 现货，金油比仅作趋势观察，
#    单位「桶/盎司」；ICE DXY(≈101) ≠ FRED 广义美元 DTWEXBGS(≈121)，不可互换。

# A5：Caldara-Iacoviello 地缘政治风险指数（日频 xls，GPRD_MA30 为 30 日均）
GPR_XLS_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
GPR_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "gpr_daily_recent.xls")
GPR_DAYS = 400          # 只取最近 400 天
# A4：不另采，直接复用「黄金供需季度」的「央行及其他机构」列（WGC 口径，季度）
MACRO_A4_QUARTERS = 12
MACRO_SERIES_WEEKS = 52  # 日频统一降采样为周频（每周最后一个有效值）

# ---------- 事件条（event bar）：免费新闻 RSS + 日线涨跌幅 ----------
# event 三字段（eventDate / eventPct / eventText）原先是纯人工快照，会滞后。
# 现改为 fetch：新闻标题 -> eventText，新闻日期 -> eventDate，当日金价涨跌 -> eventPct。
#
# 主源用 Google News RSS：免费、无需 key、支持关键词 + 语言 + when:Nd 时间窗。
# 实测可用（2026-10-11）：中文 q=黄金 金价 / 英文 q=gold price。
# 备选实测可用源（如需换成快讯流，改下面的 EVENT_FEEDS 即可）：
#   华尔街见闻  https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&client=pc&limit=20
#   东方财富    https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_50_1_.html
#   Investing   https://www.investing.com/rss/news.rss
# ❌ 不可用：Stooq（JS 反爬）、Kitco RSS（404）、mining.com（403）、
#           FRED 伦敦金定盘价 GOLDPMGBD228NLBM（已下架）。

# 日线收盘价（算 eventPct 用）：Yahoo chart 接口，免费无 key。
# GC=F = COMEX 黄金期货连续，与 XAU/USD 现货有基差但日涨跌方向/幅度基本一致。
YAHOO_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
               "?range={rng}&interval=1d")
YAHOO_GOLD_SYM = "GC=F"
YAHOO_RANGE = "6mo"

# 新闻源。{q} 会被替换成 query（需 URL 编码由脚本处理）。
EVENT_FEEDS = [
    {"name": "Google News · 中文", "lang": "zh", "weight": 1.00,
     "query": "黄金 金价",
     "url": "https://news.google.com/rss/search?q={q}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"},
    {"name": "Google News · 中文·央行", "lang": "zh", "weight": 1.05,
     "query": "黄金 央行 购金 储备",
     "url": "https://news.google.com/rss/search?q={q}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"},
    {"name": "Google News · EN", "lang": "en", "weight": 0.85,
     "query": "gold price",
     "url": "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"},
]

# 相关性：标题必须命中至少一个核心词，否则丢弃（Google News 会混入消费/导购噪音）。
EVENT_CORE_WORDS = ["黄金", "金价", "现货黄金", "贵金属", "gold", "xau", "bullion"]
# 命中则加分（宏观/央行驱动因子），每个 +0.35
EVENT_SIGNAL_WORDS = [
    "央行", "购金", "储备", "增持", "美联储", "fed", "降息", "加息", "利率",
    "cpi", "通胀", "非农", "就业", "美元", "关税", "地缘", "避险", "etf",
    "实际利率", "收益率", "central bank", "rate cut", "inflation", "tariff",
    "safe-haven", "safe haven", "record", "创新高", "新高", "回调", "反弹",
]
# 命中则重罚（金店促销 / 消费导购类噪音），score *= 0.25
EVENT_NOISE_WORDS = ["饰品", "柜台", "克重", "送父母", "婚庆", "促销", "打折",
                     "金店", "专柜", "款", "克价", "回购价", "以旧换新"]
# 来源权重：权威源优先，未列出的按 0.9
EVENT_SOURCE_WEIGHT = {
    "reuters": 1.6, "路透": 1.6, "bloomberg": 1.6, "彭博": 1.6,
    "world gold council": 1.55, "世界黄金协会": 1.55, "wgc": 1.55,
    "kitco": 1.4, "wall street journal": 1.4, "financial times": 1.4, "ft": 1.4,
    "华尔街见闻": 1.25, "财联社": 1.25, "investing.com": 1.2, "fxstreet": 1.1,
    "新浪财经": 1.1, "东方财富": 1.1, "证券时报": 1.1, "第一财经": 1.1,
    "经济观察网": 1.0, "yahoo finance": 1.0, "cnbc": 1.2, "marketwatch": 1.1,
}
# 明确降权的聚合/地方站（不是黑名单，只是排后面）
EVENT_SOURCE_PENALTY = {
    "杭州网": 0.4, "新湖南": 0.4, "京报网": 0.5, "观点网": 0.6,
    "jck": 0.4, "fortune": 0.6, "forex factory": 0.7, "stonex": 0.7,
    "the economic times": 0.6,
}
EVENT_WINDOW_DAYS = 3      # 只看最近 N 天的新闻；窗口内无命中则放宽到 EVENT_WINDOW_FALLBACK
EVENT_WINDOW_FALLBACK = 10 # 兜底窗口
# eventText 最大长度：中文按字符、英文/拉丁按字符分开给（同屏宽度下英文信息密度约 2.3 倍）
EVENT_TEXT_MAX_CJK = 34
EVENT_TEXT_MAX_LATIN = 78
EVENT_KEEP_ROWS = 40       # 「黄金事件流」sheet 保留条数

# ---------- 无法程序化抓取、需人工填 Excel 的数据 ----------
# WGC 央行购金（季度）：无公开 API，只有季报 PDF / 网页表格。
# 流程：人工取数 -> 填入 data/gold_data.xlsx「央行购金*」sheet -> build_html 生效。
MANUAL_ONLY = [
    "中国 H1 净进口 764t（WGC 净进口口径 / 海关 HS7108）",
    "WGC 年度净购 863t / 2025 年口径（与 IFS 年度表非同一口径，勿混用）",
]
