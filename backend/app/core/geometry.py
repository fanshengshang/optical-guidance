# -*- coding: utf-8 -*-
"""投影 <-> 摄像头 坐标换算（纯函数）。"""
from typing import Tuple

import cv2
import numpy as np


def cam_to_proj(pt: Tuple[float, float], homography_inv) -> Tuple[float, float]:
    """摄像头坐标 -> 投影坐标。"""
    p = np.array([[list(pt)]], dtype=np.float32)
    q = cv2.perspectiveTransform(p, np.asarray(homography_inv, dtype=np.float64))
    return float(q[0][0][0]), float(q[0][0][1])


def proj_to_cam(pt: Tuple[float, float], homography) -> Tuple[int, int]:
    """投影坐标 -> 摄像头坐标。"""
    p = np.array([[list(pt)]], dtype=np.float32)
    q = cv2.perspectiveTransform(p, np.asarray(homography, dtype=np.float64))
    return int(round(float(q[0][0][0]))), int(round(float(q[0][0][1])))
