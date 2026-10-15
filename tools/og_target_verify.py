# -*- coding: utf-8 -*-
"""验证 TargetPage 画布编辑器：不白屏、按钮在、新增链路通（验证后删测试料位）。"""
import os, sys, time

SKILL = r"C:\Users\21449\.workbuddy\skills\local-webapp-headless-verify\scripts"
sys.path.insert(0, SKILL)
from cdp_ws import CDP, start_servers, stop_all, wait_http, http  # noqa: E402

ROOT = r"C:\Users\21449\Desktop\optical-guidance"
VENV_PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
NODE = r"C:\Users\21449\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
BACKEND = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend")


def main():
    handles = start_servers(
        [VENV_PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8002"],
        BACKEND,
        [NODE, "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "5174"],
        FRONTEND,
    )
    ok_be = wait_http("127.0.0.1", 8002, "/health", timeout=50)
    ok_fe = wait_http("127.0.0.1", 5174, "/", head_only=True, timeout=40)
    if not (ok_be and ok_fe):
        stop_all(handles)
        print("FAIL: 服务未就绪")
        return 1

    # 记录初始料位数（按 orderIndex）
    _, before = http("GET", "/api/targets/")
    before_ids = [t["id"] for t in before]

    report = {}
    with CDP(port=9337) as c:
        c.goto("http://127.0.0.1:5174/targets",
               wait_expr="document.querySelectorAll('.ant-btn').length>0", settle=1.5)
        report["content_len"] = c.content_len(".ant-layout-content")
        report["has_circle_btn"] = c.js(
            "(()=>[...document.querySelectorAll('.ant-btn')].some(b=>(b.innerText||'').replace(/\\s+/g,'').includes('圆形')))()")
        report["has_rect_btn"] = c.js(
            "(()=>[...document.querySelectorAll('.ant-btn')].some(b=>(b.innerText||'').replace(/\\s+/g,'').includes('矩形')))()")
        report["shape_count_before"] = c.js(
            "document.querySelectorAll('[style*=\"cursor: move\"]').length")
        # 点击「圆形」新增
        c.click_text(".ant-btn", "圆形")
        time.sleep(1.2)
        report["shape_count_after"] = c.js(
            "document.querySelectorAll('[style*=\"cursor: move\"]').length")
        report["errors"] = c.errors()

    # 后端确认新增 + 删除测试料位
    _, after = http("GET", "/api/targets/")
    after_ids = [t["id"] for t in after]
    new_ids = [i for i in after_ids if i not in before_ids]
    report["new_targets"] = len(new_ids)
    for nid in new_ids:
        http("DELETE", f"/api/targets/{nid}")

    stop_all(handles)

    print(report)
    ok = (
        report["content_len"] > 0
        and report["has_circle_btn"] is True
        and report["has_rect_btn"] is True
        and report["shape_count_before"] == len(before_ids)
        and report["new_targets"] == 1
        and report["shape_count_after"] >= report["shape_count_before"] + 1
        and not report["errors"]
    )
    print("TARGET CANVAS VERIFY", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
