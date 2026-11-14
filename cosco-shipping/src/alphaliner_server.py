# -*- coding: utf-8 -*-
"""Alphaliner 同步本地服务 —— 供 alphaliner-weekly.html 的「同步」按钮调用。

定位：本服务是「Alphaliner 周六快照采集」自动化的**手动等价入口**，
用于自动逻辑漏执行时补跑，流水线与自动化完全一致：
    ① 抓取 PublicTop100 → 写 xlsx 的「全球」「COSCO」两张表 + 重算「分析要点」
    ② 只重建 alphaliner-weekly.html（--only alphaliner，不碰 Drewry / SSE 页面）
    ③ openpyxl 只读三项校验
浏览器无法直接写本地 Excel，故由本服务落盘；服务只监听 127.0.0.1。

启动：
    cd cosco-shipping
    python src/alphaliner_server.py                    # 默认 127.0.0.1:8765

接口：
    GET  /health  → {"ok": true, "service": "alphaliner-sync", ...}
    GET|POST /sync → 执行上述三步，返回 JSON（含 render / checks / stages）
说明：跨域放开，便于 file:// 或线上副本调用本机服务；但线上副本 reload 后
      仍是云端旧 HTML，需推送部署后才生效。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alphaliner_sync as sync_mod  # noqa: E402
import build_weekly_pages as pages  # noqa: E402

HOST = "127.0.0.1"
PORT = int(os.environ.get("ALPHALINER_PORT", "8765"))
_SYNC_LOCK = threading.Lock()       # 串行化，防止连点并发写同一个 xlsx


class PipelineError(RuntimeError):
    """流水线某一阶段失败；partial 记录此前已完成的副作用，供前端如实提示。"""

    def __init__(self, stage, message, partial=None):
        super().__init__(message)
        self.stage = stage
        self.partial = partial or {}


def run_pipeline() -> dict:
    """= 周六自动化的完整三步；返回结构与 sync() 兼容，额外带 render/checks。"""
    t0 = time.time()
    partial, stages = {}, {}
    with _SYNC_LOCK:
        # 阶段 0：写前预检（锁文件 / 文件存在）
        t = time.time()
        try:
            sync_mod.check_lock()
        except Exception as e:
            raise PipelineError("precheck", str(e), partial)
        stages["precheck_ms"] = int((time.time() - t) * 1000)

        # 阶段 1：抓取 + 写 xlsx（sync 内部还会再做一次锁检测）
        t = time.time()
        try:
            res = sync_mod.sync()
        except Exception as e:
            raise PipelineError("fetch_write", "%s: %s" % (type(e).__name__, e), partial)
        stages["fetch_write_ms"] = int((time.time() - t) * 1000)
        partial.update({"written": True, "publish_date": res.get("publish_date"),
                        "backup": res.get("backup")})

        # 阶段 2：只重建 Alphaliner 页 —— 绝不能无参调用（那会全量重建三页）
        t = time.time()
        try:
            rendered = pages.main(["--only", "alphaliner"]) or []
            if len(rendered) != 1 or rendered[0]["page"] != "alphaliner":
                raise RuntimeError("渲染范围异常：%r" % [r["page"] for r in rendered])
            names = [os.path.basename(r["path"]) for r in rendered]
        except Exception as e:
            raise PipelineError("render", "%s: %s" % (type(e).__name__, e), partial)
        stages["render_ms"] = int((time.time() - t) * 1000)
        render = {"pages": names, "periods": rendered[0]["periods"],
                  "bytes": rendered[0]["bytes"]}
        partial["rendered"] = names

        # 阶段 3：三项校验（只读，共用于 CLI 与按钮）
        t = time.time()
        try:
            checks = sync_mod.verify(expected_date=res["publish_date"])
        except Exception as e:
            raise PipelineError("verify", "%s: %s" % (type(e).__name__, e), partial)
        stages["verify_ms"] = int((time.time() - t) * 1000)

        return {**res, "render": render, "checks": checks,
                "stages": stages, "elapsed_ms": int((time.time() - t0) * 1000)}


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
                             "xlsx": sync_mod.AL_XLSX,
                             "pipeline": ["fetch_write", "render(--only alphaliner)", "verify"]})
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
            res = run_pipeline()
            ck = res.get("checks") or {}
            self._json(200, res)
            log("sync ok: %s · global=%s TEU, COSCO=%s TEU, order%%=%s · checks=%s"
                % (res["publish_date"], res["global"]["active_teu"],
                   res["cosco"]["total_teu"], res["cosco"]["order_pct"],
                   "3/3" if ck.get("all_passed") else "FAILED"))
        except PipelineError as e:
            # 分阶段错误：带上此前已完成的副作用，避免用户误判「数据没写」
            self._json(500, {"ok": False, "stage": e.stage, "error": str(e),
                             "partial": e.partial, "trace": traceback.format_exc()[-800:]})
            log("sync FAILED at %s: %s" % (e.stage, e))
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, e)
            self._json(500, {"ok": False, "stage": "unknown", "error": err,
                             "partial": {}, "trace": traceback.format_exc()[-800:]})
            log("sync FAILED: " + err)

    def log_message(self, fmt, *args):
        log("%s - %s" % (self.address_string(), fmt % args))


def log(msg):
    print("[%s] %s" % (__import__("datetime").datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def main():
    if not os.path.exists(sync_mod.AL_XLSX):
        print("警告：找不到数据源 %s" % sync_mod.AL_XLSX)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print("Alphaliner 同步服务已启动： http://%s:%d" % (HOST, PORT))
    print("  · 健康检查 GET  /health")
    print("  · 完整流水线 GET|POST /sync（抓取 → 只重建 Alphaliner 页 → 三项校验）")
    print("  · 目标文件 %s" % sync_mod.AL_XLSX)
    print("按 Ctrl+C 停止。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
