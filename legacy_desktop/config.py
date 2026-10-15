# -*- coding: utf-8 -*-
"""光学引导系统 · 全局配置与显示器探测。

设计原则：物理位置可能变动，所以投影仪/摄像头的“屏幕位置”不要写死，
启动时自动探测副屏（投影仪）位置。
"""
import ctypes
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(exist_ok=True)
CALIB_PATH = STATE_DIR / "calib.json"

# 投影仪输出分辨率（作为“投影坐标系”的基准，料盒都定义在这个坐标系里）
PROJ_W, PROJ_H = 1024, 768

# 摄像头（分辨率会依次尝试下面的候选，取第一个能出帧的）
# 注：MediaPipe 内部会降采样，输入分辨率对推理耗时影响很小（1920x1080 约 16ms/帧），
#     这里选 1280x720 兼顾标定角点精度与预览流畅度。
CAM_INDEX = 0
CAM_W, CAM_H = 1280, 720
CAM_FALLBACK = [(1280, 720), (1920, 1080), (640, 480)]

# 手进入料盒后的停留判定（秒），抑制抖动
HAND_DWELL_SEC = 0.12

# 标定：投影黑/白两帧的等待与采样
CALIB_SETTLE_SEC = 0.35
CALIB_SAMPLES = 5


def list_monitors():
    """返回 [(left, top, right, bottom), ...]，按系统枚举顺序。"""
    monitors = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    proc_type = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.POINTER(RECT), ctypes.c_double)

    def _cb(hmon, hdc, lprc, data):
        r = lprc.contents
        monitors.append((r.left, r.top, r.right, r.bottom))
        return 1

    ctypes.windll.user32.EnumDisplayMonitors(0, 0, proc_type(_cb), 0)
    return monitors


def get_projector_rect():
    """返回投影仪窗口的 (x, y, w, h)。

    优先取“非主屏”的那块；若只有一块屏，则退回默认配置。
    """
    mons = list_monitors()
    if not mons:
        return (1920, 0, PROJ_W, PROJ_H)
    primary_idx = 0
    for i, (l, t, r, b) in enumerate(mons):
        if l <= 0 < r and t <= 0 < b:
            primary_idx = i
            break
    others = [m for i, m in enumerate(mons) if i != primary_idx]
    if not others:
        return (mons[0][0], mons[0][1], mons[0][2] - mons[0][0], mons[0][3] - mons[0][1])
    l, t, r, b = others[0]
    return (l, t, r - l, b - t)


def projector_geometry():
    x, y, w, h = get_projector_rect()
    return f"{w}x{h}+{x}+{y}", (w, h)
