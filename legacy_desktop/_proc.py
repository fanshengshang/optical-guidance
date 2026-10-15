# -*- coding: utf-8 -*-
"""临时：查指定 PID 的命令行。"""
import subprocess

pids = [24924, 35708]
for pid in pids:
    cmd = ("Get-CimInstance Win32_Process -Filter \"ProcessId=%d\" | "
           "Select-Object -ExpandProperty CommandLine" % pid)
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, errors="replace")
    print(f"PID {pid}: {(r.stdout or '(none)').strip()}")
