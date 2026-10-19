# -*- coding: utf-8 -*-
"""Pydantic 请求/响应 Schema（Create 与 Response 分开定义，字段名 snake_case）。"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    message: str


# ── 模型 ────────────────────────────────────────────────────
class ModelCreate(BaseModel):
    id: Optional[str] = None
    name: str
    model_type: str = "hand"
    version: str = ""
    file_path: str = ""
    is_active: bool = False
    meta: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


class ModelResponse(BaseModel):
    id: str
    name: str
    model_type: str
    version: str
    file_path: str
    is_active: bool
    meta: Optional[Dict[str, Any]] = None
    created_at: str


# ── 摄像头 ──────────────────────────────────────────────────
class CameraCreate(BaseModel):
    id: Optional[str] = None
    name: str
    source_type: str = "local_device"
    source_url: str = "0"
    width: int = 1280
    height: int = 720
    note: Optional[str] = None
    created_at: Optional[str] = None


class CameraResponse(BaseModel):
    id: str
    name: str
    source_type: str
    source_url: str
    width: int
    height: int
    note: Optional[str] = None
    created_at: str


# ── 取料位（坐标） ──────────────────────────────────────────
class TargetCreate(BaseModel):
    id: Optional[str] = None
    name: str
    shape: str = "circle"
    x: float = 0.0
    y: float = 0.0
    r: float = 80.0
    w: float = 160.0
    h: float = 160.0
    order_index: int = 0
    color: str = "#38bdf8"
    enabled: bool = True
    created_at: Optional[str] = None


class TargetResponse(BaseModel):
    id: str
    name: str
    shape: str
    x: float
    y: float
    r: float
    w: float
    h: float
    order_index: int
    color: str
    enabled: bool
    created_at: str


# ── 工序 ────────────────────────────────────────────────────
class ProcessStepSchema(BaseModel):
    order: int
    target_id: str
    target_name: str = ""
    name: str = ""
    # 投影屏上引导工人的动作提示词（如「请拿取电容盒，放掌心停一下」），可留空
    instruction: str = ""
    # 本步骤的停留时长（秒）：手在该取料位停多久算「拿对」。留空则回落工序/全局 dwell_sec
    dwell_sec: Optional[float] = None


class ProcessCreate(BaseModel):
    id: Optional[str] = None
    name: str
    steps: List[ProcessStepSchema] = Field(default_factory=list)
    # 工序级引导参数覆盖（留空继承全局默认）；字段见 core/guide_config.py
    guide_config: Optional[Dict[str, Any]] = None
    # 投影开始/结束提示：启动/完成时在投影屏上显示，停留对应秒数
    start_hint: Optional[str] = None
    start_hint_sec: Optional[float] = 3.0
    end_hint: Optional[str] = None
    end_hint_sec: Optional[float] = 3.0
    note: Optional[str] = None
    created_at: Optional[str] = None


class ProcessResponse(BaseModel):
    id: str
    name: str
    steps: List[ProcessStepSchema]
    guide_config: Optional[Dict[str, Any]] = None
    start_hint: Optional[str] = None
    start_hint_sec: Optional[float] = 3.0
    end_hint: Optional[str] = None
    end_hint_sec: Optional[float] = 3.0
    note: Optional[str] = None
    created_at: str


# ── 标定 ────────────────────────────────────────────────────
class CalibrationRunRequest(BaseModel):
    camera_id: Optional[str] = None


class CalibrationResponse(BaseModel):
    id: str
    camera_id: Optional[str] = None
    proj_size: List[float]
    area: float
    quad_cam: List[List[float]]
    homography: List[List[float]]
    homography_inv: List[List[float]]
    debug_image_path: Optional[str] = None
    warning: str = ""
    is_current: bool
    created_at: str


# ── 引导配置 ────────────────────────────────────────────────
class GuideConfigUpdate(BaseModel):
    """全局引导配置的整体替换（字段与取值范围见 core/guide_config.py）。"""
    config: Dict[str, Any] = Field(default_factory=dict)


class GuideSettingsResponse(BaseModel):
    config: Dict[str, Any] = Field(default_factory=dict)        # 当前全局有效配置
    fields: List[Dict[str, Any]] = Field(default_factory=list)  # 字段元信息，供前端渲染表单


# ── 运行时 ──────────────────────────────────────────────────
class RuntimeStartRequest(BaseModel):
    process_id: str
    camera_id: Optional[str] = None


class ProjectorStateResponse(BaseModel):
    """投影页每帧拉取的状态。"""

    mode: str = "idle"                       # idle / guide / black / white / error
    proj_size: List[int] = Field(default_factory=lambda: [1024, 768])
    targets: List[Dict[str, Any]] = Field(default_factory=list)
    colors: Dict[str, Optional[str]] = Field(default_factory=dict)
    step_index: int = 0
    step_total: int = 0
    step_text: str = ""
    instruction: str = ""                     # 当前步的引导提示词（可留空）
    hand_xy: Optional[List[float]] = None
    progress: Optional[float] = None         # 手在目标位的停留进度 0..1，用于进度环
    flash: Optional[str] = None
    announce: Optional[Dict[str, Any]] = None  # 开始/结束提示 {text, tone}
    message: str = ""
    seq: int = 0
    # ── 引导动画参数（来自有效引导配置，管理人员可在「系统设置 / 工序编排」里调） ──
    pulse_enabled: bool = True
    pulse_period_ms: int = 1200
    ring_enabled: bool = True
    arrow_enabled: bool = False


class RuntimeStatusResponse(BaseModel):
    running: bool = False
    run_id: Optional[str] = None
    process_id: Optional[str] = None
    process_name: str = ""
    camera_id: Optional[str] = None
    step_index: int = 0
    step_total: int = 0
    step_text: str = ""
    cycle: int = 1                          # 当前进行到第几轮循环（从 1 开始）
    target_id: Optional[str] = None
    hand_detected: bool = False
    hand_xy: Optional[List[float]] = None
    progress: Optional[float] = None         # 手在当前目标位的停留进度 0..1
    colors: Dict[str, Optional[str]] = Field(default_factory=dict)
    last_event: Optional[str] = None
    wrong_count: int = 0
    calibrated: bool = False
    detector: str = ""
    message: str = ""
    fps: float = 0.0
    source_ok: bool = False       # 本次运行是否真的读到帧
    source_desc: str = ""         # 取流说明（分辨率 / 打不开的原因）


# ── 记录 ────────────────────────────────────────────────────
class EventResponse(BaseModel):
    id: str
    run_id: str
    step_index: int
    cycle: int = 1
    target_id: Optional[str] = None
    target_name: str
    result: str
    detail: str
    snapshot_path: Optional[str] = None
    snapshot_url: Optional[str] = None
    created_at: str


class RunResponse(BaseModel):
    id: str
    process_id: Optional[str] = None
    process_name: str
    camera_id: Optional[str] = None
    status: str
    total_steps: int
    done_steps: int
    wrong_count: int
    cycles: int = 0
    started_at: str
    ended_at: Optional[str] = None
    created_at: str


class RunDetailResponse(RunResponse):
    events: List[EventResponse] = Field(default_factory=list)
