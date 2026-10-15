# -*- coding: utf-8 -*-
"""临时：验证设置 1920x1080 是否导致读帧失败。"""
import cv2

for be, name in [(cv2.CAP_DSHOW, "DSHOW"), (cv2.CAP_MSMF, "MSMF")]:
    cap = cv2.VideoCapture(0, be)
    print(f"{name}: opened={cap.isOpened()}")
    if not cap.isOpened():
        cap.release()
        continue
    ok, f = cap.read()
    print(f"  default read={ok} shape={None if f is None else f.shape}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    ok2, f2 = False, None
    for _ in range(5):
        ok2, f2 = cap.read()
        if ok2:
            break
    print(f"  after set 1920x1080 -> reported {w}x{h}, read={ok2}, shape={None if f2 is None else f2.shape}")
    cap.release()
print("RESTEST DONE")
