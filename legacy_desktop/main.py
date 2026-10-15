# -*- coding: utf-8 -*-
"""光学引导系统 · 主程序。

流程：打开画面 -> 启动标定（投影黑白差求单应矩阵）-> 进入引导循环
      手部检测(摄像头) -> 换算到投影坐标 -> 引导引擎判定 -> 投影仪投红/绿光

按键：r = 重新标定   1/2/3 = 手动跳步   n = 下一步   ESC = 退出
运行：.venv\\Scripts\\python.exe main.py
"""
import ctypes

# 多显示器坐标必须先用物理像素（必须在 import tkinter 之前）
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import os
import time
import tkinter as tk

import cv2
import numpy as np
from PIL import Image, ImageTk

import config
import calibrate as calib_mod
from detector import MediaPipeHandDetector, NullHandDetector
from engine import GuidanceEngine
from layout import default_boxes
from process import default_process
from projector import ProjectorWindow

PREVIEW_W = 900


def open_camera():
    """打开摄像头并确定一个“真的能出帧”的分辨率。

    逐个索引、逐个候选分辨率尝试；只有真正 read() 成功才认账。
    避免出现“句柄打开成功但永远读不到帧”的黑屏。
    """
    for idx in range(4):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            continue
        for (w, h) in config.CAM_FALLBACK:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            ok = False
            for _ in range(8):          # 部分摄像头切换分辨率后前几帧是空帧
                ok, frame = cap.read()
                if ok and frame is not None:
                    break
            if ok:
                real_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                real_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                print(f"[cam] index={idx} requested={w}x{h} actual={real_w}x{real_h} shape={frame.shape}")
                return cap, idx
        cap.release()
    return None, None


def cam_to_proj(pt, Hinv):
    p = np.array([[pt]], dtype=np.float32)
    q = cv2.perspectiveTransform(p, np.asarray(Hinv, dtype=np.float64))
    return float(q[0][0][0]), float(q[0][0][1])


def proj_to_cam(pt, H):
    p = np.array([[pt]], dtype=np.float32)
    q = cv2.perspectiveTransform(p, np.asarray(H, dtype=np.float64))
    return int(q[0][0][0]), int(q[0][0][1])


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("光学引导系统 · 控制台")
        self.root.geometry("460x150+40+40")

        geom, size = config.projector_geometry()
        self.proj = ProjectorWindow(self.root, geom, size)

        self.status = tk.Label(self.root, text="初始化…", anchor="w",
                               justify="left", font=("Microsoft YaHei", 11))
        self.status.pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(self.root, text="r 重新标定 ｜ n 下一步 ｜ ESC 退出",
                 anchor="w", font=("Microsoft YaHei", 10)).pack(fill="x", padx=12)

        # 主屏调试预览
        self.prev_win = tk.Toplevel(self.root)
        self.prev_win.title("Camera · 调试预览")
        self.prev_win.geometry(f"{PREVIEW_W + 20}x{PREVIEW_W + 140}+40+190")
        self.prev_win.configure(bg="#0b0b0b")
        self.prev_win.attributes("-topmost", True)
        self.big = tk.Label(self.prev_win, text="", fg="#facc15", bg="#0b0b0b",
                            font=("Consolas", 16, "bold"))
        self.big.pack(fill="x", pady=(4, 2))
        self.prev_label = tk.Label(self.prev_win, bg="#0b0b0b")
        self.prev_label.pack(fill="both", expand=True)

        self.cap, self.cam_idx = open_camera()
        try:
            self.det = MediaPipeHandDetector()
            self.det_name = "MediaPipe"
        except Exception as e:
            self.det = NullHandDetector()
            self.det_name = f"无检测器({e})"

        self.boxes = default_boxes()
        self.engine = GuidanceEngine(self.boxes, default_process(),
                                     dwell=config.HAND_DWELL_SEC)
        self.H = None
        self.Hinv = None
        self.cur_colors = {}
        self.cur_hand_proj = None
        self.last_event = ""

        self.root.bind_all("<Key>", self.on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.root.after(200, self.run_calibration)
        self.root.mainloop()

    # ---------- 标定 ----------
    def run_calibration(self):
        if self.cap is None:
            self.status.config(text="[!] 摄像头打不开")
            return
        self.status.config(text="标定中：投影全黑/全白对比，请保持画面稳定…")
        self.proj.solid("black")
        self.root.update()
        time.sleep(0.2)
        dbg = str(config.STATE_DIR / "calib_debug.jpg")
        res = calib_mod.calibrate(self.cap, self.proj, self.root, debug_save=dbg)
        if res.get("ok"):
            self.H = res["homography"]
            self.Hinv = res["homography_inv"]
            calib_mod.save_calib(res)
            self.status.config(
                text=f"标定完成 ✓  投影区面积={res['area']:.0f}px²  (结果存 state/calib.json)")
        else:
            self.H = self.Hinv = None
            self.status.config(text=f"标定失败：{res.get('reason')}  按 r 重试")
        self.loop()

    # ---------- 主循环 ----------
    def loop(self):
        if self.cap is None:
            self.root.after(50, self.loop)
            return
        ok, frame = self.cap.read()
        if ok:
            hh, ww = frame.shape[:2]
            hand_cam = self.det.detect(frame)
            hand_proj = None
            if hand_cam is not None and self.Hinv is not None:
                hand_proj = cam_to_proj(hand_cam, self.Hinv)

            colors, hand_box, event = self.engine.update(hand_proj)
            self.cur_colors = colors
            self.cur_hand_proj = hand_proj
            if event:
                self.last_event = f"{event[0]} @ {event[1]}"

            # 投影画面
            step = self.engine.step_index
            tgt = self.engine.target_box_id
            txt = f"第 {step + 1}/{len(self.engine.process.steps)} 步：{self.engine.process.step_name(step)}"
            flash = "green" if (event and event[0] in ("ok", "advance")) else \
                    ("red" if (event and event[0] == "wrong") else None)
            self.proj.draw(self.boxes, colors, step_text=txt,
                           hand_proj=hand_proj, flash=flash)

            # 调试预览叠加
            vis = frame.copy()
            if hand_cam is not None:
                cv2.circle(vis, (int(hand_cam[0]), int(hand_cam[1])), 14, (0, 255, 255), 3)
            if self.H is not None:
                for b in self.boxes:
                    cx, cy = proj_to_cam((b.cx, b.cy), self.H)
                    cv2.circle(vis, (cx, cy), 6, (0, 200, 255), -1)
                cv2.polylines(vis, [np.int32([
                    proj_to_cam((0, 0), self.H), proj_to_cam((config.PROJ_W - 1, 0), self.H),
                    proj_to_cam((config.PROJ_W - 1, config.PROJ_H - 1), self.H),
                    proj_to_cam((0, config.PROJ_H - 1), self.H)])], True, (0, 255, 0), 3)

            rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            ph = int(PREVIEW_W * hh / ww)
            img = img.resize((PREVIEW_W, ph))
            tkimg = ImageTk.PhotoImage(img)
            self.prev_label.configure(image=tkimg)
            self.prev_label.image = tkimg

            self.big.config(text=f"手: {'有' if hand_cam else '无'}  "
                                 f"目标: {tgt}  事件: {self.last_event}")
        self.root.after(30, self.loop)

    # ---------- 交互 ----------
    def on_key(self, e):
        k = e.keysym.lower()
        if k == "escape":
            self.on_close()
        elif k == "r":
            self.root.after(10, self.run_calibration)
        elif k == "n":
            self.engine.advance()

    def on_close(self):
        try:
            if self.cap is not None:
                self.cap.release()
            self.det.close()
        finally:
            self.root.destroy()


if __name__ == "__main__":
    App()
