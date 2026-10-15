# -*- coding: utf-8 -*-
"""启动标定：投影仪/摄像头位置可能每次都变，所以每次启动先做一次对齐。

原理（对台面颜色、环境光都不敏感）：
  1) 投影仪打「全黑」-> 摄像头拍一帧 dark
  2) 投影仪打「全白」-> 摄像头拍一帧 light
  3) |light - dark| 只有投影照到的地方会变亮 -> 阈值 + 最大轮廓 = 投影覆盖区
  4) 取该区域四角 -> 单应矩阵 H：投影画面坐标(1024x768) -> 摄像头画面坐标
"""
import json
import time
from typing import Optional

import cv2
import numpy as np

import config


def _grab_avg(cap, n):
    for _ in range(3):
        cap.read()
    acc = None
    cnt = 0
    for _ in range(n):
        ok, f = cap.read()
        if not ok:
            continue
        f = f.astype(np.float32)
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


def calibrate(cap, proj, root, debug_save: Optional[str] = None) -> dict:
    """执行一次标定，返回结果 dict（含 H / Hinv / 四角）。"""
    proj.solid("black")
    root.update()
    time.sleep(config.CALIB_SETTLE_SEC)
    dark = _grab_avg(cap, config.CALIB_SAMPLES)

    proj.solid("white")
    root.update()
    time.sleep(config.CALIB_SETTLE_SEC)
    light = _grab_avg(cap, config.CALIB_SAMPLES)

    proj.solid("black")
    root.update()

    result = {"ok": False, "reason": ""}
    if dark is None or light is None:
        result["reason"] = "摄像头取帧失败"
        return result

    diff = cv2.absdiff(light, dark)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 0)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kern = np.ones((15, 15), np.uint8)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kern)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kern)

    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        result["reason"] = "未检测到投影区域（对比不足？）"
        return result
    c = max(cnts, key=cv2.contourArea)
    area = cv2.contourArea(c)
    peri = cv2.arcLength(c, True)
    approx = cv2.approxPolyDP(c, 0.02 * peri, True)
    if len(approx) == 4:
        quad = approx.reshape(-1, 2)
    else:
        box = cv2.boxPoints(cv2.minAreaRect(c))
        quad = box
    quad = _order_quad(quad)

    src = np.float32([[0, 0], [config.PROJ_W - 1, 0],
                      [config.PROJ_W - 1, config.PROJ_H - 1], [0, config.PROJ_H - 1]])
    H = cv2.findHomography(src, quad)[0]
    if H is None:
        result["reason"] = "单应矩阵求解失败"
        return result
    Hinv = np.linalg.inv(H)

    if debug_save:
        vis = light.copy()
        cv2.polylines(vis, [quad.astype(np.int32)], True, (0, 255, 0), 4)
        for i, p in enumerate(quad):
            cv2.circle(vis, (int(p[0]), int(p[1])), 12, (0, 0, 255), -1)
            cv2.putText(vis, str(i), (int(p[0]) + 14, int(p[1])),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        cv2.imwrite(debug_save, vis)

    result.update({
        "ok": True,
        "quad_cam": quad.tolist(),
        "area": float(area),
        "homography": H.tolist(),
        "homography_inv": Hinv.tolist(),
    })
    return result


def save_calib(res: dict):
    data = {
        "proj_size": [config.PROJ_W, config.PROJ_H],
        "quad_cam": res["quad_cam"],
        "homography": res["homography"],
        "homography_inv": res["homography_inv"],
        "note": "H: 投影坐标 -> 摄像头坐标；Hinv: 摄像头坐标 -> 投影坐标",
    }
    config.CALIB_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_calib():
    if not config.CALIB_PATH.exists():
        return None
    return json.loads(config.CALIB_PATH.read_text(encoding="utf-8"))
