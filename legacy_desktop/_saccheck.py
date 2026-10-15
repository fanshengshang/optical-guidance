# -*- coding: utf-8 -*-
"""临时：读取 Smart App Control 状态与相关策略。"""
import winreg

def read(root, path, name):
    try:
        k = winreg.OpenKey(root, path)
        v, _ = winreg.QueryValueEx(k, name)
        return v
    except FileNotFoundError:
        return "(键不存在)"
    except Exception as e:
        return f"(错误: {e})"

print("SAC VerifiedAndReputablePolicyState =",
      read(winreg.HKEY_LOCAL_MACHINE,
           r"SYSTEM\CurrentControlSet\Control\CI\Policy",
           "VerifiedAndReputablePolicyState"),
      "  (0=关闭 1=开启 2=评估中)")
print("CI Policy\\State\\Security =",
      read(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\CI\State", "Security"))
