# -*- coding: utf-8 -*-
"""数据模型层（ORM + 会话）。

本项目自身的约定：
- 主键 String(64) 存 uuid；时间列 String(32) 存 "YYYY-MM-DD HH:MM:SS"；
- 复杂结构用 JSON 列（工序步骤不建子表）；
- 外键统一带 ondelete 策略；SQLite 需要每连接显式打开外键与 WAL。
"""
from sqlalchemy import (JSON, Boolean, Column, Float, ForeignKey, Integer,
                        String, Text, create_engine, event, inspect, text)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from datetime import datetime

from ..config import DATABASE_URL


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False, "timeout": 10}}
    return {"pool_pre_ping": True, "pool_recycle": 3600, "pool_size": 10, "max_overflow": 20}


engine = create_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL))

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, connection_record):
        """SQLite 默认关闭外键约束，需每个连接显式开启。"""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── AI 模型注册（本系统只需要一个：手部检测） ────────────────
class ModelRegistryModel(Base):
    __tablename__ = "model_registry"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False, index=True)
    model_type = Column(String(32), nullable=False, default="hand")  # hand / other
    version = Column(String(64), nullable=False, default="")
    # 相对 MODEL_REGISTRY_DIR 的路径，如 hand-mediapipe/hand_landmarker.task
    file_path = Column(String(512), nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=False)
    meta = Column(JSON, default=dict)
    created_at = Column(String(32), nullable=False, default="")


class CameraModel(Base):
    __tablename__ = "cameras"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False, index=True)
    source_type = Column(String(32), nullable=False, default="local_device")  # local_device/rtsp/http
    source_url = Column(String(512), nullable=False, default="0")
    width = Column(Integer, nullable=False, default=1280)
    height = Column(Integer, nullable=False, default=720)
    note = Column(Text, nullable=True)
    created_at = Column(String(32), nullable=False, default="")


# ── 取料位：直接用坐标定义（不再靠模型识别料盒） ─────────────
class TargetModel(Base):
    """一个取料位 / 引导点。坐标在**投影坐标系**（PROJ_W x PROJ_H）里。"""

    __tablename__ = "targets"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False, index=True)
    shape = Column(String(16), nullable=False, default="circle")   # circle / rect
    x = Column(Float, nullable=False, default=0.0)
    y = Column(Float, nullable=False, default=0.0)
    r = Column(Float, nullable=False, default=80.0)                # circle 半径 / rect 用 w,h
    w = Column(Float, nullable=False, default=160.0)
    h = Column(Float, nullable=False, default=160.0)
    order_index = Column(Integer, nullable=False, default=0)
    color = Column(String(16), nullable=False, default="#38bdf8")  # 非激活时的描边色
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(String(32), nullable=False, default="")


# ── 工序：步骤存 JSON，不建子表 ──
class ProcessModel(Base):
    __tablename__ = "processes"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False, index=True)
    # [{"order":0,"target_id":"...","target_name":"...","name":"取垫片"}]
    steps = Column(JSON, default=list)
    # 工序级引导参数覆盖（留空即继承系统全局默认）；字段见 core/guide_config.py
    guide_config = Column(JSON, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(String(32), nullable=False, default="")


# ── 运行记录 ────────────────────────────────────────────────
class RunModel(Base):
    __tablename__ = "runs"

    id = Column(String(64), primary_key=True)
    process_id = Column(String(64), ForeignKey("processes.id", ondelete="SET NULL"), nullable=True)
    process_name = Column(String(128), nullable=False, default="")
    camera_id = Column(String(64), ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(16), nullable=False, default="running")  # running/done/aborted
    total_steps = Column(Integer, nullable=False, default=0)
    done_steps = Column(Integer, nullable=False, default=0)
    wrong_count = Column(Integer, nullable=False, default=0)
    started_at = Column(String(32), nullable=False, default="")
    ended_at = Column(String(32), nullable=True)
    created_at = Column(String(32), nullable=False, default="")

    events = relationship("EventModel", back_populates="run",
                          cascade="all, delete-orphan")


class EventModel(Base):
    """逐步事件：手在某个取料位上的判定结果。"""

    __tablename__ = "events"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False, default=0)
    target_id = Column(String(64), nullable=True)
    target_name = Column(String(128), nullable=False, default="")
    result = Column(String(16), nullable=False, default="ok")   # ok / wrong / advance
    detail = Column(String(255), nullable=False, default="")
    # 相对 DATA_DIR 的抓拍路径
    snapshot_path = Column(String(512), nullable=True)
    created_at = Column(String(32), nullable=False, default="")

    run = relationship("RunModel", back_populates="events")


# ── 标定 ────────────────────────────────────────────────────
class CalibrationModel(Base):
    __tablename__ = "calibrations"

    id = Column(String(64), primary_key=True)
    camera_id = Column(String(64), ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True)
    proj_size = Column(JSON, nullable=False, default=list)      # [1024, 768]
    # H: 投影坐标 -> 摄像头坐标；Hinv 反向
    homography = Column(JSON, nullable=False, default=list)
    homography_inv = Column(JSON, nullable=False, default=list)
    quad_cam = Column(JSON, nullable=False, default=list)
    area = Column(Float, nullable=False, default=0.0)
    debug_image_path = Column(String(512), nullable=True)
    # 标定质量的提醒（如"投影范围超出摄像头视野"）
    warning = Column(String(512), nullable=False, default="")
    is_current = Column(Boolean, nullable=False, default=True)
    created_at = Column(String(32), nullable=False, default="")


class SettingModel(Base):
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(JSON, nullable=True)


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns():
    """手写迁移：老库缺列时补上（不用 Alembic）。"""
    wanted = {
        "targets": [("w", "FLOAT DEFAULT 160"), ("h", "FLOAT DEFAULT 160"),
                    ("color", "VARCHAR(16) DEFAULT '#38bdf8'"),
                    ("enabled", "BOOLEAN DEFAULT 1")],
        "runs": [("wrong_count", "INTEGER DEFAULT 0"), ("done_steps", "INTEGER DEFAULT 0")],
        "processes": [("guide_config", "JSON")],
        "model_registry": [("meta", "JSON")],
        "calibrations": [("warning", "VARCHAR(512) DEFAULT ''")],
    }
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, columns in wanted.items():
            if table not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in columns:
                if name not in have:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}'))


def reconcile_stale_runs(session) -> int:
    """把历史遗留的 running 记录标记为 aborted。

    后端进程重启意味着上次的运行线程已不存在，这些记录不可能是真的 running
    （进程被强杀时 finalize 没走到）。返回被修正的记录数。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = session.query(RunModel).filter(
        RunModel.status == "running", RunModel.ended_at.is_(None)).all()
    for r in rows:
        r.status = "aborted"
        r.ended_at = now
    return len(rows)
