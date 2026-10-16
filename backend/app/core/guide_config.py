# -*- coding: utf-8 -*-
"""引导配置：判定 / 动画 / 检错的参数，支持「全局默认 ← 工序覆盖」两层。

设计目标：参数**不写死在代码里**——管理人员可以在「系统设置」页调全局默认，
在「工序编排」页对单个工序做覆盖；运行时取合并后的有效配置。

本模块只做纯逻辑（字段定义 / 校验 / 合并），不碰数据库与 I/O，方便单测。
新增一个可配项 = 往 FIELDS 里加一条，前端表单会自动多出一项。
"""
from typing import Any, Dict, List, Optional

# 可配置项定义。type: bool / int / float；min/max 仅对数值生效。
FIELDS: List[Dict[str, Any]] = [
    # ── 引导动画 ──────────────────────────────────────────────
    {"key": "pulse_enabled", "type": "bool", "default": True,
     "group": "引导动画", "doc": "当前该取的取料位是否做呼吸 / 脉冲动画"},
    {"key": "pulse_period_ms", "type": "int", "default": 1200, "min": 300, "max": 3000,
     "group": "引导动画", "doc": "脉冲周期（毫秒），越小闪得越快"},
    {"key": "ring_enabled", "type": "bool", "default": True,
     "group": "引导动画", "doc": "是否显示停留进度环（手伸进目标位，环走满即判定拿对）"},
    {"key": "arrow_enabled", "type": "bool", "default": False,
     "group": "引导动画", "doc": "是否显示从手位置指向目标位的引导箭头"},
    # ── 判定 ──────────────────────────────────────────────────
    {"key": "dwell_sec", "type": "float", "default": 0.12, "min": 0.02, "max": 2.0,
     "group": "判定", "doc": "手停留在取料位多久算「拿对」（秒），越小越灵敏"},
    {"key": "detect_every_n_frames", "type": "int", "default": 1, "min": 1, "max": 5,
     "group": "判定", "doc": "手部检测跳帧：每 N 帧检一次、中间沿用上次位置，值越大越省 CPU（N=1 即每帧都检）"},
    # ── 检错 ──────────────────────────────────────────────────
    {"key": "detect_wrong_order", "type": "bool", "default": True,
     "group": "检错", "doc": "检测顺序错：手伸向了后面步骤才该取的取料位"},
    {"key": "detect_mis_touch", "type": "bool", "default": True,
     "group": "检错", "doc": "检测误触：手进了目标位但没停够 dwell 就离开"},
    {"key": "mis_touch_sec", "type": "float", "default": 0.05, "min": 0.0, "max": 1.0,
     "group": "检错", "doc": "误触的最小停留（秒），低于它才算「碰了一下」"},
    {"key": "hold_red_until_correct", "type": "bool", "default": True,
     "group": "检错", "doc": "拿错后持续显示红色直到纠正，而不是一闪而过"},
]

_BY_KEY: Dict[str, Dict[str, Any]] = {f["key"]: f for f in FIELDS}
DEFAULT: Dict[str, Any] = {f["key"]: f["default"] for f in FIELDS}


def defaults() -> Dict[str, Any]:
    return dict(DEFAULT)


def field_meta() -> List[Dict[str, Any]]:
    """字段元信息，供前端自动渲染表单（含分组、类型、范围、说明）。"""
    return [dict(f) for f in FIELDS]


def sanitize(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把任意外来配置过滤成合法值：只保留认识的键，类型 / 范围不对的丢弃。"""
    out: Dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        spec = _BY_KEY.get(key)
        if spec is None:
            continue
        kind = spec["type"]
        try:
            if kind == "bool":
                out[key] = bool(val)
            elif kind == "int":
                iv = int(val)
                lo, hi = spec.get("min"), spec.get("max")
                if lo is not None:
                    iv = max(lo, min(hi, iv))
                out[key] = iv
            elif kind == "float":
                fv = float(val)
                lo, hi = spec.get("min"), spec.get("max")
                if lo is not None:
                    fv = max(lo, min(hi, fv))
                out[key] = round(fv, 4)
        except (TypeError, ValueError):
            continue
    return out


def merge(*layers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """按顺序叠加：后者覆盖前者，最后会补上没提到的默认值。"""
    out = defaults()
    for layer in layers:
        if layer:
            out.update(sanitize(layer))
    return out


def effective(global_config: Optional[Dict[str, Any]] = None,
              process_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """运行时的有效配置 = 默认 ← 全局 ← 工序覆盖。"""
    return merge(global_config, process_config)
