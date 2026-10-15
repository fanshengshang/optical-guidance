# -*- coding: utf-8 -*-
"""抓拍：把判定瞬间的画面落到 snapshots/，供追溯页回看。"""
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

from .. import config


def _day() -> str:
    return datetime.now().strftime("%Y%m%d")


def save_snapshot(frame: Optional[np.ndarray], run_id: str, step_index: int,
                  result: str) -> Optional[str]:
    """存一张抓拍，返回**相对 DATA_DIR 的路径**（库里就存这个）。"""
    if frame is None:
        return None
    try:
        rel_dir = ("snapshots", _day())
        abs_dir = config.data_path(*rel_dir)
        abs_dir.mkdir(parents=True, exist_ok=True)
        name = f"{run_id}_step{step_index:02d}_{result}.jpg"
        abs_path = abs_dir / name
        cv2.imwrite(str(abs_path), frame)
        return config.data_relative(abs_path)
    except Exception:
        return None
