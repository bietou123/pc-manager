"""电脑管家主入口：Flask 提供 API，pywebview 承载界面。"""

import io
import os
import socket
import sys
import threading

from flask import Flask, jsonify, request, send_from_directory

from core import cleaner, monitor, startup, sysinfo

# 打包成 --windowed 后没有控制台，标准输出会变成 None，print 会直接抛异常
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()


def resource_path(relative):
    """定位静态资源：打包后在 _MEIPASS，开发时在项目目录。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


WEB_DIR = resource_path("web")

app = Flask(__name__, static_folder=None)
app.json.ensure_ascii = False


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(WEB_DIR, filename)


@app.route("/api/system")
def api_system():
    return jsonify(sysinfo.get_system_info())


@app.route("/api/monitor")
def api_monitor():
    limit = request.args.get("limit", default=12, type=int)
    return jsonify(monitor.get_stats(limit))


@app.route("/api/clean/targets")
def api_clean_targets():
    return jsonify(cleaner.list_targets())


@app.route("/api/clean/scan", methods=["POST"])
def api_clean_scan():
    payload = request.get_json(silent=True) or {}
    return jsonify(cleaner.scan(payload.get("keys")))


@app.route("/api/clean/run", methods=["POST"])
def api_clean_run():
    payload = request.get_json(silent=True) or {}
    return jsonify(cleaner.clean(payload.get("keys", [])))


@app.route("/api/startup")
def api_startup():
    return jsonify(startup.list_startup())


@app.route("/api/startup/disable", methods=["POST"])
def api_startup_disable():
    payload = request.get_json(silent=True) or {}
    return jsonify(startup.disable(payload.get("id", "")))


@app.route("/api/startup/enable", methods=["POST"])
def api_startup_enable():
    payload = request.get_json(silent=True) or {}
    return jsonify(startup.enable(payload.get("id", "")))


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(port):
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False, use_reloader=False)


def main():
    port = _free_port()
    server = threading.Thread(target=_serve, args=(port,), daemon=True)
    server.start()

    url = f"http://127.0.0.1:{port}"
    print(f"[info] 服务已启动：{url}")

    try:
        import webview

        webview.create_window(
            "电脑管家",
            url,
            width=1200,
            height=780,
            min_size=(980, 640),
            background_color="#0f1115",
        )
        webview.start()
    except Exception as exc:
        # 没有可用的 WebView 时退回浏览器，功能不受影响
        print(f"[warn] 无法启动内嵌窗口（{exc}），改用浏览器打开")
        import webbrowser

        webbrowser.open(url)
        server.join()


if __name__ == "__main__":
    main()
