# -*- coding: utf-8 -*-
"""光学引导系统 · 后端入口。

启动：cd backend && ..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8002
"""
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, seed
from .core import guide_config
from .api import calibration as calibration_api
from .api import cameras as cameras_api
from .api import models as models_api
from .api import processes as processes_api
from .api import records as records_api
from .api import runtime as runtime_api
from .api import settings as settings_api
from .api import targets as targets_api
from .models.database import init_db, SessionLocal, reconcile_stale_runs
from .services.guidance_service import guidance_service
from .services.video_service import video_manager

# 日志同时落一份 UTF-8 文件，规避 Windows 控制台 GBK 乱码
LOG_FILE = Path(config.BASE_DIR) / "backend.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("optical-guidance")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_data_dirs()
    init_db()
    created = seed.seed_if_empty()
    if created:
        logger.info("[App] 初始化数据: %s", ", ".join(created))
    # 对账：把上次进程退出时没来得及收尾的 running 记录标记为 aborted
    db = SessionLocal()
    try:
        fixed = reconcile_stale_runs(db)
        if fixed:
            db.commit()
            logger.info("[App] 对账：%d 条遗留 running 记录已标记为 aborted", fixed)
    finally:
        db.close()
    guidance_service.load_calibration()
    guidance_service.refresh_idle_projector("等待启动")
    logger.info("[App] Database initialized; DATA_DIR=%s", config.DATA_DIR)
    yield
    guidance_service.shutdown()
    video_manager.close_all()
    logger.info("[App] Shutting down")


app = FastAPI(title="光学引导系统",
              description="摄像头看手 + 投影仪投光的作业事前引导系统",
              version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_ROOT = Path(config.DATA_DIR)
DATA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(DATA_ROOT)), name="static")

app.include_router(cameras_api.router)
app.include_router(models_api.router)
app.include_router(targets_api.router)
app.include_router(processes_api.router)
app.include_router(calibration_api.router)
app.include_router(runtime_api.router)
app.include_router(runtime_api.projector_router)
app.include_router(records_api.router)
app.include_router(settings_api.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "optical-guidance",
            "data_dir": config.DATA_DIR, "proj_size": [config.PROJ_W, config.PROJ_H]}


@app.get("/api/config")
def public_config():
    return {
        "proj_size": [config.PROJ_W, config.PROJ_H],
        "camera_default": [config.CAM_DEFAULT_WIDTH, config.CAM_DEFAULT_HEIGHT],
        "stream_interval": config.STREAM_INTERVAL_SEC,
        "hand_dwell_sec": guide_config.DEFAULT["dwell_sec"],
    }


@app.exception_handler(Exception)
async def unhandled(_, exc: Exception):        # pragma: no cover
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})
