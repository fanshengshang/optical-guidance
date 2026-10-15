# -*- coding: utf-8 -*-
"""光学引导系统 · 全局配置。

本项目自身的约定：
- 数据落在项目根的 optical-guidance-data/，一级目录是**固定契约**；
- 库里只存相对 DATA_DIR 的路径；
- 业务代码不手写目录字符串，一律走 data_path() / data_relative()。
"""
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]        # backend/
PROJECT_DIR = BASE_DIR.parent                          # 项目根


def _load_local_env() -> None:
    """.env 里本地覆盖（只在环境变量未设置时生效）。"""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()

# ── 服务 ────────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
# 后端端口（与其它本地服务错开）
PORT = int(os.getenv("PORT", "8002"))
RELOAD = os.getenv("RELOAD", "true").lower() == "true"

ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5174,http://127.0.0.1:5174"
    ).split(",") if o.strip()
]

# ── 数据库 ──────────────────────────────────────────────────
DB_DRIVER = os.getenv("DB_DRIVER", "sqlite")
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(BASE_DIR / 'optical-guidance.db').as_posix()}"

# AI 模型仓库（一个模型一个目录）
MODEL_REGISTRY_DIR = BASE_DIR / "model_registry"

# ── 数据目录 ────────────────────────────────────────────────
# DATA_DIR 下的一级目录是**固定契约**：
#   <DATA_DIR>/
#   ├── snapshots/      判定瞬间抓拍   <YYYYMMDD>/<run_id>_step<NN>_<ok|wrong>.jpg
#   ├── recordings/     工序录像       <YYYYMMDD>/<run_id>.avi
#   └── diagnostics/    标定/诊断调试图 <YYYYMM>/calib_<时间戳>.jpg
# 库里存的一律是相对 DATA_DIR 的路径（如 snapshots/20261008/xxx.jpg），
# 所以搬动 DATA_DIR 本身不用改数据；但改一级目录名必须同步迁移文件与库内路径。
DEFAULT_DATA_DIR = PROJECT_DIR / "optical-guidance-data"
DATA_DIR = str(Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR)).resolve())

DATA_SUBDIRS = ("snapshots", "recordings", "diagnostics")


class DataPathError(ValueError):
    """给出的路径越出了 DATA_DIR。"""


_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def _safe_part(part) -> str:
    piece = str(part).replace("\\", "/")
    if piece.startswith("/") or _DRIVE_PREFIX.match(piece) or os.path.isabs(str(part)):
        raise DataPathError(f"绝对路径不能拼进数据目录: {part!r}")
    if ".." in piece.split("/"):
        raise DataPathError(f"路径不能含 `..` 片段: {part!r}")
    return piece


def data_path(*parts: str) -> Path:
    """拼出 DATA_DIR 下的绝对路径。拒绝绝对路径与 `..`。"""
    root = Path(DATA_DIR)
    if not parts:
        return root
    return root.joinpath(*[_safe_part(p) for p in parts])


def data_relative(path) -> str:
    """把 DATA_DIR 下的绝对路径转回库内使用的相对路径（正斜杠）。"""
    root = Path(DATA_DIR).resolve()
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise DataPathError(f"路径不在数据目录内: {path!r}") from exc


def ensure_data_dirs() -> None:
    for name in DATA_SUBDIRS:
        data_path(name).mkdir(parents=True, exist_ok=True)


# ── 投影坐标系 ──────────────────────────────────────────────
# 投影仪分辨率（料盒/取料位都定义在这个坐标系里）
PROJ_W = int(os.getenv("PROJ_W", "1024"))
PROJ_H = int(os.getenv("PROJ_H", "768"))

# ── 摄像头默认参数 ──────────────────────────────────────────
CAM_DEFAULT_WIDTH = int(os.getenv("CAMERA_FRAME_WIDTH", "1280"))
CAM_DEFAULT_HEIGHT = int(os.getenv("CAMERA_FRAME_HEIGHT", "720"))
# 降级候选顺序：本机实测 1920x1080 能开能读但全黑，所以把它排到最后，
# 优先试 1024x768 / 960x540 / 800x600 / 640x480 这些确实出画面的档位。
CAM_FALLBACK_RESOLUTIONS = ((1280, 720), (1024, 768), (960, 540),
                            (800, 600), (640, 480), (1920, 1080))

# ── 引导判定 ────────────────────────────────────────────────
HAND_DWELL_SEC = float(os.getenv("HAND_DWELL_SEC", "0.12"))
CALIB_SETTLE_SEC = float(os.getenv("CALIB_SETTLE_SEC", "0.45"))
CALIB_SAMPLES = int(os.getenv("CALIB_SAMPLES", "5"))
# 推流限速（秒/帧）
STREAM_INTERVAL_SEC = float(os.getenv("RUNTIME_STREAM_INTERVAL_SECONDS", "0.05"))
