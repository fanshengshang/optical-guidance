# -*- coding: utf-8 -*-
"""临时：列出可能占用摄像头的进程（python / 相机类程序）。"""
import subprocess

out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                     capture_output=True, text=True, errors="replace").stdout
keys = ["python", "amcap", "camera", "相机", "wechat", "weixin", "qq", "teams",
        "zoom", "obs", "douyin", "youdao", "explorer"]
hit = []
for line in out.splitlines():
    low = line.lower()
    if any(k in low for k in keys):
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2:
            hit.append((parts[0], parts[1]))
for name, pid in sorted(set(hit)):
    if "python" in name.lower():
        print("PY ", name, pid)
for name, pid in sorted(set(hit)):
    if "python" not in name.lower():
        print("APP", name, pid)
print("TOTAL", len(set(hit)))
