# -*- coding: utf-8 -*-
"""投影渲染：在投影仪（副屏）上全屏显示引导画面。

- solid(color)   : 标定用的纯色帧（全黑 / 全白）
- draw(...)      : 常规引导画面（料盒光斑、当前步骤文字）
"""
import tkinter as tk
from typing import Dict, List, Optional, Tuple

# 状态 -> (填充色, 描边色)；填充为 None 表示只要描边
STYLE = {
    "green": ("#16a34a", ""),      # 拿对
    "red": ("#dc2626", ""),        # 拿错
    "hint": ("#14532d", ""),       # 待取提示（暗绿）
    "warn": ("#78350f", ""),       # 手刚进入、尚未判定（暗琥珀）
    None: (None, "#3f4650"),       # 未激活
}

FONT = "Microsoft YaHei"


class ProjectorWindow:
    def __init__(self, root: tk.Tk, geom: str, size: Tuple[int, int]):
        self.w, self.h = size
        self.win = tk.Toplevel(root)
        self.win.title("Projector · 引导画面")
        self.win.geometry(geom)
        self.win.configure(bg="black")
        self.win.attributes("-topmost", True)
        try:
            self.win.overrideredirect(True)
        except Exception:
            pass
        self.c = tk.Canvas(self.win, width=self.w, height=self.h,
                           bg="black", highlightthickness=0)
        self.c.pack(fill="both", expand=True)

    def solid(self, color: str):
        """标定用：整屏一个颜色。"""
        self.c.delete("all")
        self.c.configure(bg=color)

    def draw(self, boxes, colors: Dict[str, Optional[str]],
             step_text: str = "", hand_proj: Optional[Tuple[float, float]] = None,
             flash: Optional[str] = None):
        c = self.c
        c.delete("all")
        c.configure(bg="#0d1013")

        for b in boxes:
            fill, outline = STYLE.get(colors.get(b.id), STYLE[None])
            kwargs = dict(outline=outline or "#3f4650", width=4)
            if fill:
                kwargs["fill"] = fill
            c.create_oval(b.cx - b.r, b.cy - b.r, b.cx + b.r, b.cy + b.r, **kwargs)
            c.create_text(b.cx, b.cy + b.r + 28, text=b.name,
                          fill="#cbd5e1", font=(FONT, 16))

        if hand_proj is not None:
            x, y = hand_proj
            c.create_oval(x - 12, y - 12, x + 12, y + 12, outline="#ffffff", width=2)

        if step_text:
            c.create_text(self.w // 2, 70, text=step_text,
                          fill="#e5e7eb", font=(FONT, 24, "bold"))

        if flash:
            col = "#16a34a" if flash == "green" else "#dc2626"
            c.create_rectangle(0, 0, self.w, 10, fill=col, outline="")

    def close(self):
        try:
            self.win.destroy()
        except Exception:
            pass
