# -*- coding: utf-8 -*-
"""摄像头取流与 MJPEG 推流。

Windows 上只走 DirectShow（MSMF 在本机 USB 摄像头上会 `Failed to select stream 0`）。
分辨率按候选列表逐个尝试，只认真正 read() 出帧的那一个——避免
「句柄打开成功但永远读不到帧」的黑屏。
"""
import threading
import time
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from .. import config


def _parse_local_index(source_url: str) -> int:
    try:
        return int(str(source_url).strip())
    except Exception:
        return 0


# 判定「整帧全黑」的阈值：本机实测 1920x1080 那档能开能读但 mean=0.0，
# 属于设备不支持的假分辨率，必须排除掉。
BLACK_MEAN = 1.0


def open_capture(source_type: str, source_url: str,
                 width: int, height: int) -> Tuple[Optional[cv2.VideoCapture], str]:
    """打开一路视频源，返回 (cap, 说明)。本地设备带分辨率降级。

    候选分辨率里优先挑**真正能出非全黑画面**的那一档；只有全部候选都全黑时，
    才退而接受一个全黑的（并在说明里标注），避免在黑屏上跑整套系统。
    """
    if source_type == "local_device":
        index = _parse_local_index(source_url)
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            return None, f"摄像头 index={index} 打不开（可能被别的程序占用）"
        candidates = [(width, height)] + [
            r for r in config.CAM_FALLBACK_RESOLUTIONS if r != (width, height)]
        black_hit = None      # (w, h, real) —— 能读但全黑，兜底用
        for (w, h) in candidates:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            for _ in range(8):
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                real = "%dx%d" % (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                                  int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
                if float(frame.mean()) >= BLACK_MEAN:
                    return cap, f"index={index} 分辨率={real}"
                if black_hit is None:
                    black_hit = (w, h, real)
                break          # 这一档只出全黑，换下一档
            # 该分辨率读不到帧，试下一个
        if black_hit is not None:
            w, h, real = black_hit
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            return cap, f"index={index} 分辨率={real}（画面全黑，可能不是真实可用分辨率）"
        cap.release()
        return None, f"摄像头 index={index} 能打开但读不到帧"

    url = str(source_url).strip()
    api = cv2.CAP_FFMPEG if url.lower().startswith(("rtsp", "http")) else cv2.CAP_ANY
    cap = cv2.VideoCapture(url, api) if api != cv2.CAP_ANY else cv2.VideoCapture(url)
    if not cap.isOpened():
        cap.release()
        return None, f"视频源打不开: {url}"
    ok, frame = cap.read()
    if not ok or frame is None:
        cap.release()
        return None, f"视频源无数据: {url}"
    return cap, f"{url} {frame.shape[1]}x{frame.shape[0]}"


class VideoSource:
    """一路持续取流的视频源，带最新帧缓存（供推流复用）。"""

    def __init__(self, source_type: str, source_url: str, width: int, height: int):
        self.source_type = source_type
        self.source_url = source_url
        self.description = ""
        self._cap, self.description = open_capture(source_type, source_url, width, height)
        self._lock = threading.Lock()
        self._last_good: Optional[np.ndarray] = None
        self._last_good_ts = 0.0

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def read(self) -> Optional[np.ndarray]:
        """读一帧；**读不到就返回 None**，不拿旧帧糊弄调用方。

        运行主循环靠这个 None 判断相机是不是掉线了（早先这里回落到
        self._last_good，导致掉线后永远读得到帧，掉线检测形同虚设）。
        """
        if self._cap is None:
            return None
        with self._lock:
            ok, frame = self._cap.read()
        if ok and frame is not None:
            self._last_good = frame
            self._last_good_ts = time.monotonic()
            return frame
        return None

    def latest(self, max_age: Optional[float] = None) -> Optional[np.ndarray]:
        """最近一帧。传 max_age 则超过这么久没有新帧就当作没有（预览用，避免一直显示冻结画面）。"""
        if self._last_good is None:
            return None
        if max_age is not None and time.monotonic() - self._last_good_ts > max_age:
            return None
        return self._last_good

    def release(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None


def encode_jpeg(frame: np.ndarray, quality: int = 80) -> Optional[bytes]:
    if frame is None:
        return None
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else None


def mjpeg_chunk(jpeg: bytes) -> bytes:
    return (b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
            + jpeg + b"\r\n")


def placeholder_frame(text: str, width: int = 960, height: int = 540) -> np.ndarray:
    """取不到画面时的占位帧，避免前端一片黑看不出原因。"""
    frame = np.full((height, width, 3), 22, dtype=np.uint8)
    cv2.putText(frame, text, (24, height // 2), cv2.FONT_HERSHEY_SIMPLEX,
                0.9, (80, 200, 255), 2, cv2.LINE_AA)
    return frame


class VideoManager:
    """按 camera_id 缓存已打开的 VideoSource。"""

    def __init__(self):
        self._sources: Dict[str, VideoSource] = {}
        self._lock = threading.Lock()

    def open(self, camera_id: str, source_type: str, source_url: str,
             width: int, height: int) -> VideoSource:
        # 快速路径：已有可用源直接返回（锁内只做字典读写）
        old = None
        with self._lock:
            src = self._sources.get(camera_id)
            if src is not None and src.is_open:
                return src
            if src is not None:
                self._sources.pop(camera_id, None)
                old = src
        # 锁外释放旧源、构造新源：cv2.VideoCapture(DSHOW) 打开是秒级阻塞，
        # 不能占着 VideoManager 的全局锁 —— 否则预览页在相机打不开时反复重试，
        # 会一直抢锁，把 start() 的 open 卡住。
        if old is not None:
            old.release()
        new = VideoSource(source_type, source_url, width, height)
        with self._lock:
            cur = self._sources.get(camera_id)
            if cur is not None and cur.is_open:
                # 并发下别的线程已放好可用源，丢弃自己这份
                new.release()
                return cur
            self._sources[camera_id] = new
            return new

    def get(self, camera_id: str) -> Optional[VideoSource]:
        return self._sources.get(camera_id)

    def close(self, camera_id: str):
        with self._lock:
            src = self._sources.pop(camera_id, None)
        if src is not None:
            src.release()

    def close_all(self):
        with self._lock:
            items = list(self._sources.values())
            self._sources.clear()
        for src in items:
            src.release()


video_manager = VideoManager()
