#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目统一入口。

    python run.py extract   解析 data/raw（PDF / Excel）与内置手工数据 -> data/processed/
    python run.py dataset   抓取线上五维数据 + 合并离线产物      -> data/dataset/
    python run.py html      渲染 data/dataset/                  -> output/*.html
    python run.py build     = dataset + html
    python run.py all       = extract + dataset + html
    python run.py serve [端口]   本地预览（默认 8000，带 FRED/EIA 代理）

各子命令都以子进程方式调用 src 下对应模块，单个失败不会污染其它步骤。
"""
import os
import shutil
import subprocess
import sys

# 产物可复现性要求：3.12+ 的 sum() 用 Neumaier 补偿求和，但 3.13 与 3.14 对
# 「int 混入 float 列表」的处理不同，会让 composite 末位浮点数字漂移，
# 导致同一份数据渲染出的 HTML 无法字节复现。这里只做提醒，不强行拦截。
EXPECTED_PY = (3, 13)

# extract 需要 pdfplumber / openpyxl 两个**可选**依赖，它们装在独立 venv 里，
# 而不是日常构建用的解释器里。下面依次尝试，取第一个真正带依赖的解释器。
EXTRACT_DEPS = ("pdfplumber", "openpyxl", "pymupdf")

# dataset 需要 yfinance / pandas 两个**刷新期**依赖（只有 Brent 期限结构用得到，
# 装在 .venv 里）。2026-10-07 的坑：日常 `python run.py dataset` 走的是系统
# 3.14 解释器，它没装这两个包 → brent_term 降级为空，页面上只剩一句
# 「本期未取到 Brent 期限结构数据」，而 .venv 里明明装得好好的。
# 所以 dataset / build 一律按下面的候选顺序挑解释器，别再硬用 sys.executable。
DATASET_DEPS = ("yfinance", "pandas")

# 离线解析脚本：把 data/raw/ 下的 PDF / Excel 与内置手工数据解析成 data/processed/*.json
EXTRACTORS = [
    ("EIA《AEO 20XX》美国液体燃料消费 (eia_aeo xlsx → PSD000:fa_Total 逐年原值)", "src.extract.eia_aeo"),
    ("IEA《Oil 20XX》中期展望需求路径 (iea_oil PDF → Total products 行)", "src.extract.iea_oil"),
    # ⚠️ 2026-10-11 摘除 src.fetch.supply.opec_momr（MOMR 表 5-7）登记：OPEC 原油产量图与
    #    Non-OPEC DoC 图均换源 STEO base tables 表 3d（steo_monthly），其产出键已全部下线。
    #    脚本与其存档 opec_monthly.json 已于 2026-10-23 移出仓库，
    #    口径要点留档在 README「已下线口径留档」。
    # ⚠️ 2026-10-16 摘除 src.fetch.supply.steo_monthly 的登记：世界 / OPEC / 非 OPEC 的
    #    月度原油产量已由「手工下载 STEO base tables xlsx + 离线解析」换成 **EIA STEO 官方
    #    实时 API**，并移到 `dataset` 步骤（build_dataset 里调用 steo_monthly.fetch()），
    #    这样 `python run.py build` 每月自动取到最新一期 —— 挂在 extract 步骤时 build 不刷新。
    #    （data/raw/eia_steo/*_base.xlsx 与旧解析逻辑留档，不再参与流水线。）
    ("美国 SPR (EIA 周度石油周报 API · PET.WCSSTUS1.W)", "src.fetch.supply.us_spr"),
    ("OECD 商业原油库存 (MOMR 表 9-1)", "src.fetch.supply.oecd_stocks"),
    ("全球钻井数 (Baker Hughes Excel)", "src.fetch.supply.rig_count"),
    ("制造业 PMI / GDP 预期", "src.fetch.demand.pmi_gdp"),
    ("炼厂开工率 / 中国加工量进口量", "src.fetch.demand.refinery"),
    # 2026-10-14 新增：EIA STEO 表 2 的 Brent/WTI 现货均价预测（逐期年度值），
    # 供「未来展望」模块 outlook8（EIA 油价基准预测）使用。与 IMF 的季度油价面板
    # 并列成「原油价格预测」组 —— 全球只有这两家发布油价预测。
    ("EIA STEO 表 2 油价预测（PDF → Brent/WTI 逐期年度值）", "src.extract.eia_steo_price"),
]

COMMANDS = {
    "extract": "解析离线原始数据 -> data/processed/",
    "dataset": "抓取线上数据并合并 -> data/dataset/",
    "html": "渲染单文件仪表盘 -> output/",
    "build": "dataset + html",
    "all": "extract + dataset + html",
    "serve": "启动本地服务器（默认 8000）",
}


def _root():
    return os.path.dirname(os.path.abspath(__file__))


def run(module, *args, python=None):
    """以子进程运行一个模块，返回退出码。python 缺省用当前解释器。"""
    cmd = [python or sys.executable, "-m", module, *args]
    return subprocess.run(cmd, cwd=_root()).returncode


def _version(python):
    """取解释器的版本号字符串，取不到返回 '?'。"""
    out = subprocess.run([python, "-V"], capture_output=True, text=True)
    return (out.stdout or out.stderr).strip().replace("Python ", "") or "?"


def _has_deps(python, deps=EXTRACT_DEPS):
    """该解释器是否装齐了给定依赖（默认 extract 的可选依赖）。"""
    if not python:
        return False
    if not (os.path.exists(python) or shutil.which(python)):
        return False
    probe = "import " + ", ".join(deps)
    return subprocess.run([python, "-c", probe],
                          capture_output=True).returncode == 0


def _extract_python():
    """挑一个带可选依赖的解释器跑 extract。

    优先级：$EXTRACT_PYTHON > 项目内 .venv > 当前解释器。
    都不带依赖时照常返回当前解释器 —— src/common/deps.py 会打印安装指引
    并以退出码 3 退出，本文件把它记为「跳过」而非失败。
    """
    candidates = [os.environ.get("EXTRACT_PYTHON"),
                  os.path.join(_root(), ".venv", "bin", "python"),
                  sys.executable]
    for python in candidates:
        if _has_deps(python):
            return python
    return sys.executable


def _dataset_python():
    """挑一个带刷新期依赖（yfinance / pandas）的解释器跑 dataset / build。

    优先级：$DATASET_PYTHON > 项目内 .venv（3.13.12，依赖版本按 requirements.txt 锁死）
    > 当前解释器。选到 .venv 还顺带解决「产物字节复现」：3.13 与 3.14 的
    sum() 浮点差异会让 composite 末位漂移（见 EXPECTED_PY 的注释）。
    三个候选都不带依赖时返回当前解释器，由 brent_term 自己降级并打印指引。
    """
    candidates = [os.environ.get("DATASET_PYTHON"),
                  os.path.join(_root(), ".venv", "bin", "python"),
                  sys.executable]
    for python in candidates:
        if _has_deps(python, DATASET_DEPS):
            return python
    return sys.executable


def cmd_extract():
    """逐个跑离线解析脚本。

    pdfplumber 等可选依赖缺失时脚本以退出码 3 退出，这里只记为「跳过」而非失败，
    因为这只影响重解析 PDF，不影响 build 链路。
    """
    from src.common.deps import EXIT_CODE_MISSING_DEP

    py = _extract_python()
    print(f"extract 使用解释器: {py} (python {_version(py)})")

    failed, skipped = [], []
    for label, module in EXTRACTORS:
        print(f"\n=== extract: {label} ===")
        code = run(module, python=py)
        if code == EXIT_CODE_MISSING_DEP:
            print(f"  -- 跳过（缺可选依赖）: {label}")
            skipped.append(label)
        elif code != 0:
            print(f"  !! 失败: {label}")
            failed.append(label)

    print("\n--- extract 汇总 ---")
    print(f"成功 {len(EXTRACTORS) - len(failed) - len(skipped)} / {len(EXTRACTORS)}")
    if skipped:
        print("跳过（缺可选依赖，装好后重跑即可）:")
        for name in skipped:
            print("  -", name)
    if failed:
        print("失败:")
        for name in failed:
            print("  -", name)
    return 1 if failed else 0


def cmd_dataset():
    py = _dataset_python()
    print(f"dataset 使用解释器: {py} (python {_version(py)})")
    return run("src.pipeline.build_dataset", python=py)


def cmd_html():
    py = _dataset_python()
    print(f"html 使用解释器: {py} (python {_version(py)})")
    return run("src.pipeline.build_html", python=py)


def cmd_build():
    # 两步都走同一个解释器：只让 dataset 换 3.13、html 仍用 3.14，
    # 会出现「数据来自 3.13、渲染结果来自 3.14」的浮点漂移，产出不再是字节可复现的
    py = _dataset_python()
    print(f"build 使用解释器: {py} (python {_version(py)})")
    return run("src.pipeline.build_dataset", python=py) or run("src.pipeline.build_html", python=py)


def cmd_all():
    # extract 中个别脚本可能因缺 pdfplumber/openpyxl 失败，不阻断后续步骤
    cmd_extract()
    return cmd_build()


def cmd_serve(port=None):
    return run("src.serve", *([port] if port else []))


def _check_python():
    if sys.version_info[:2] != EXPECTED_PY:
        cur = ".".join(str(x) for x in sys.version_info[:3])
        print(f"⚠️  当前 Python {cur}，推荐 {EXPECTED_PY[0]}.{EXPECTED_PY[1]}.x；"
              f"版本不一致会让产物 HTML 无法与既有版本字节复现。")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        print("可用命令：")
        for name, desc in COMMANDS.items():
            print(f"  {name:10s} {desc}")
        return 0

    _check_python()
    cmd, rest = args[0], args[1:]
    if cmd == "extract":
        return cmd_extract()
    if cmd == "dataset":
        return cmd_dataset()
    if cmd == "html":
        return cmd_html()
    if cmd == "build":
        return cmd_build()
    if cmd == "all":
        return cmd_all()
    if cmd == "serve":
        return cmd_serve(rest[0] if rest else None)

    print(f"未知命令：{cmd}")
    print("可用命令：" + ", ".join(COMMANDS))
    return 2


if __name__ == "__main__":
    sys.exit(main())
