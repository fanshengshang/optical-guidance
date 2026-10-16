# -*- coding: utf-8 -*-
"""投影画面状态机。

投影页（浏览器 kiosk 全屏到副屏）按固定节奏拉取这里的快照并渲染，
所以标定用的「全黑/全白」和运行时的「红绿引导」都只是同一个状态的不同 mode。
"""
import threading
import time
from typing import Any, Dict, Optional

from .. import config
from ..core import guide_config


class ProjectorService:
    def __init__(self):
        self._lock = threading.Lock()
        # 动画相关字段随有效引导配置走（默认取自 guide_config，运行时会被覆盖）
        self._state: Dict[str, Any] = {
            "mode": "idle",
            "proj_size": [config.PROJ_W, config.PROJ_H],
            "targets": [],
            "colors": {},
            "step_index": 0,
            "step_total": 0,
            "step_text": "",
            "instruction": "",
            "hand_xy": None,
            "progress": None,
            "flash": None,
            "message": "等待启动",
            "announce": None,          # 开始/结束提示 {text, tone: 'start'|'end'}
            "seq": 0,
            # ── 引导动画参数（前端据此渲染脉冲 / 进度环 / 箭头） ──
            "pulse_enabled": guide_config.DEFAULT["pulse_enabled"],
            "pulse_period_ms": guide_config.DEFAULT["pulse_period_ms"],
            "ring_enabled": guide_config.DEFAULT["ring_enabled"],
            "arrow_enabled": guide_config.DEFAULT["arrow_enabled"],
        }
        self._flash_until = 0.0

    # ---------- 写 ----------
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            # flash 是一次性闪烁，过期就在同一把锁里清掉，避免读改写竞争
            if self._flash_until and time.monotonic() > self._flash_until:
                self._state["flash"] = None
                self._flash_until = 0.0
            return dict(self._state)

    def _bump(self, **changes):
        with self._lock:
            self._state.update(changes)
            self._state["seq"] = int(self._state.get("seq", 0)) + 1

    def set_mode(self, mode: str, message: str = ""):
        self._bump(mode=mode, message=message)

    def set_idle(self, message: str = "等待启动"):
        self._bump(mode="idle", colors={}, hand_xy=None, progress=None, flash=None,
                   step_text="", instruction="", step_index=0, step_total=0,
                   announce=None, message=message)

    def set_announce(self, text: str, tone: str = "start", message: str = ""):
        """开始/结束提示：在投影屏上显示一段大字文案（tone=start 蓝 / end 绿）。"""
        self._bump(mode="announce", announce={"text": text, "tone": tone},
                   colors={}, hand_xy=None, progress=None, flash=None,
                   step_text="", instruction="", step_index=0, step_total=0,
                   message=message or text)

    def update_guide(self, targets, colors, step_index, step_total,
                     step_text, hand_xy, flash=None, message="",
                     instruction: str = "",
                     progress: Optional[float] = None,
                     guide: Optional[Dict[str, Any]] = None):
        changes: Dict[str, Any] = dict(
            mode="guide", targets=list(targets), colors=dict(colors),
            step_index=step_index, step_total=step_total, step_text=step_text,
            instruction=instruction or "",
            hand_xy=list(hand_xy) if hand_xy else None,
            progress=(None if progress is None else round(float(progress), 3)),
            flash=flash, message=message, announce=None)
        # 动画参数只在有效配置存在时覆盖，否则沿用上一次 / 默认，避免闪烁
        if guide:
            changes.update(
                pulse_enabled=bool(guide.get("pulse_enabled", True)),
                pulse_period_ms=int(guide.get("pulse_period_ms", 1200)),
                ring_enabled=bool(guide.get("ring_enabled", True)),
                arrow_enabled=bool(guide.get("arrow_enabled", False)))
        if flash:
            self._flash_until = time.monotonic() + 0.45
        self._bump(**changes)


projector_service = ProjectorService()
