# -*- coding: utf-8 -*-
"""料盒布局：在「投影坐标系」（1024x768）里定义每个料盒的位置。

工人面前的料盒与投影画面里的位置一一对应。启动标定后，
投影坐标 <-> 摄像头坐标可以互转，从而把「手的位置」落到某个料盒。
"""
from dataclasses import dataclass
from typing import List


@dataclass
class Box:
    id: str
    name: str
    cx: float          # 投影坐标（像素）
    cy: float
    r: float           # 判定半径（像素）


def default_boxes() -> List[Box]:
    """默认布局：一排 3 个料盒，放在投影画面下半部。可自行调整。"""
    y = 560
    xs = [220, 512, 804]
    names = ["料盒 A", "料盒 B", "料盒 C"]
    return [Box(f"box{i + 1}", names[i], xs[i], y, 130) for i in range(3)]
