# -*- coding: utf-8 -*-
"""可选依赖的按需收口。

只有**解析 data/raw 下的离线文件**才需要这些库：

    pdfplumber  解析 OPEC MOMR 月报 PDF（oecd_stocks；原 opec_momr 已下线移出仓库）
    openpyxl    解析 Baker Hughes 钻井数 Excel（rig_count）
    pymupdf     解析 OPEC WOO / IEA《Oil 20XX》长期展望 PDF（opec_woo / iea_oil）

日常刷新链路 `python run.py build` = 抓线上数据 + 渲染，两个都用不到：
build_dataset 的第 [6/6] 步直接读取已解析好的 data/processed/*.json。

所以它们是**可选的、按需安装的依赖**。缺失时给出可操作提示并以固定退出码 3 退出，
而不是抛一长串 traceback —— 便于 run.py extract 识别为「可跳过的失败」而非真失败。
"""
EXIT_CODE_MISSING_DEP = 3

_HINT = "        安装：python3.13 -m pip install -r requirements.txt"


def _missing(lib, purpose):
    print(f"  [deps] 缺少 {lib} —— 仅{purpose}时需要。")
    print(_HINT)
    print("        若只是刷新线上数据 / 重新渲染看板，可跳过：run.py build 不需要它。")
    raise SystemExit(EXIT_CODE_MISSING_DEP)


def require_pdfplumber():
    """返回 pdfplumber；未安装时打印指引并以退出码 3 退出。"""
    try:
        import pdfplumber
    except ImportError:
        _missing("pdfplumber", "解析 OPEC MOMR 月报 PDF")
    return pdfplumber


def require_openpyxl():
    """返回 openpyxl；未安装时打印指引并以退出码 3 退出。"""
    try:
        import openpyxl
    except ImportError:
        _missing("openpyxl", "解析 Baker Hughes 钻井数 Excel")
    return openpyxl


def require_pymupdf():
    """返回 pymupdf（fitz 别名）；未安装时打印指引并以退出码 3 退出。"""
    try:
        import pymupdf
    except ImportError:
        _missing("pymupdf", "解析 OPEC WOO / IEA《Oil 20XX》展望 PDF")
    return pymupdf
