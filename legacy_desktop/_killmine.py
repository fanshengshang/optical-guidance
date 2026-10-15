# -*- coding: utf-8 -*-
"""临时：清理本轮遗留在 light-pilot / optical-guidance 下的 python 进程。"""
import os
import subprocess

ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "
      "'light-pilot|optical-guidance' } | ForEach-Object { "
      "\"$($_.ProcessId)|$($_.CommandLine)\" }")
r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True, text=True, errors="replace")
lines = [l for l in (r.stdout or "").splitlines() if l.strip()]
print("found", len(lines), "processes")
for l in lines:
    pid, _, cmd = l.partition("|")
    pid = pid.strip()
    print(" -", pid, cmd.strip()[:120])
    if pid.isdigit() and int(pid) != os.getpid():
        kr = subprocess.run(["taskkill", "/F", "/PID", pid],
                            capture_output=True, text=True, errors="replace")
        out = (kr.stdout or kr.stderr or "").strip()
        print("   killed ->", out[:100])
print("CLEANUP DONE")
