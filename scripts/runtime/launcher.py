#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
光学引导系统 · 一键启动 / 停止（纯 Python 实现）

为什么不再用 PowerShell 编排进程：
    Windows PowerShell 5.1 在环境里同时存在 Path / PATH 两个大小写不同的键时，
    Start-Process 带 -RedirectStandardOutput / -RedirectStandardError 会抛
        "已添加项。字典中的关键字:"Path"所添加的关键字:"PATH""
    直接导致后台服务起不来（实测归一化 $env:PATH 也无效）。
    这里改用 Python subprocess 直接派生进程：日志落盘、PID 记录到
    optical-guidance-data/run-state.json，全部可控，且不依赖 PS 的编码 / 执行策略。

用法（正常由「启动光学引导系统.bat」调用）：
    python scripts/runtime/launcher.py start
    python scripts/runtime/launcher.py stop
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------
# 路径与常量
# --------------------------------------------------------------------------
HOST = "127.0.0.1"
BACKEND_PORT = 8002
FRONTEND_PORT = 5174

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND_DIR = os.path.join(ROOT, "backend")
FRONTEND_DIR = os.path.join(ROOT, "frontend")
VENV_DIR = os.path.join(ROOT, ".venv")
VENV_PY = os.path.join(VENV_DIR, "Scripts", "python.exe")
DATA_DIR = os.path.join(ROOT, "optical-guidance-data")
STATE_FILE = os.path.join(DATA_DIR, "run-state.json")
PROJECTOR_PROFILE = os.path.join(ROOT, ".projector-profile")

REQ_FILE = os.path.join(BACKEND_DIR, "requirements.txt")
STAMP_FILE = os.path.join(VENV_DIR, ".requirements.stamp")
NODE_MODULES = os.path.join(FRONTEND_DIR, "node_modules")
VITE_JS = os.path.join(NODE_MODULES, "vite", "bin", "vite.js")

PIP_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
NPM_REGISTRY = "https://registry.npmmirror.com"

# Windows 进程创建标志
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

# --------------------------------------------------------------------------
# 控制台输出
# --------------------------------------------------------------------------
if not sys.stdout.isatty():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _enable_ansi() -> None:
    try:
        k = ctypes.windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)
    except Exception:
        pass


def step(msg: str) -> None:
    print("\033[36m==> %s\033[0m" % msg, flush=True)


def ok(msg: str) -> None:
    print("    \033[32m%s\033[0m" % msg, flush=True)


def warn(msg: str) -> None:
    print("    \033[33m%s\033[0m" % msg, flush=True)


def err(msg: str) -> None:
    print("\033[31m%s\033[0m" % msg, flush=True)


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------
def _taskkill(pid: int) -> None:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass


def listening_pids(port: int) -> set:
    """返回正在 LISTEN 指定端口的 PID 集合（解析 netstat -ano）。"""
    pids = set()
    try:
        cp = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, timeout=25,
        )
    except Exception:
        return pids
    text = None
    for enc in ("oem", "utf-8", "gbk", "latin-1"):
        try:
            text = cp.stdout.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        return pids
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        if parts[0].upper() != "TCP":
            continue
        if parts[3].upper() != "LISTENING":
            continue
        if parts[1].rsplit(":", 1)[-1] == str(port):
            try:
                pids.add(int(parts[4]))
            except ValueError:
                pass
    return pids


def free_port(port: int) -> None:
    for pid in listening_pids(port):
        warn("端口 %d 被 PID %d 占用，正在结束" % (port, pid))
        _taskkill(pid)


def wait_http(url: str, timeout: int = 90) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if 200 <= r.status < 500:
                    return True
        except Exception:
            pass
        time.sleep(0.6)
    return False


def spawn(cmd, cwd: str, out_path: str, err_path: str):
    """派生一个脱离当前控制台的子进程，stdout/stderr 追加写入日志文件。"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out = open(out_path, "ab", buffering=0)
    err = open(err_path, "ab", buffering=0)
    base_flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    last_exc = None
    try:
        for extra in (CREATE_BREAKAWAY_FROM_JOB, 0):
            try:
                # 作业对象不允许 breakaway 时（WinError 5），退化为普通派生
                return subprocess.Popen(
                    cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                    stdout=out, stderr=err,
                    creationflags=base_flags | extra, close_fds=True,
                )
            except OSError as exc:
                last_exc = exc
        raise last_exc
    finally:
        out.close()
        err.close()


def find_node():
    p = shutil.which("node")
    if p:
        return p
    for c in (r"C:\Program Files\nodejs\node.exe",
              r"C:\Program Files (x86)\nodejs\node.exe"):
        if os.path.exists(c):
            return c
    return None


def find_npm():
    p = shutil.which("npm")
    if p:
        return p
    for c in (r"C:\Program Files\nodejs\npm.cmd",
              r"C:\Program Files (x86)\nodejs\npm.cmd"):
        if os.path.exists(c):
            return c
    return None


def find_browser():
    for p in (
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     r"Google\Chrome\Application\chrome.exe"),
    ):
        if os.path.exists(p):
            return p
    return None


# --------------------------------------------------------------------------
# 多显示器探测
# --------------------------------------------------------------------------
class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]


def get_monitors():
    """返回 [{left, top, width, height, primary}]，坐标已做 DPI 感知。"""
    user32 = ctypes.windll.user32

    # 先争取 Per-Monitor V2，拿不到再退到 System DPI Aware
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(RECT), ctypes.c_void_p,
    )
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = ctypes.c_bool
    user32.EnumDisplayMonitors.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, MONITORENUMPROC, ctypes.c_void_p,
    ]
    user32.EnumDisplayMonitors.restype = ctypes.c_bool

    monitors = []

    def _cb(hmon, hdc, lprc, data):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r = mi.rcMonitor
            monitors.append({
                "left": r.left, "top": r.top,
                "width": r.right - r.left, "height": r.bottom - r.top,
                "primary": bool(mi.dwFlags & 1),
            })
        return 1

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), None)
    return monitors


# --------------------------------------------------------------------------
# 环境准备
# --------------------------------------------------------------------------
def ensure_venv() -> str:
    step("检查虚拟环境（本项目独立）")
    if os.path.exists(VENV_PY):
        ok("复用已有虚拟环境 %s" % VENV_DIR)
        return VENV_PY
    base = sys.executable
    if not base:
        raise SystemExit("找不到可用的 Python 解释器，无法创建虚拟环境")
    ok("创建独立虚拟环境 %s" % VENV_DIR)
    r = subprocess.run([base, "-m", "venv", VENV_DIR])
    if r.returncode != 0 or not os.path.exists(VENV_PY):
        raise SystemExit("创建虚拟环境失败")
    return VENV_PY


def ensure_python_deps(py: str) -> None:
    if (os.path.exists(STAMP_FILE) and os.path.exists(REQ_FILE)
            and os.path.getmtime(STAMP_FILE) >= os.path.getmtime(REQ_FILE)):
        ok("后端依赖已就绪")
        return
    step("安装后端依赖（清华镜像）")
    r = subprocess.run([py, "-m", "pip", "install", "-i", PIP_INDEX, "-r", REQ_FILE])
    if r.returncode != 0:
        raise SystemExit("后端依赖安装失败")
    open(STAMP_FILE, "w").close()


def ensure_frontend_deps() -> None:
    if os.path.isdir(NODE_MODULES):
        ok("前端依赖已就绪")
        return
    npm = find_npm()
    if not npm:
        raise SystemExit("找不到 npm，请先安装 Node.js 20.19+ / 22.12+")
    step("安装前端依赖（npmmirror）")
    r = subprocess.run([npm, "install", "--registry=" + NPM_REGISTRY],
                       cwd=FRONTEND_DIR, shell=True)
    if r.returncode != 0:
        raise SystemExit("前端依赖安装失败")


# --------------------------------------------------------------------------
# start
# --------------------------------------------------------------------------
def start() -> int:
    _enable_ansi()
    print()
    step("光学引导系统 · 启动")
    os.makedirs(DATA_DIR, exist_ok=True)

    py = ensure_venv()
    ensure_python_deps(py)
    ensure_frontend_deps()

    node = find_node()
    if not node:
        raise SystemExit("找不到 node，请先安装 Node.js 20.19+ / 22.12+")
    if not os.path.exists(VITE_JS):
        raise SystemExit("找不到 vite（%s），请先在 frontend 里 npm install" % VITE_JS)

    step("清理端口 %d / %d" % (BACKEND_PORT, FRONTEND_PORT))
    free_port(BACKEND_PORT)
    free_port(FRONTEND_PORT)
    time.sleep(0.4)

    state = {"started_at": time.time()}

    step("启动后端")
    be = spawn(
        [py, "-m", "uvicorn", "app.main:app",
         "--host", HOST, "--port", str(BACKEND_PORT)],
        BACKEND_DIR,
        os.path.join(BACKEND_DIR, "backend.out.log"),
        os.path.join(BACKEND_DIR, "backend.err.log"),
    )
    state["backend_pid"] = be.pid

    step("启动前端")
    fe = spawn(
        [node, VITE_JS, "--host", HOST, "--port", str(FRONTEND_PORT), "--strictPort"],
        FRONTEND_DIR,
        os.path.join(FRONTEND_DIR, "frontend.out.log"),
        os.path.join(FRONTEND_DIR, "frontend.err.log"),
    )
    state["frontend_pid"] = fe.pid

    step("等待服务就绪")
    backend_ok = wait_http("http://%s:%d/health" % (HOST, BACKEND_PORT), 90)
    frontend_ok = wait_http("http://%s:%d/" % (HOST, FRONTEND_PORT), 90)
    if backend_ok:
        ok("后端就绪   http://%s:%d/docs" % (HOST, BACKEND_PORT))
    else:
        warn("后端未就绪，请查看 backend\\backend.err.log")
    if frontend_ok:
        ok("前端就绪   http://%s:%d" % (HOST, FRONTEND_PORT))
    else:
        warn("前端未就绪，请查看 frontend\\frontend.err.log")

    # 注意：venv 里的 python.exe 只是个存根，会再派生真正的解释器进程，
    # 所以 Popen 拿到的 PID 不一定是真正在监听端口的那一个。这里补记真实监听 PID。
    for port, key in ((BACKEND_PORT, "backend_listen_pid"),
                      (FRONTEND_PORT, "frontend_listen_pid")):
        listeners = sorted(listening_pids(port))
        if listeners:
            state[key] = listeners[0]

    # ---------- 副屏投影 + 控制台 ----------
    browser = find_browser()
    monitors = get_monitors()
    secondary = next((m for m in monitors if not m["primary"]), None)

    proj_url = "http://%s:%d/projector" % (HOST, FRONTEND_PORT)
    console_url = "http://%s:%d/monitoring" % (HOST, FRONTEND_PORT)

    if browser and secondary:
        b = secondary
        step("在副屏打开投影页（%dx%d @ %d,%d）"
             % (b["width"], b["height"], b["left"], b["top"]))
        # 必须关掉「被遮挡窗口的节流」，否则投影窗口被判为不可见 ->
        # 定时器降到 1 次/秒、绘制层被丢弃，表现为投影出来一片白。
        args = [
            "--app=" + proj_url,
            "--window-position=%d,%d" % (b["left"], b["top"]),
            "--window-size=%d,%d" % (b["width"], b["height"]),
            "--start-fullscreen",
            "--user-data-dir=" + PROJECTOR_PROFILE,
            "--no-first-run", "--no-default-browser-check", "--disable-sync",
            "--disable-features=msEdgeFirstRunExperience,msImplicitSignin,"
            "CalculateNativeWinOcclusion",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
        ]
        try:
            bp = subprocess.Popen([browser] + args,
                                  creationflags=DETACHED_PROCESS
                                  | CREATE_NEW_PROCESS_GROUP,
                                  close_fds=True)
            state["projector_browser_pid"] = bp.pid
        except OSError as exc:
            warn("投影页浏览器启动失败：%s" % exc)
    else:
        warn("没找到副屏或浏览器，投影页请手动打开（拖到投影屏后按 F11 全屏）：")
        warn("  " + proj_url)

    step("打开控制台")
    try:
        if browser:
            subprocess.Popen([browser, "--new-window", console_url])
        else:
            os.startfile(console_url)      # noqa: S606
    except Exception as exc:
        warn("控制台页打开失败：%s" % exc)

    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass

    print()
    print("\033[32m光学引导系统已启动：\033[0m")
    print("  控制台   http://%s:%d/monitoring" % (HOST, FRONTEND_PORT))
    print("  投影页   %s" % proj_url)
    print("  接口文档 http://%s:%d/docs" % (HOST, BACKEND_PORT))
    print("\033[33m停止请双击「关闭光学引导系统.bat」\033[0m")
    return 0 if (backend_ok and frontend_ok) else 1


# --------------------------------------------------------------------------
# stop
# --------------------------------------------------------------------------
def stop() -> int:
    _enable_ansi()
    print()
    step("光学引导系统 · 停止")

    pids = []
    seen = set()
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as fh:
                st = json.load(fh)
            for key in ("projector_browser_pid", "frontend_pid", "backend_pid",
                        "frontend_listen_pid", "backend_listen_pid"):
                val = st.get(key)
                if isinstance(val, int) and val > 0 and val not in seen:
                    seen.add(val)
                    pids.append((key, val))
        except Exception:
            pass

    for key, pid in pids:
        warn("结束 %s (PID %d)" % (key, pid))
        _taskkill(pid)

    for port in (BACKEND_PORT, FRONTEND_PORT):
        for pid in listening_pids(port):
            warn("结束端口 %d 上的残留进程 PID %d" % (port, pid))
            _taskkill(pid)

    try:
        os.remove(STATE_FILE)
    except Exception:
        pass

    time.sleep(0.6)
    left = [p for p in (BACKEND_PORT, FRONTEND_PORT) if listening_pids(p)]
    if not left:
        print("\033[32m光学引导系统已停止。\033[0m")
        return 0
    print("\033[33m以下端口仍被占用：%s\033[0m" % ", ".join(str(p) for p in left))
    return 1


# --------------------------------------------------------------------------
def main(argv) -> int:
    if len(argv) < 2 or argv[1] not in ("start", "stop"):
        print("用法：python scripts/runtime/launcher.py {start|stop}")
        return 2
    try:
        return start() if argv[1] == "start" else stop()
    except SystemExit as exc:
        err(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
