# -*- coding: utf-8 -*-
"""标定：执行一次对齐 + 读取历史/当前结果 + 标定自检图。"""
from typing import List

import cv2
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import config
from ..models.database import CalibrationModel, TargetModel
from ..models.schemas import CalibrationResponse, CalibrationRunRequest
from ..services import calibration_service
from ..services.guidance_service import guidance_service
from .dependencies import get_db

router = APIRouter(prefix="/api/calibration", tags=["calibration"])


@router.post("/run")
def run_calibration(payload: CalibrationRunRequest | None = None):
    camera_id = payload.camera_id if payload else None
    res = guidance_service.run_calibration(camera_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("reason", "标定失败"))
    return res


@router.get("/", response_model=List[CalibrationResponse])
def list_calibrations(db: Session = Depends(get_db)):
    return (db.query(CalibrationModel)
            .order_by(CalibrationModel.created_at.desc()).limit(50).all())


@router.get("/current", response_model=CalibrationResponse)
def current_calibration(db: Session = Depends(get_db)):
    row = (db.query(CalibrationModel)
           .filter(CalibrationModel.is_current == True)  # noqa: E712
           .order_by(CalibrationModel.created_at.desc()).first())
    if not row:
        raise HTTPException(status_code=404, detail="还没有标定记录")
    return row


def _stem_of(rel_path: str) -> str:
    """由 debug_image_path（…/calib_20261008_145718.jpg）取到主干，
    与 calibration_service._save_debug 写 _light/_dark/_diff 的命名约定对应。"""
    return rel_path[:-4] if rel_path.lower().endswith(".jpg") else rel_path


@router.get("/{calib_id}/overlay")
def calibration_overlay(calib_id: str, db: Session = Depends(get_db)):
    """标定自检图：真实画面（含实际照亮区）+ 检测到的投影区 + 各料位判定范围。

    直接把 PNG 返给 <img>，不走 JSON。
    """
    row = db.query(CalibrationModel).filter(CalibrationModel.id == calib_id).first()
    if row is None or not row.debug_image_path:
        raise HTTPException(status_code=404, detail="该标定没有过程图，无法生成自检图")
    stem = _stem_of(str(row.debug_image_path))
    dark = cv2.imread(str(config.data_path(stem + "_dark.jpg")), cv2.IMREAD_COLOR)
    diff = cv2.imread(str(config.data_path(stem + "_diff.jpg")), cv2.IMREAD_COLOR)
    if dark is None or diff is None:
        raise HTTPException(status_code=404,
                            detail="标定过程图已不在磁盘上，请重新标定一次")
    targets = [{"name": t.name, "shape": t.shape, "x": t.x, "y": t.y,
                "r": t.r, "w": t.w, "h": t.h}
               for t in (db.query(TargetModel)
                         .filter(TargetModel.enabled == True)  # noqa: E712
                         .order_by(TargetModel.order_index, TargetModel.name).all())]
    png = calibration_service.render_selfcheck(
        dark, diff, row.homography, row.quad_cam, targets, row.warning or "")
    if not png:
        raise HTTPException(status_code=500, detail="自检图生成失败")
    return Response(content=png, media_type="image/png")
