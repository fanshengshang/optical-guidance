# -*- coding: utf-8 -*-
"""临时：测 MediaPipe 在各分辨率下的推理耗时，用于定 CAM 分辨率。"""
import time
import cv2

from detector import MediaPipeHandDetector

det = MediaPipeHandDetector()
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
ok, frame = cap.read()
print("frame:", ok, None if frame is None else frame.shape)
cap.release()

if ok and frame is not None:
    for w, h in [(640, 480), (960, 720), (1280, 720), (1920, 1080)]:
        small = cv2.resize(frame, (w, h))
        # 预热
        det.detect(small)
        n = 12
        t0 = time.perf_counter()
        for _ in range(n):
            det.detect(small)
        dt = (time.perf_counter() - t0) / n
        print(f"{w}x{h}: {dt * 1000:.1f} ms/frame  -> {1 / dt:.1f} fps")
det.close()
print("BENCH DONE")
