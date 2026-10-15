# -*- coding: utf-8 -*-
"""运行时：启停、状态、MJPEG 推流，以及投影页需要拉取的状态。"""
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from .. import config
from ..models.schemas import (ProjectorStateResponse, RuntimeStartRequest,
                              RuntimeStatusResponse)
from ..services.guidance_service import guidance_service
from ..services.projector_service import projector_service
from ..services.video_service import encode_jpeg, mjpeg_chunk, placeholder_frame

router = APIRouter(prefix="/api/runtime", tags=["runtime"])
projector_router = APIRouter(prefix="/api/projector", tags=["projector"])

MJPEG_MEDIA = "multipart/x-mixed-replace; boundary=frame"


@router.post("/start")
def start(payload: RuntimeStartRequest):
    res = guidance_service.start(payload.process_id, payload.camera_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("reason", "启动失败"))
    return res


@router.post("/stop")
def stop():
    return guidance_service.stop()


@router.get("/status", response_model=RuntimeStatusResponse)
def status():
    return guidance_service.status()


@router.get("/snapshot")
def snapshot():
    """取当前画面单帧 JPEG。"""
    jpeg = guidance_service.latest_jpeg() or encode_jpeg(placeholder_frame("无画面"))
    return Response(content=jpeg, media_type="image/jpeg")


def _runtime_frames():
    """运行中的推流。停止后必须自己收尾，否则连接会挂着一直重发最后一帧。"""
    while guidance_service.running:
        jpeg = guidance_service.latest_jpeg()
        if jpeg is not None:
            yield mjpeg_chunk(jpeg)
        time.sleep(config.STREAM_INTERVAL_SEC)


@router.get("/stream")
def stream(camera_id: str | None = Query(None)):
    """运行中推带标注的画面；未运行时退化为纯画面预览。"""
    gen = (_runtime_frames() if guidance_service.running
           else guidance_service.preview_stream(camera_id))
    return StreamingResponse(gen, media_type=MJPEG_MEDIA)


# ── 投影页 ──────────────────────────────────────────────────
@projector_router.get("/state", response_model=ProjectorStateResponse)
def projector_state():
    return projector_service.snapshot()
