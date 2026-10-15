# -*- coding: utf-8 -*-
"""临时：无 GUI 单测引导引擎逻辑（不需要摄像头/投影仪）。"""
import time

from engine import GuidanceEngine
from layout import default_boxes
from process import default_process

BOXES = default_boxes()
B = {b.id: (b.cx, b.cy) for b in BOXES}
AWAY = (-500.0, -500.0)   # 手离开所有料盒

ok_all = True


def check(label, got, want):
    global ok_all
    good = got == want
    ok_all = ok_all and good
    print(f"[{'PASS' if good else 'FAIL'}] {label}: got={got} want={want}")


def step_over(e, dwell):
    time.sleep(dwell + 0.03)


def fresh(dwell=0.05):
    return GuidanceEngine(BOXES, default_process(), dwell=dwell)


# ---- 1. 正确料盒停留 -> 绿 + ok ----
e = fresh()
c, hb, ev = e.update(B["box1"])
check("刚进入目标盒(未满停留) 颜色", c["box1"], "hint")
check("刚进入目标盒 无事件", ev, None)
step_over(e, 0.05)
c, hb, ev = e.update(B["box1"])
check("满停留 目标盒颜色=绿", c["box1"], "green")
check("满停留 事件=ok", ev, ("ok", "box1"))

# ---- 2. 抬手离开 -> advance 到下一步 ----
c, hb, ev = e.update(AWAY)
check("离开后 事件=advance", ev, ("advance", None))
check("离开后 步骤号", e.step_index, 1)
check("离开后 目标盒", e.target_box_id, "box2")

# ---- 3. 进错料盒 -> 红 + wrong ----
c, hb, ev = e.update(B["box1"])
time.sleep(0.08)
c, hb, ev = e.update(B["box1"])
check("错盒满停留 颜色=红", c["box1"], "red")
check("错盒满停留 事件=wrong", ev, ("wrong", "box1"))
check("错盒时 目标盒仍为提示色", c["box2"], "hint")

# ---- 4. 关键回归：A->B->A 不应“一进入就判定” ----
e = fresh(dwell=0.2)
e.update(B["box1"])          # 进 A，开始计时
time.sleep(0.25)
e.update(B["box1"])          # A 满停留
# 手移到 B（另一个盒），再立刻回到 A，应重新计时，未满停留
e.update(B["box2"])
c, hb, ev = e.update(B["box1"])
check("回到 A 后未满停留 颜色不是绿", c["box1"] in ("hint", "warn"), True)
check("回到 A 后未满停留 事件", ev, None)

# ---- 5. 走完全程 ----
e = fresh()
for bid in ["box1", "box2", "box3"]:
    e.update(B[bid]); time.sleep(0.08); e.update(B[bid])
    e.update(AWAY)
check("走完全程 到达末步", e.step_index, 2)
check("末步 目标盒", e.target_box_id, "box3")
check("at_end", e.at_end(), True)

print()
print("ENGINE TEST:", "ALL PASS" if ok_all else "HAS FAILURE")
