# -*- coding: utf-8 -*-
"""动作 / 工序定义（可复用的动作与工序抽象）。

工序 = 一串步骤；每一步指定「该去哪个料盒拿料」。
后续要接入「放置/装配」类动作时，在这里扩展 Step 的字段即可。
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Step:
    index: int
    box_id: str        # 该步骤应取的料盒 id
    name: str          # 人类可读的动作名


@dataclass
class Process:
    name: str
    steps: List[Step] = field(default_factory=list)

    def target_box_id(self, step_index: int) -> Optional[str]:
        if 0 <= step_index < len(self.steps):
            return self.steps[step_index].box_id
        return None

    def step_name(self, step_index: int) -> str:
        if 0 <= step_index < len(self.steps):
            return self.steps[step_index].name
        return ""


def default_process() -> Process:
    """示例工序：依次取三样料。"""
    return Process("示例工序", [
        Step(0, "box1", "取垫片"),
        Step(1, "box2", "取螺栓"),
        Step(2, "box3", "取螺母"),
    ])
