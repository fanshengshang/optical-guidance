# -*- coding: utf-8 -*-
"""自检：依赖 + MediaPipe 手部接口 + 摄像头取帧。不弹窗，用于排查环境问题。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("python", sys.version.split()[0])

import cv2
import numpy as np
print("cv2", cv2.__version__, "| numpy", np.__version__)

import mediapipe as mp
print("mediapipe", mp.__version__)
print("has mp.solutions:", hasattr(mp, "solutions"))
if hasattr(mp, "solutions"):
    print("has solutions.hands:", hasattr(mp.solutions, "hands"))

det = None
try:
    from detector import MediaPipeHandDetector
    det = MediaPipeHandDetector()
    print("HandDetector init: OK")
except Exception as e:
    print("HandDetector init FAILED:", repr(e))

cap = None
for i in range(4):
    c = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    if c.isOpened():
        ok, f = c.read()
        if ok:
            cap = c
            print(f"camera {i}: {f.shape[1]}x{f.shape[0]}")
            if det is not None:
                print("hand detect ->", det.detect(f))
            break
        c.release()
if cap is None:
    print("camera: none of 0-3")
else:
    cap.release()
    if det is not None:
        det.close()
print("SELFCHECK DONE")
