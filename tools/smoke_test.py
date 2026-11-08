"""后端冒烟测试：不启动窗口，直接打各接口，并检查 WebView 环境。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app


def check_static():
    client = app.test_client()
    failed = 0
    for path in ("/", "/style.css", "/app.js"):
        resp = client.get(path)
        ok = resp.status_code == 200 and len(resp.data) > 200
        print(f"[{'ok' if ok else 'FAIL'}] GET {path} -> {resp.status_code} ({len(resp.data)} 字节)")
        if not ok:
            failed += 1
    return failed


def check_api():
    client = app.test_client()
    checks = [
        ("GET", "/api/system", None),
        ("GET", "/api/clean/targets", None),
        ("GET", "/api/startup", None),
        ("GET", "/api/monitor", None),
        ("POST", "/api/clean/scan", {}),
    ]
    failed = 0
    for method, path, body in checks:
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, json=body)
        ok = resp.status_code == 200
        print(f"[{'ok' if ok else 'FAIL'}] {method} {path} -> {resp.status_code} ({len(resp.data)} 字节)")
        if not ok:
            failed += 1
    return failed


def check_webview():
    try:
        import webview
    except Exception as exc:
        print(f"[env] pywebview 不可用: {type(exc).__name__}: {exc}")
        return
    try:
        from importlib.metadata import version

        print(f"[env] pywebview {version('pywebview')}")
    except Exception:
        print("[env] pywebview 已安装")
    for module in ("clr", "webview.platforms.edgechromium"):
        try:
            __import__(module)
            print(f"[env] {module} 可用")
        except Exception as exc:
            print(f"[env] {module} 不可用: {type(exc).__name__}: {exc}")


def main():
    print("=== WebView 环境 ===")
    check_webview()
    print("=== 后端接口 ===")
    failed = check_api()
    print("=== 静态资源 ===")
    failed += check_static()
    print("=== 结果 ===")
    print("全部通过" if failed == 0 else f"{failed} 个接口失败")
    return failed


if __name__ == "__main__":
    sys.exit(main())
