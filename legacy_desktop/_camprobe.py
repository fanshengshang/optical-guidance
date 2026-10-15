# -*- coding: utf-8 -*-
"""临时：探测摄像头不同后端能否打开。"""
import cv2
print("cv2", cv2.__version__)
backends = [(cv2.CAP_DSHOW, "DSHOW"), (cv2.CAP_MSMF, "MSMF"), (cv2.CAP_ANY, "ANY")]
for b, name in backends:
    for i in range(4):
        cap = cv2.VideoCapture(i, b)
        if cap.isOpened():
            ok, f = cap.read()
            print(f"{name} idx={i}: opened, read={ok}, shape={None if f is None else f.shape}")
            cap.release()
            break
        cap.release()
    else:
        print(f"{name}: none of 0-3")
print("PROBE DONE")
