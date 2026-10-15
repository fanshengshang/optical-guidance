# -*- coding: utf-8 -*-
"""引导引擎：把「手的位置 + 当前步骤」翻译成每个料盒的指示颜色。

第一版规则：
  - 目标料盒：常显「待取」提示色（淡绿）
  - 手伸进目标料盒并停留 -> 绿（拿对），抬手离开后自动进入下一步
  - 手伸进非目标料盒并停留 -> 红（拿错）
"""
import time
from typing import Dict, List, Optional, Tuple

from layout import Box
from process import Process


class GuidanceEngine:
    def __init__(self, boxes: List[Box], process: Process,
                 dwell: float = 0.12):
        self.boxes = {b.id: b for b in boxes}
        self.process = process
        self.dwell = dwell
        self.step_index = 0
        self._enter_at: Dict[str, float] = {}
        self._cur_box: Optional[str] = None
        self._satisfied = False
        self.last_wrong_box: Optional[str] = None

    @property
    def target_box_id(self) -> Optional[str]:
        return self.process.target_box_id(self.step_index)

    def _box_at(self, px: float, py: float) -> Optional[str]:
        for b in self.boxes.values():
            if (px - b.cx) ** 2 + (py - b.cy) ** 2 <= b.r ** 2:
                return b.id
        return None

    def update(self, hand_proj_xy: Optional[Tuple[float, float]]):
        """返回 (colors, hand_box_id, event)。

        colors: {box_id: 'hint'|'green'|'red'|None}
        event : ('ok'|'wrong'|'advance', box_id) 或 None
        """
        now = time.monotonic()
        target = self.target_box_id
        colors: Dict[str, Optional[str]] = {bid: None for bid in self.boxes}
        if target:
            colors[target] = "hint"

        hand_box = None
        if hand_proj_xy is not None:
            hand_box = self._box_at(hand_proj_xy[0], hand_proj_xy[1])

        event = None
        if hand_box is None:
            # 手已离开：若本步已拿对，则推进到下一步
            if self._satisfied:
                if self.advance():
                    event = ("advance", None)
            self._enter_at.clear()
            self._cur_box = None
        else:
            # 手从一个料盒换到另一个料盒时要重新计时；
            # 否则 setdefault 会命中上一次停留留下的旧时间戳，导致“一进入就判定已停留”。
            if hand_box != self._cur_box:
                self._cur_box = hand_box
                self._enter_at.clear()
            started = self._enter_at.setdefault(hand_box, now)
            if now - started >= self.dwell:
                if hand_box == target:
                    colors[hand_box] = "green"
                    if not self._satisfied:
                        self._satisfied = True
                        event = ("ok", hand_box)
                else:
                    colors[hand_box] = "red"
                    self.last_wrong_box = hand_box
                    event = ("wrong", hand_box)
            else:
                # 刚进入，未满停留，先给中性色
                colors[hand_box] = "hint" if hand_box == target else "warn"

        return colors, hand_box, event

    def advance(self) -> bool:
        if self.step_index < len(self.process.steps) - 1:
            self.step_index += 1
            self._satisfied = False
            self._enter_at.clear()
            self._cur_box = None
            return True
        return False

    def at_end(self) -> bool:
        return self.step_index >= len(self.process.steps) - 1
