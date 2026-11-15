# -*- coding: utf-8 -*-
"""
本地服务器：托管 output/ 下的仪表盘，并代理 FRED / EIA API。

为什么需要它：
  FRED 公共 API 不返回 CORS 头，浏览器里直接 fetch 会被同源策略拦截
  （表现为 "Failed to fetch"）。本服务在本地（localhost，同源）转发请求，
  FRED/EIA 的真实请求在服务端发起（不受 CORS 限制），再把 JSON 回给页面。

用法（在仓库根目录执行）：
  python -m src.serve            # 默认 http://localhost:8000/
  python -m src.serve 9000       # 自定义端口
然后浏览器打开 http://localhost:8000/ ，填 Key 点「拉取实时」。

注意：这是**单线程** HTTPServer。一旦有浏览器保持 keep-alive 连接不释放，
后续所有请求都会被阻塞（表现为页面一直转圈、curl 返回 000/超时）。
调试时若怀疑卡死，先关掉残留的 headless Chrome / 旧进程再重启本服务。
"""
import json
import os
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

# 允许从任意目录启动（如 `python3 src/serve.py` 或 `cd src && python3 serve.py`）：
# 把仓库根目录（src/ 的父目录）加入 sys.path，使 `src` 包可被导入。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src import config
from src.paths import OUTPUT_DIR as OUT_DIR

# 静态文件根目录的真实路径（解析掉符号链接）；路径穿越校验以它为准，只算一次。
_OUT_REAL = os.path.realpath(OUT_DIR)

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
EIA_URL = "https://api.eia.gov/v2/seriesid"

_CT = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def _curl_json(url, label):
    # 用 curl 而非 urllib：本环境 Python 的 ssl 栈连 FRED 会 SSL EOF，curl 正常
    out = subprocess.run(
        ["curl", "-sS", "--fail", "--max-time", "40", url],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"{label}请求失败: {out.stderr.strip()[:200]}")
    return json.loads(out.stdout)


def _proxy_fred(key, ids, start):
    merged = {}
    for sid in ids:
        url = f"{FRED_URL}?series_id={sid}&api_key={key}&file_type=json&observation_start={start}"
        data = _curl_json(url, "FRED")
        for o in data.get("observations", []):
            if o.get("value") not in (".", None):
                merged.setdefault(o["date"], {})[sid] = float(o["value"])
    return {"map": merged}


def _proxy_eia(key, ids, length=None):
    """代理 EIA v2 seriesid。``length`` 用于限流：日度序列默认会返回 5000 个观测
    （2006 年至今），而看板只需要 2024 起的那一段 —— 不限流会白传三千多个点，
    在单线程 HTTPServer 上直接体现为「拉取实时」多等几十秒（2026-10-08 实测）。
    """
    merged = {}
    for sid in ids:
        url = f"{EIA_URL}/{sid}?api_key={key}"
        if length:
            url += f"&length={length}"
        data = _curl_json(url, "EIA")
        m = {}
        for p in data.get("response", {}).get("data", []):
            if p.get("value") is not None:
                m[p["period"]] = float(p["value"])
        merged[sid] = m
    return {"map": merged}


def resolve_static(rel):
    """把 URL 相对路径映射到 output/ 下的绝对路径；越界或非法时返回 None。

    ⚠️ 不能用字符串前缀判断（``fpath.startswith(OUT_DIR)``）：
    同级目录名 ``outputX`` 会被前缀匹配放过（``/…/outputX/secret`` startswith ``/…/output``）。
    另外 ``os.path.join`` 遇到绝对路径参数会整体覆盖根目录，也必须靠 commonpath 拦掉。
    """
    try:
        fpath = os.path.realpath(os.path.join(_OUT_REAL, rel))
    except ValueError:  # rel 含 NUL 字节等非法字符
        return None
    if os.path.commonpath([fpath, _OUT_REAL]) != _OUT_REAL:
        return None
    return fpath


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, fpath):
        with open(fpath, "rb") as f:
            content = f.read()
        ext = os.path.splitext(fpath)[1].lower()
        self.send_response(200)
        self.send_header("Content-Type", _CT.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/fred":
                qs = urllib.parse.parse_qs(parsed.query)
                key = qs.get("key", [""])[0]
                ids = [x for x in qs.get("ids", [""])[0].split(",") if x]
                start = qs.get("start", [config.START_DATE])[0]
                if not key or not ids:
                    return self._send_json(400, {"error": "缺少 key 或 ids"})
                return self._send_json(200, _proxy_fred(key, ids, start))
            if parsed.path == "/api/eia":
                qs = urllib.parse.parse_qs(parsed.query)
                key = qs.get("key", [""])[0]
                ids = [x for x in qs.get("ids", [""])[0].split(",") if x]
                length = qs.get("length", [""])[0]
                if not key or not ids:
                    return self._send_json(400, {"error": "缺少 key 或 ids"})
                return self._send_json(200, _proxy_eia(key, ids, length))
            if parsed.path == "/api/news":
                # 原油快讯增量抓取：区间 = [本地最后日期, 今天]。
                # ⚠️ Argus 有 AWS WAF 挑战，非浏览器请求会拿到挑战页；
                #    此时返回 ok=false / blocked=true，由前端把原因显示出来，不假装成功。
                try:
                    from src.fetch.news import argus as argus_news
                    qs = urllib.parse.parse_qs(parsed.query)
                    until = qs.get("until", [""])[0] or None
                    return self._send_json(200, argus_news.run(until=until))
                except Exception as e:
                    return self._send_json(502, {"ok": False, "error": str(e)})
            # 静态文件：映射到 output/
            # ⚠️ 路径穿越防护必须用 commonpath 而不是字符串前缀判断：
            # 前缀判断会被同级目录名骗过（rel="../outputX/secret" -> /…/outputX/secret
            # 仍然 startswith /…/output）。另外 join() 遇到绝对路径 rel 会整体覆盖
            # 根目录，也必须靠 commonpath 拦掉。
            rel = urllib.parse.unquote(parsed.path.lstrip("/"))
            if rel == "":
                rel = "crude_oil_dashboard.html"
            fpath = resolve_static(rel)
            if fpath is None:
                return self._send_json(403, {"error": "forbidden"})
            if os.path.isfile(fpath):
                return self._send_file(fpath)
            return self._send_json(404, {"error": "not found: " + rel})
        except Exception as e:  # 代理上游出错（Key 错 / 网络不通 / 超时）
            return self._send_json(502, {"error": str(e)})

    def log_message(self, fmt, *args):
        sys.stderr.write("[serve] " + (fmt % args) + "\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    # ThreadingHTTPServer：/api/news 会启动无头 Chromium 渲染 Argus 页（数秒级），
    # 单线程会卡住整页，改多线程后抓取期间其它请求仍可响应。
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    Handler.timeout = 120   # 留足浏览器渲染 + 网络时间，避免长请求被提前断开
    print(f"仪表盘已启动： http://localhost:{port}/")
    print("（Ctrl+C 停止）")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
