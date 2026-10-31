# -*- coding: utf-8 -*-
"""Alphaliner 同步本地服务 —— 供看板「同步 Alphaliner」按钮调用。

启动：
    cd cosco-shipping
    .venv/bin/python alphaliner_server.py          # 默认 127.0.0.1:8765

接口：
    GET  /health  → {"ok": true, "service": "alphaliner-sync"}
    GET|POST /sync → 抓 Alphaliner PublicTop100 并写入 xlsx 的两个 sheet，返回 JSON

说明：浏览器无法直接写本地 Excel，所以按钮通过本机这个服务落盘；
服务只监听 127.0.0.1，且对跨域请求放开（看板可能是 file:// 或 https:// 打开）。
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alphaliner_sync as sync_mod  # noqa: E402

HOST = "127.0.0.1"
PORT = int(os.environ.get("ALPHALINER_PORT", "8765"))


class Handler(BaseHTTPRequestHandler):
    server_version = "AlphalinerSync/1.0"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/health"):
            self._json(200, {"ok": True, "service": "alphaliner-sync",
                             "endpoints": ["/health", "/sync"],
                             "xlsx": sync_mod.XLSX})
        elif path == "/sync":
            self._do_sync()
        else:
            self._json(404, {"ok": False, "error": "unknown path %s" % path})

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/sync":
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                try:
                    self.rfile.read(n)
                except Exception:
                    pass
            self._do_sync()
        else:
            self._json(404, {"ok": False, "error": "unknown path %s" % path})

    def _do_sync(self):
        try:
            res = sync_mod.sync()
            self._json(200, res)
            log("sync ok: global=%s TEU, COSCO=%s TEU, order%%=%s"
                % (res["global"]["active_teu"], res["cosco"]["total_teu"], res["cosco"]["order_pct"]))
        except Exception as e:  # 明确回传错误，方便按钮上提示
            err = "%s: %s" % (type(e).__name__, e)
            self._json(500, {"ok": False, "error": err, "trace": traceback.format_exc()[-800:]})
            log("sync FAILED: " + err)

    def log_message(self, fmt, *args):
        log("%s - %s" % (self.address_string(), fmt % args))


def log(msg):
    print("[%s] %s" % (__import__("datetime").datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def main():
    if not os.path.exists(sync_mod.XLSX):
        print("警告：找不到数据源 %s" % sync_mod.XLSX)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print("Alphaliner 同步服务已启动： http://%s:%d" % (HOST, PORT))
    print("  · 健康检查 GET  /health")
    print("  · 执行同步 GET|POST /sync")
    print("  · 目标文件 %s" % sync_mod.XLSX)
    print("按 Ctrl+C 停止。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
