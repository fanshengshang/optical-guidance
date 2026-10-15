# -*- coding: utf-8 -*-
"""临时：在 OpenCV 5.0 下多方式探测摄像头。"""
import time
import cv2

print("cv2", cv2.__version__)

try:
    reg = cv2.videoio_registry
    print("backends:", [reg.getBackendName(b) for b in reg.getBackends()])
except Exception as e:
    print("registry err:", e)


def try_cam(label, src, backend=None):
    try:
        cap = cv2.VideoCapture(src) if backend is None else cv2.VideoCapture(src, backend)
    except Exception as e:
        print(f"{label}: ctor error {e}")
        return False
    if not cap.isOpened():
        print(f"{label}: NOT opened")
        cap.release()
        return False
    ok, f = False, None
    for _ in range(20):
        ok, f = cap.read()
        if ok:
            break
        time.sleep(0.05)
    print(f"{label}: opened, read={ok}, shape={None if f is None else f.shape}")
    cap.release()
    return ok


combos = [
    ("DSHOW idx0", 0, cv2.CAP_DSHOW),
    ("MSMF  idx0", 0, cv2.CAP_MSMF),
    ("DEFAULT idx0", 0, None),
    ("MSMF  idx1", 1, cv2.CAP_MSMF),
    ("DSHOW str0", "0", cv2.CAP_DSHOW),
    ("MSMF  str0", "0", cv2.CAP_MSMF),
]
for label, src, be in combos:
    try_cam(label, src, be)
print("PROBE2 DONE")
