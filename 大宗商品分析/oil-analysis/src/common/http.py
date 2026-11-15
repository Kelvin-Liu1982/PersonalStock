# -*- coding: utf-8 -*-
"""HTTP 抓取公共层。

统一收口 curl / urlopen 两种通道、重试与超时，避免每个抓取脚本各写一份。
所有函数在失败时返回空结果而非抛出，保证单个数据源挂掉不会中断整条流水线。
"""
import csv
import io
import json
import subprocess
import time
import urllib.request


def _curl(url, timeout=40, retries=0, retry_delay=2, user_agent=None):
    cmd = ["curl", "-s", "--max-time", str(timeout)]
    if user_agent:
        cmd += ["-A", user_agent]
    if retries:
        cmd += ["--retry", str(retries), "--retry-delay", str(retry_delay)]
    cmd.append(url)
    return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()


def fetch_fred_csv(series_id, start, tries=3, pause=2, timeout=40):
    """抓取 FRED 的 fredgraph CSV，返回 ``{YYYY-MM-DD: float}``。全部重试失败返回 {}。"""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    for _ in range(tries):
        try:
            data = _curl(url, timeout=timeout)
            break
        except Exception:
            time.sleep(pause)
    else:
        return {}

    out = {}
    rows = list(csv.reader(io.StringIO(data)))[1:]
    # ⚠️ FRED 维护期会返回 **HTTP 200 的 HTML 维护页**（2026-10-22 实测：
    #    fredgraph.csv 与 api.stlouisfed.org 双双如此）。curl 不报错、每行都过不了
    #    float() 而被跳过 → 静默返回 {}，上层分不清「FRED 挂了」和「序列真的没更新」。
    #    这里显式报警，让「无数据」带上原因（回落逻辑见 build_dataset._fallback_fred）。
    if not out and data.strip()[:1] == "<":
        print(f"  [fred]  ⚠ {series_id} 返回 HTML 而非 CSV（FRED 维护/拦截页？），本次视为无数据")
    elif not rows:
        print(f"  [fred]  ⚠ {series_id} 返回体无数据行（{len(data)} B），本次视为无数据")
    for row in rows:
        if len(row) < 2:
            continue
        date, value = row[0], row[1]
        # FRED 用 "." 表示缺失、"ND" 表示无定义
        if not value.strip() or value in (".", "ND"):
            continue
        try:
            out[date] = float(value)
        except ValueError:
            pass
    return out


def fetch_fred_group(series_map, start, label):
    """批量抓取一组 FRED 序列，返回 ``{key: {YYYY-MM-DD: float}}``。

    prices（价格基准）与 fred_macro（宏观金融）此前各写一份同样的循环，
    改日志格式或加重试要改两处；收口到这里后只保留一份实现。
    """
    out = {}
    prefix = f"  [{label}]".ljust(12)
    for key, series_id in series_map.items():
        out[key] = fetch_fred_csv(series_id, start)
        last = list(out[key])[-1] if out[key] else None
        print(f"{prefix}{key}: {len(out[key])} pts, last={last}")
    return out


def fetch_json_curl(url, tries=1, pause=2, timeout=40, curl_retry=0, user_agent=None):
    """用 curl 抓 JSON（EIA 等接口对 curl 的兼容性好于 urllib）。失败返回 {}。"""
    for attempt in range(tries):
        try:
            return json.loads(_curl(url, timeout=timeout, retries=curl_retry, user_agent=user_agent))
        except Exception as exc:
            if attempt == tries - 1:
                print("   fetch_json_curl failed:", exc)
                return {}
            time.sleep(pause)
    return {}


def fetch_json_urlopen(url, headers=None, timeout=40):
    """用 urllib 抓 JSON（Yahoo 等需要自定义 UA 的接口）。失败返回 {}。"""
    try:
        request = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except Exception as exc:
        print("   fetch_json_urlopen failed:", exc)
        return {}
