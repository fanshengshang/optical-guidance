# -*- coding: utf-8 -*-
"""摄像头配置 + 本地设备扫描。"""
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..models.database import CameraModel
from ..models.schemas import CameraCreate, CameraResponse, MessageResponse
from ..services.calibration_service import detect_cameras
from ..services.guidance_service import guidance_service
from .dependencies import get_db

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("/", response_model=List[CameraResponse])
def list_cameras(db: Session = Depends(get_db)):
    return db.query(CameraModel).order_by(CameraModel.created_at).all()


@router.get("/scan")
def scan_local_devices(max_index: int = Query(6, ge=1, le=16)):
    """扫描本机可用的本地摄像头（会短暂占用设备，运行中拒绝调用）。"""
    if guidance_service.running:
        raise HTTPException(status_code=409, detail="运行中无法扫描摄像头，请先停止")
    return {"devices": detect_cameras(max_index)}


@router.get("/{camera_id}", response_model=CameraResponse)
def get_camera(camera_id: str, db: Session = Depends(get_db)):
    row = db.query(CameraModel).filter(CameraModel.id == camera_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    return row


@router.post("/", response_model=CameraResponse)
def create_camera(payload: CameraCreate, db: Session = Depends(get_db)):
    row = CameraModel(
        id=payload.id or str(uuid.uuid4()),
        name=payload.name.strip(),
        source_type=payload.source_type or "local_device",
        source_url=payload.source_url or "0",
        width=payload.width, height=payload.height, note=payload.note,
        created_at=payload.created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{camera_id}", response_model=CameraResponse)
def update_camera(camera_id: str, payload: CameraCreate, db: Session = Depends(get_db)):
    row = db.query(CameraModel).filter(CameraModel.id == camera_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    row.name = payload.name.strip()
    row.source_type = payload.source_type or "local_device"
    row.source_url = payload.source_url or "0"
    row.width, row.height = payload.width, payload.height
    row.note = payload.note
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{camera_id}", response_model=MessageResponse)
def delete_camera(camera_id: str, db: Session = Depends(get_db)):
    row = db.query(CameraModel).filter(CameraModel.id == camera_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    db.delete(row)
    db.commit()
    return MessageResponse(message="Camera deleted")
