# -*- coding: utf-8 -*-
"""取料位（引导目标点）：直接用坐标定义，坐标在投影坐标系里。"""
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models.database import TargetModel
from ..models.schemas import MessageResponse, TargetCreate, TargetResponse
from ..services.guidance_service import guidance_service
from .dependencies import get_db

router = APIRouter(prefix="/api/targets", tags=["targets"])


@router.get("/", response_model=List[TargetResponse])
def list_targets(db: Session = Depends(get_db)):
    return db.query(TargetModel).order_by(TargetModel.order_index, TargetModel.name).all()


@router.get("/{target_id}", response_model=TargetResponse)
def get_target(target_id: str, db: Session = Depends(get_db)):
    row = db.query(TargetModel).filter(TargetModel.id == target_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Target not found")
    return row


@router.post("/", response_model=TargetResponse)
def create_target(payload: TargetCreate, db: Session = Depends(get_db)):
    row = TargetModel(
        id=payload.id or str(uuid.uuid4()),
        name=payload.name.strip(),
        shape=payload.shape or "circle",
        x=payload.x, y=payload.y, r=payload.r, w=payload.w, h=payload.h,
        order_index=payload.order_index, color=payload.color or "#38bdf8",
        enabled=payload.enabled,
        created_at=payload.created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    guidance_service.refresh_idle_projector()
    return row


@router.put("/{target_id}", response_model=TargetResponse)
def update_target(target_id: str, payload: TargetCreate, db: Session = Depends(get_db)):
    row = db.query(TargetModel).filter(TargetModel.id == target_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Target not found")
    row.name = payload.name.strip()
    row.shape = payload.shape or "circle"
    row.x, row.y, row.r = payload.x, payload.y, payload.r
    row.w, row.h = payload.w, payload.h
    row.order_index = payload.order_index
    row.color = payload.color or "#38bdf8"
    row.enabled = payload.enabled
    db.commit()
    db.refresh(row)
    guidance_service.refresh_idle_projector()
    return row


@router.delete("/{target_id}", response_model=MessageResponse)
def delete_target(target_id: str, db: Session = Depends(get_db)):
    row = db.query(TargetModel).filter(TargetModel.id == target_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Target not found")
    db.delete(row)
    db.commit()
    guidance_service.refresh_idle_projector()
    return MessageResponse(message="Target deleted")
