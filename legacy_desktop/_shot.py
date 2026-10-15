# -*- coding: utf-8 -*-
"""临时：整屏截图（含所有显示器），用于自验证 GUI 实际渲染结果。"""
import sys
from PIL import ImageGrab

out = sys.argv[1] if len(sys.argv) > 1 else "state/shot.png"
img = ImageGrab.grab(all_screens=True)
img.save(out)
print(f"saved {out} size={img.size}")
