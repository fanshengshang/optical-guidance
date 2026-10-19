# -*- coding: utf-8 -*-
"""引导判定引擎（纯逻辑，无 I/O，可单测）。

规则：
  - 目标取料位常显「待取」提示色（hint）
  - 手进入目标位并停留 dwell 秒 -> green（拿对），拿对**立即**推进到下一步，
    刚完成的那格锁绿（green）直到手离开，期间绝不判红/判错
  - 手进入非目标位并停留 dwell 秒 -> red（拿错；若该位属于后面步骤，另标「顺序错」）
  - 手刚进入、未满停留 -> 中性色（目标位 hint / 非目标位 warn），并给出停留进度
  - 误触：手进了目标位、但没停够 dwell 就离开
  - 拿错后该位持续红（可关），直到拿对 / 推进

判定项与阈值都由 guide_config 传进来（dwell / 是否检顺序错 / 是否检误触 等），
本类只接收参数、不内置业务策略。

坐标一律是**投影坐标系**；调用方负责把摄像头坐标换算过来。
"""
import time
from typing import Dict, List, Optional, Tuple


class Target:
    __slots__ = ("id", "name", "x", "y", "r", "shape", "w", "h", "color")

    def __init__(self, id: str, name: str = "", x: float = 0.0, y: float = 0.0,
                 r: float = 80.0, shape: str = "circle", w: float = 160.0, h: float = 160.0,
                 color: str = "#38bdf8"):
        self.id = id
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.r = float(r)
        self.shape = shape
        self.w = float(w)
        self.h = float(h)
        self.color = color

    def contains(self, px: float, py: float) -> bool:
        if self.shape == "rect":
            return abs(px - self.x) <= self.w / 2 and abs(py - self.y) <= self.h / 2
        return (px - self.x) ** 2 + (py - self.y) ** 2 <= self.r ** 2

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "shape": self.shape,
                "x": self.x, "y": self.y, "r": self.r, "w": self.w, "h": self.h,
                "color": self.color}


class Step:
    __slots__ = ("order", "target_id", "name", "target_name", "instruction", "dwell_sec")

    def __init__(self, order: int, target_id: str, name: str = "", target_name: str = "",
                 instruction: str = "", dwell_sec: Optional[float] = None):
        self.order = order
        self.target_id = target_id
        self.name = name
        self.target_name = target_name
        self.instruction = instruction
        self.dwell_sec = dwell_sec


class GuidanceEngine:
    def __init__(self, targets: List[Target], steps: List[Step], dwell: float = 0.12,
                 detect_wrong_order: bool = True, detect_mis_touch: bool = True,
                 mis_touch_sec: float = 0.05, hold_red_until_correct: bool = True):
        self.targets: Dict[str, Target] = {t.id: t for t in targets}
        self.steps: List[Step] = list(steps)
        self.dwell = float(dwell)
        self.detect_wrong_order = bool(detect_wrong_order)
        self.detect_mis_touch = bool(detect_mis_touch)
        self.mis_touch_sec = float(mis_touch_sec)
        self.hold_red_until_correct = bool(hold_red_until_correct)
        self.step_index = 0
        self._enter_at: Dict[str, float] = {}
        self._cur_target: Optional[str] = None
        self._satisfied = False
        self._done_target: Optional[str] = None     # 刚拿对、手还没离开的位（锁绿）
        self._wrong_hold: Optional[str] = None      # 拿错后持续红提示的取料位
        self.last_wrong_target: Optional[str] = None

    # ---------- 查询 ----------
    @property
    def target_id(self) -> Optional[str]:
        if 0 <= self.step_index < len(self.steps):
            return self.steps[self.step_index].target_id
        return None

    @property
    def step_total(self) -> int:
        return len(self.steps)

    def step_text(self) -> str:
        if not self.steps:
            return "未配置工序"
        s = self.steps[self.step_index]
        label = s.name or s.target_name or s.target_id
        return f"第 {self.step_index + 1}/{len(self.steps)} 步：{label}"

    def step_instruction(self) -> str:
        """当前步的引导提示词（管理人员在工序步骤里填，可留空）。"""
        if not self.steps:
            return ""
        return (self.steps[self.step_index].instruction or "").strip()

    def current_dwell(self) -> float:
        """当前步的停留时长：步骤单独设了就优先用，否则回落全局 dwell。"""
        if self.steps:
            step_dwell = self.steps[self.step_index].dwell_sec
            if step_dwell is not None:
                try:
                    return max(0.0, float(step_dwell))
                except (TypeError, ValueError):
                    pass
        return self.dwell

    def at_end(self) -> bool:
        return bool(self.steps) and self.step_index >= len(self.steps) - 1

    @property
    def satisfied(self) -> bool:
        """当前这一步是否已拿对（用于判断整条工序是否完成）。"""
        return self._satisfied

    def target_at(self, px: float, py: float) -> Optional[str]:
        for t in self.targets.values():
            if t.contains(px, py):
                return t.id
        return None

    def _step_index_of(self, target_id: str) -> Optional[int]:
        """某个取料位是第几步要求的（同名取料位取最先出现的步骤）。"""
        for i, s in enumerate(self.steps):
            if s.target_id == target_id:
                return i
        return None

    def _is_future_target(self, target_id: str) -> bool:
        """该取料位是否是「后面某一步」才该取的 —— 用于区分「顺序错」。"""
        idx = self._step_index_of(target_id)
        return idx is not None and idx > self.step_index

    # ---------- 主判定 ----------
    def update(self, hand_xy: Optional[Tuple[float, float]]):
        """返回 (colors, hand_target, event, progress)。

        colors  : {target_id: 'hint'|'green'|'red'|'warn'|None}
        event   : ('ok'|'wrong'|'wrong_order'|'mis_touch', target_id or None,
                   event_step) —— event_step 是事件发生那一刻的步骤序号，
                   尤其 ok 事件在 advance 前记录，避免归因错位到下一步。
        progress: 手在当前位的停留进度 0..1（没落在任何取料位时为 None）
        """
        now = time.monotonic()
        want = self.target_id
        dwell = self.current_dwell()
        colors: Dict[str, Optional[str]] = {tid: None for tid in self.targets}
        if want:
            colors[want] = "hint"
        # 拿错后持续的红色提示（直到拿对 / 推进）
        if self.hold_red_until_correct and self._wrong_hold in colors:
            colors[self._wrong_hold] = "red"

        hand_target = None
        if hand_xy is not None:
            hand_target = self.target_at(hand_xy[0], hand_xy[1])

        event = None
        progress = None
        if hand_target is None:
            prev = self._cur_target
            # 手抬离：刚完成的锁绿位随之解除（手真的离开了该位）
            self._done_target = None
            # 误触：手进了目标位、没停够 dwell 就离开
            if (self.detect_mis_touch and prev is not None and prev == want
                    and not self._satisfied):
                stayed = now - self._enter_at.get(prev, now)
                if self.mis_touch_sec <= stayed < dwell:
                    event = ("mis_touch", prev, self.step_index)
            self._enter_at.clear()
            self._cur_target = None
        else:
            # 换到另一个位时重新计时（否则会命中上一次停留的旧时间戳）
            if hand_target != self._cur_target:
                # 手离开了刚完成的锁绿位，解除锁绿
                if self._done_target is not None and hand_target != self._done_target:
                    self._done_target = None
                self._cur_target = hand_target
                self._enter_at.clear()
            started = self._enter_at.setdefault(hand_target, now)
            elapsed = now - started
            progress = min(1.0, elapsed / dwell) if dwell > 0 else 1.0

            # 手停在刚完成的锁绿位：保持绿，不再参与任何判定（绝不判红）
            if self._done_target is not None and hand_target == self._done_target:
                colors[hand_target] = "green"
                progress = 1.0
            elif elapsed >= dwell:
                if hand_target == want:
                    colors[hand_target] = "green"
                    self._wrong_hold = None
                    if not self._satisfied:
                        self._satisfied = True
                        # 事件发生在 advance 之前，记下此刻的步序，避免归因错位
                        event = ("ok", hand_target, self.step_index)
                        # 拿对即推进：立刻进入下一步，并把刚完成位锁绿到手离开。
                        # 手无需抬离，下一步的蓝光提示已经亮起。
                        if self.advance():
                            self._done_target = hand_target
                            want = self.target_id
                            if want:
                                colors[want] = "hint"
                            if self.hold_red_until_correct and self._wrong_hold in colors:
                                colors[self._wrong_hold] = "red"
                else:
                    colors[hand_target] = "red"
                    self.last_wrong_target = hand_target
                    self._wrong_hold = hand_target
                    if self.detect_wrong_order and self._is_future_target(hand_target):
                        event = ("wrong_order", hand_target, self.step_index)
                    else:
                        event = ("wrong", hand_target, self.step_index)
            else:
                colors[hand_target] = "hint" if hand_target == want else "warn"

        return colors, hand_target, event, progress

    def advance(self) -> bool:
        """推进到下一步。返回 False 表示已是最后一步、无下一步可推。

        方案 A：拿对即推进 —— 由 update() 在「ok」事件里立即调用，
        不再等手抬离。刚完成位的锁绿由调用方用 _done_target 记录。
        """
        if self.step_index < len(self.steps) - 1:
            self.step_index += 1
            self._satisfied = False
            self._enter_at.clear()
            self._cur_target = None
            self._wrong_hold = None
            return True
        return False

    def reset(self):
        self.step_index = 0
        self._satisfied = False
        self._done_target = None
        self._enter_at.clear()
        self._cur_target = None
        self._wrong_hold = None
        self.last_wrong_target = None
