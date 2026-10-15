# -*- coding: utf-8 -*-
"""手部检测：MediaPipe Tasks API（HandLandmarker），输出手在「摄像头画面」中的位置。

mediapipe 1.x 已移除旧的 mp.solutions，改为 Tasks API，需要配套的
models/hand_landmarker.task 模型文件（已放在项目 models/ 下）。
检测器抽象成接口，将来要换别的手部模型，只需新写一个类实现 detect()。
"""
import os
from typing import Optional, Tuple

import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    _HAS_MP = True
except Exception:
    _HAS_MP = False

MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "models", "hand_landmarker.task")


class HandDetector:
    """接口：detect(frame_bgr) -> (x, y) 摄像头像素坐标 或 None。"""

    def detect(self, frame_bgr) -> Optional[Tuple[float, float]]:
        raise NotImplementedError

    def close(self):
        pass


class MediaPipeHandDetector(HandDetector):
    def __init__(self, max_hands: int = 1, det_conf: float = 0.5,
                 track_conf: float = 0.5):
        if not _HAS_MP:
            raise RuntimeError("未安装 mediapipe")
        if not os.path.exists(MODEL_PATH):
            raise RuntimeError(f"缺少手部模型文件: {MODEL_PATH}")
        opts = mp_vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=mp_vision.RunningMode.IMAGE,
            num_hands=max_hands,
            min_hand_detection_confidence=det_conf,
            min_hand_presence_confidence=det_conf,
            min_tracking_confidence=track_conf,
        )
        self._det = mp_vision.HandLandmarker.create_from_options(opts)
        self._palm_id = 9          # 中指掌指关节 ≈ 掌心

    def detect(self, frame_bgr) -> Optional[Tuple[float, float]]:
        h, w = frame_bgr.shape[:2]
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = self._det.detect(mp_img)
        if not res.hand_landmarks:
            return None
        lm = res.hand_landmarks[0][self._palm_id]
        return (float(lm.x * w), float(lm.y * h))

    def landmarks(self, frame_bgr):
        """可选：返回首只手全部关键点的像素坐标，用于画骨架。"""
        h, w = frame_bgr.shape[:2]
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = self._det.detect(mp_img)
        if not res.hand_landmarks:
            return None
        return [(p.x * w, p.y * h) for p in res.hand_landmarks[0]]

    def close(self):
        try:
            self._det.close()
        except Exception:
            pass


class NullHandDetector(HandDetector):
    def detect(self, frame_bgr):
        return None
