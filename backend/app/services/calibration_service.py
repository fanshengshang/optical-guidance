# -*- coding: utf-8 -*-
"""启动标定：投影仪/摄像头位置可能每次变，所以每次启动先做一次对齐。

原理（对台面颜色、环境光都不敏感）：
  1) 投影打「全黑」-> 摄像头拍 dark
  2) 投影打「全白」-> 摄像头拍 light
  3) |light - dark| 只有投影照到的地方会变亮 -> OTSU 阈值 + 最大轮廓 = 投影覆盖区
  4) 取该区域四角 -> 单应矩阵 H：投影画面坐标 -> 摄像头画面坐标
"""
import time
from typing import Optional

import cv2
import numpy as np

from .. import config
from .projector_service import projector_service


def _grab_avg(source, n: int) -> Optional[np.ndarray]:
    for _ in range(3):                      # 丢掉切换瞬间的旧帧
        source.read()
    acc, cnt = None, 0
    for _ in range(n):
        frame = source.read()
        if frame is None:
            continue
        f = frame.astype(np.float32)
        acc = f if acc is None else acc + f
        cnt += 1
    if acc is None or cnt == 0:
        return None
    return (acc / cnt).astype(np.uint8)


def _order_quad(pts) -> np.ndarray:
    pts = np.array(pts, dtype=np.float32).reshape(-1, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return np.array([tl, tr, br, bl], dtype=np.float32)


def _candidate(mask, w: int, h: int, margin: int = 3):
    """从一张掩膜里取最大轮廓，返回 (quad, area, 贴边数)。"""
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    area = float(cv2.contourArea(c))
    x, y, bw, bh = cv2.boundingRect(c)
    touching = sum([x <= margin, y <= margin,
                    x + bw >= w - margin, y + bh >= h - margin])
    peri = cv2.arcLength(c, True)
    approx = cv2.approxPolyDP(c, 0.02 * peri, True)
    quad = approx.reshape(-1, 2) if len(approx) == 4 else cv2.boxPoints(cv2.minAreaRect(c))
    return _order_quad(quad), area, touching


def _pick_quad(gray, w: int, h: int):
    """多种阈值/形态学组合里挑一个最"像个投影区"的四边形。

    优先选**不贴画面边缘**的候选——贴边说明投影范围超出了摄像头视野，
    此时的四角是假的（只是画面边界），算出来的单应矩阵不可信。
    """
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cands = []
    for k in (5, 9, 15):
        kern = np.ones((k, k), np.uint8)
        m = cv2.morphologyEx(otsu, cv2.MORPH_CLOSE, kern)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kern)
        got = _candidate(m, w, h)
        if got:
            cands.append(got)
    # 再补一个"固定余量"阈值，应对 OTSU 在近乎均匀画面上失手的情况
    peak = int(gray.max())
    if peak > 8:
        _, fixed = cv2.threshold(gray, max(6, int(peak * 0.35)), 255, cv2.THRESH_BINARY)
        fixed = cv2.morphologyEx(fixed, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        fixed = cv2.morphologyEx(fixed, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
        got = _candidate(fixed, w, h)
        if got:
            cands.append(got)

    if not cands:
        return None, "未检测到投影区域（投影没打到摄像头视野里？）"

    inside = [c for c in cands if c[2] == 0]
    pool = inside or cands
    quad, area, touching = max(pool, key=lambda c: c[1])

    warning = ""
    if touching >= 2:
        warning = ("投影覆盖区贴着摄像头画面边缘（%d 条边），说明投影范围已达到或超出"
                   "摄像头视野，四角取的是画面边界而非真实投影角点，标定结果不可信。"
                   "请把摄像头往后移或调广角，让整个投影矩形完整落在画面内。" % touching)
    elif touching == 1:
        warning = "投影覆盖区有一条边贴着画面边缘，标定结果可能略有偏差。"
    return (quad, area, warning, touching), ""


def calibrate(source, debug_abs_path: Optional[str] = None) -> dict:
    """执行一次标定。返回 {ok, ...}；失败时带 reason。"""
    if source is None or not source.is_open:
        return {"ok": False, "reason": "摄像头未就绪"}

    projector_service.set_mode("black", "标定中：投影全黑")
    time.sleep(config.CALIB_SETTLE_SEC)
    dark = _grab_avg(source, config.CALIB_SAMPLES)

    projector_service.set_mode("white", "标定中：投影全白")
    time.sleep(config.CALIB_SETTLE_SEC)
    light = _grab_avg(source, config.CALIB_SAMPLES)

    if dark is None or light is None:
        projector_service.set_mode("idle", "标定失败")
        return {"ok": False, "reason": "摄像头取帧失败（可能被别的程序占用）"}

    diff = cv2.absdiff(light, dark)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 0)

    # 先看"投影黑白切换到底有没有让画面变化"。这一步很关键：
    # 如果差分图基本全黑，说明投影光没照到摄像头视野里，后面无论找到什么形状
    # 都是噪声，必须直接判失败，否则会给出一个看似成功、实则乱来的单应矩阵。
    strength = float(gray.mean())
    peak = float(np.percentile(gray, 99.5))
    h, w = gray.shape[:2]
    if strength < 3.0 or peak < 20.0:
        projector_service.set_mode("idle", "标定失败")
        _save_debug(debug_abs_path, light, dark, diff, None)
        return {
            "ok": False,
            "reason": (f"投影黑白切换后画面几乎没有变化（差分均值 {strength:.1f}、"
                       f"99.5 分位 {peak:.0f}）。说明投影光没照到摄像头视野内："
                       "请确认投影仪正在出光并且正对着摄像头能看到的台面。"),
        }

    picked, reason = _pick_quad(gray, w, h)
    if picked is None:
        projector_service.set_mode("idle", "标定失败")
        _save_debug(debug_abs_path, light, dark, diff, None)
        return {"ok": False, "reason": reason}

    quad, area, warning, touching = picked

    # 太小的区域不认（投影基本没照到）
    if area < 0.02 * w * h:
        projector_service.set_mode("idle", "标定失败")
        _save_debug(debug_abs_path, light, dark, diff, quad)
        return {"ok": False,
                "reason": f"投影区域过小（{area:.0f}px²），请确认投影仪正在出光并对着台面"}

    # 对比太弱也不认（投影几乎没变化 -> 多半是没投到 / 环境光过强）
    if float(gray.max()) < 8:
        projector_service.set_mode("idle", "标定失败")
        _save_debug(debug_abs_path, light, dark, diff, quad)
        return {"ok": False,
                "reason": "黑白差分几乎没有变化：投影可能没照到摄像头视野，或投影仪未出光"}

    src = np.float32([[0, 0], [config.PROJ_W - 1, 0],
                      [config.PROJ_W - 1, config.PROJ_H - 1], [0, config.PROJ_H - 1]])
    H = cv2.findHomography(src, quad)[0]
    if H is None:
        projector_service.set_mode("idle", "标定失败")
        return {"ok": False, "reason": "单应矩阵求解失败"}

    Hinv = np.linalg.inv(H)
    _save_debug(debug_abs_path, light, dark, diff, quad)

    projector_service.set_mode("idle", "标定完成")
    return {
        "ok": True,
        "proj_size": [config.PROJ_W, config.PROJ_H],
        "quad_cam": quad.tolist(),
        "area": area,
        "touching_edges": int(touching),
        "warning": warning,
        "homography": H.tolist(),
        "homography_inv": Hinv.tolist(),
        "frame_shape": list(light.shape[:2]),
    }


def render_selfcheck(dark, diff, homography, quad, targets, warning: str = ""):
    """把标定结果画成一张**自检图**（PNG bytes）。

    读法（前端会把这句也写在图旁边）：
      - 亮区   = 投影光真正打到的地方（ground truth）
      - 青色框 = 标定**认为**的投影区
      - 琥珀圈 = 各料位在画面里的真实判定范围（投影 r 映射回画面）
      青框没有压在亮区上 → 标定认错了地方，绝不能拿它跑工序。

    背景 = 暗帧压暗 + 差分图提亮，这样既看得到台面，又能一眼看出光打在哪。
    """
    if dark is None or diff is None:
        return None
    try:
        h, w = dark.shape[:2]
        # 差分图做对比度归一化：投影黑白切换的信号常常很弱（几十灰度），
        # 不拉满的话"亮区"根本看不出来，这张图也就失去判定意义了。
        d = diff.astype(np.float32).max(axis=2)
        p995 = float(np.percentile(d, 99.5))
        scale = 255.0 / p995 if p995 > 1.0 else 1.0
        d = np.clip(d * scale, 0, 255)
        base = np.clip(dark.astype(np.float32) * 0.45
                       + d[..., None] * 0.85, 0, 255).astype(np.uint8)
        vis = base.copy()
        H = np.asarray(homography, dtype=np.float64)

        def _poly(pts):
            arr = np.array(pts, dtype=np.float32).reshape(1, -1, 2)
            return np.round(cv2.perspectiveTransform(arr, H)[0]).astype(np.int32)

        # 料位判定范围（琥珀）——引擎真正判定用的区域
        for i, t in enumerate(targets or []):
            if str(t.get("shape")) == "rect":
                w2 = float(t.get("w", 160)) / 2.0
                h2 = float(t.get("h", 160)) / 2.0
                pts = [(t["x"] - w2, t["y"] - h2), (t["x"] + w2, t["y"] - h2),
                       (t["x"] + w2, t["y"] + h2), (t["x"] - w2, t["y"] + h2)]
            else:
                r = float(t.get("r", 80))
                ang = np.linspace(0, 2 * np.pi, 120, endpoint=False)
                pts = [(t["x"] + r * np.cos(a), t["y"] + r * np.sin(a)) for a in ang]
            cv2.polylines(vis, [_poly(pts)], True, (0, 200, 255), 2)
            c = cv2.perspectiveTransform(
                np.array([[[float(t["x"]), float(t["y"])]]], dtype=np.float32), H)[0][0]
            cx, cy = int(round(float(c[0]))), int(round(float(c[1])))
            cv2.drawMarker(vis, (cx, cy), (255, 0, 255), cv2.MARKER_CROSS, 20, 2)
            name = str(t.get("name") or "")
            # cv2.putText 只认 ASCII，中文名回落到 T1/T2/…
            label = name if name.isascii() and name else ("T%d" % (i + 1))
            cv2.putText(vis, label, (cx + 12, cy - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

        # 标定认为的投影区（青色）
        q = np.round(np.asarray(quad, dtype=np.float64)).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(vis, [q], True, (255, 255, 0), 3)

        # 顶栏：结论
        cv2.rectangle(vis, (0, 0), (w, 42), (25, 25, 25), -1)
        cv2.putText(vis, "CALIBRATION SELF-CHECK: %s" % ("SUSPECT" if warning else "OK"),
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.85,
                    (0, 0, 255) if warning else (0, 200, 0), 2)
        cv2.putText(vis, "bright = real projection light | cyan = detected area | amber = judge range",
                    (10, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (225, 225, 225), 1)
        # 投影黑白切换的信号强度（原始值）：太小说明投影光几乎没进摄像头视野
        sig = "signal p99.5=%.0f" % p995
        (tw, _), _ = cv2.getTextSize(sig, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
        cv2.putText(vis, sig, (max(10, w - tw - 12), 64),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (180, 200, 255), 1)
        if warning:
            cv2.rectangle(vis, (0, h - 30), (w, h), (25, 25, 25), -1)
            cv2.putText(vis, "warning: calibration untrustworthy - re-align before running",
                        (10, h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 180, 255), 1)
        ok, buf = cv2.imencode(".png", vis)
        return buf.tobytes() if ok else None
    except Exception:
        return None


def _save_debug(debug_abs_path: Optional[str], light, dark, diff, quad):
    """把亮帧、暗帧、差分图和四角都存下来，方便回看排查。"""
    if not debug_abs_path:
        return
    try:
        base = str(debug_abs_path)
        stem = base[:-4] if base.lower().endswith(".jpg") else base

        vis = light.copy()
        if quad is not None:
            q = np.asarray(quad, dtype=np.int32)
            cv2.polylines(vis, [q], True, (0, 255, 0), 4)
            for i, p in enumerate(q):
                cv2.circle(vis, (int(p[0]), int(p[1])), 12, (0, 0, 255), -1)
                cv2.putText(vis, str(i), (int(p[0]) + 14, int(p[1])),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        cv2.imwrite(f"{stem}.jpg", vis)
        cv2.imwrite(f"{stem}_light.jpg", light)
        cv2.imwrite(f"{stem}_dark.jpg", dark)
        cv2.imwrite(f"{stem}_diff.jpg", diff)
    except Exception:
        pass


def detect_cameras(max_index: int = 6):
    """扫描本机可用的本地摄像头序号（打开后能读到帧才算）。"""
    found = []
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            continue
        ok, frame = cap.read()
        if ok and frame is not None:
            found.append({
                "index": idx,
                "resolution": f"{frame.shape[1]}x{frame.shape[0]}",
            })
        cap.release()
    return found
