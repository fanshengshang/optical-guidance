# -*- coding: utf-8 -*-
"""临时：查看 mediapipe 1.1.0 暴露的接口。"""
import pkgutil
import mediapipe

print("mediapipe", mediapipe.__version__)
print("top modules:", sorted(m.name for m in pkgutil.iter_modules(mediapipe.__path__)))

try:
    from mediapipe.tasks.python import vision
    names = [n for n in dir(vision) if "Hand" in n or "Gesture" in n]
    print("tasks.python.vision OK, hand-related:", names)
except Exception as e:
    print("tasks.python.vision failed:", repr(e))

try:
    from mediapipe.tasks.python import BaseOptions
    print("BaseOptions OK")
except Exception as e:
    print("BaseOptions failed:", repr(e))

try:
    import mediapipe as mp
    print("dir(mediapipe) sample:", [n for n in dir(mp) if not n.startswith("_")][:20])
except Exception as e:
    print(e)
