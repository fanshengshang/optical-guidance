# -*- coding: utf-8 -*-
"""工序：把取料位编排成步骤序列（步骤存 JSON，不建子表）。"""
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core import guide_config as gc
from ..models.database import ProcessModel
from ..models.schemas import MessageResponse, ProcessCreate, ProcessResponse
from .dependencies import get_db

router = APIRouter(prefix="/api/processes", tags=["processes"])


def _steps_to_dict(payload: ProcessCreate) -> list:
    """按 order 排序并补齐 order 序号，存进 JSON 列。"""
    steps = sorted(payload.steps, key=lambda s: s.order)
    out = []
    for i, s in enumerate(steps):
        out.append({
            "order": i,
            "target_id": s.target_id,
            "target_name": s.target_name,
            "name": s.name,
            "instruction": getattr(s, "instruction", "") or "",
            "dwell_sec": getattr(s, "dwell_sec", None),
        })
    return out


@router.get("/", response_model=List[ProcessResponse])
def list_processes(db: Session = Depends(get_db)):
    return db.query(ProcessModel).order_by(ProcessModel.created_at).all()


@router.get("/{process_id}", response_model=ProcessResponse)
def get_process(process_id: str, db: Session = Depends(get_db)):
    row = db.query(ProcessModel).filter(ProcessModel.id == process_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Process not found")
    return row


@router.post("/", response_model=ProcessResponse)
def create_process(payload: ProcessCreate, db: Session = Depends(get_db)):
    row = ProcessModel(
        id=payload.id or str(uuid.uuid4()),
        name=payload.name.strip(),
        steps=_steps_to_dict(payload),
        guide_config=gc.sanitize(payload.guide_config) or None,
        start_hint=payload.start_hint,
        start_hint_sec=payload.start_hint_sec,
        end_hint=payload.end_hint,
        end_hint_sec=payload.end_hint_sec,
        note=payload.note,
        created_at=payload.created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{process_id}", response_model=ProcessResponse)
def update_process(process_id: str, payload: ProcessCreate, db: Session = Depends(get_db)):
    row = db.query(ProcessModel).filter(ProcessModel.id == process_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Process not found")
    row.name = payload.name.strip()
    row.steps = _steps_to_dict(payload)
    row.guide_config = gc.sanitize(payload.guide_config) or None
    row.start_hint = payload.start_hint
    row.start_hint_sec = payload.start_hint_sec
    row.end_hint = payload.end_hint
    row.end_hint_sec = payload.end_hint_sec
    row.note = payload.note
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{process_id}", response_model=MessageResponse)
def delete_process(process_id: str, db: Session = Depends(get_db)):
    row = db.query(ProcessModel).filter(ProcessModel.id == process_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Process not found")
    db.delete(row)
    db.commit()
    return MessageResponse(message="Process deleted")
