# -*- coding: utf-8 -*-
"""手部检测（MediaPipe Tasks API · HandLandmarker）。

mediapipe 1.x 已移除旧的 mp.solutions，改用 Tasks API，需要配套的
hand_landmarker.task 模型文件。检测器做成可替换接口，将来要换别的手部模型
只需新写一个类实现 detect()。
"""
import os
import threading
from typing import List, Optional, Tuple

import numpy as np

from .. import config

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    _HAS_MP = True
except Exception:                                    # pragma: no cover
    _HAS_MP = False

DEFAULT_MODEL_REL = "hand-mediapipe/hand_landmarker.task"


def resolve_model_path(rel_or_abs: str) -> str:
    """model_registry 下的相对路径 -> 本机绝对路径（换机器后自动重定位）。"""
    if rel_or_abs and os.path.isabs(rel_or_abs) and os.path.exists(rel_or_abs):
        return rel_or_abs
    registry = config.MODEL_REGISTRY_DIR
    cand = os.path.join(str(registry), str(rel_or_abs).replace("/", os.sep))
    if os.path.exists(cand):
        return cand
    # 路径失效时按 model_registry 之后的部分重新拼
    marker = "model_registry"
    parts = str(rel_or_abs).replace("\\", "/").split("/")
    if marker in parts:
        tail = parts[parts.index(marker) + 1:]
        cand2 = os.path.join(str(registry), *tail)
        if os.path.exists(cand2):
            return cand2
    return os.path.join(str(registry), *DEFAULT_MODEL_REL.split("/"))


class HandDetector:
    """接口：detect(frame_bgr) -> (x, y) 摄像头像素坐标 或 None。"""

    name = "none"

    def detect(self, frame_bgr) -> Optional[Tuple[float, float]]:
        raise NotImplementedError

    def close(self):
        pass


class MediaPipeHandDetector(HandDetector):
    name = "MediaPipe HandLandmarker"

    def __init__(self, model_asset_path: str, max_hands: int = 1,
                 det_conf: float = 0.5, track_conf: float = 0.5):
        if not _HAS_MP:
            raise RuntimeError("未安装 mediapipe")
        path = resolve_model_path(model_asset_path)
        if not os.path.exists(path):
            raise RuntimeError(f"缺少手部模型文件: {path}")
        self.model_path = path
        opts = mp_vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=path),
            running_mode=mp_vision.RunningMode.IMAGE,
            num_hands=max_hands,
            min_hand_detection_confidence=det_conf,
            min_hand_presence_confidence=det_conf,
            min_tracking_confidence=track_conf,
        )
        self._det = mp_vision.HandLandmarker.create_from_options(opts)
        self._palm_id = 9                     # 中指掌指关节 ≈ 掌心
        self._lock = threading.Lock()

    def detect(self, frame_bgr) -> Optional[Tuple[float, float]]:
        lm = self.landmarks(frame_bgr)
        if not lm:
            return None
        return lm[self._palm_id]

    def landmarks(self, frame_bgr) -> Optional[List[Tuple[float, float]]]:
        if frame_bgr is None:
            return None
        h, w = frame_bgr.shape[:2]
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        with self._lock:
            res = self._det.detect(mp_img)
        if not res.hand_landmarks:
            return None
        return [(float(p.x * w), float(p.y * h)) for p in res.hand_landmarks[0]]

    def close(self):
        # 实测本机 mediapipe 1.1.0 的 HandLandmarker.close() 会长时间阻塞在
        # 内部 executor 上（创建/使用/关闭同线程也一样），正常流程绝不能调它。
        # 检测器进程内缓存复用（见 build_detector），进程退出由操作系统回收。
        pass


class NullHandDetector(HandDetector):
    name = "无检测器"

    def __init__(self, reason: str = ""):
        self.name = f"无检测器({reason})" if reason else "无检测器"

    def detect(self, frame_bgr):
        return None


_DETECTOR_CACHE = {}
_CACHE_LOCK = threading.Lock()


def build_detector(model_rel_path: str = DEFAULT_MODEL_REL) -> HandDetector:
    """构造（并缓存）手部检测器；失败时退回空检测器并把原因带进名字。

    检测器按模型路径**进程内缓存复用**：本机 mediapipe 的 close() 会长时间
    阻塞（见 MediaPipeHandDetector.close 的说明），每轮运行各建各关会把
    停止流程拖死。detect() 内部自带锁，跨线程调用是安全的。
    """
    with _CACHE_LOCK:
        det = _DETECTOR_CACHE.get(model_rel_path)
        if det is None:
            try:
                det = MediaPipeHandDetector(model_rel_path)
            except Exception as exc:
                det = NullHandDetector(str(exc))
            _DETECTOR_CACHE[model_rel_path] = det
        return det
