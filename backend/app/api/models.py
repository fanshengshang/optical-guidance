# -*- coding: utf-8 -*-
"""AI 模型注册（本系统只需要一个：手部检测）。"""
import os
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models.database import ModelRegistryModel
from ..models.schemas import MessageResponse, ModelCreate, ModelResponse
from ..services.hand_service import DEFAULT_MODEL_REL, resolve_model_path
from .dependencies import get_db

router = APIRouter(prefix="/api/models", tags=["models"])


def _with_runtime(row: ModelRegistryModel) -> dict:
    resolved = resolve_model_path(row.file_path or DEFAULT_MODEL_REL)
    return {
        "id": row.id, "name": row.name, "model_type": row.model_type,
        "version": row.version, "file_path": row.file_path,
        "is_active": row.is_active, "meta": row.meta or {},
        "created_at": row.created_at,
        "resolved_path": resolved,
        "available": os.path.exists(resolved),
    }


@router.get("/")
def list_models(db: Session = Depends(get_db)):
    rows = db.query(ModelRegistryModel).order_by(ModelRegistryModel.created_at).all()
    return [_with_runtime(r) for r in rows]


@router.post("/", response_model=ModelResponse)
def create_model(payload: ModelCreate, db: Session = Depends(get_db)):
    row = ModelRegistryModel(
        id=payload.id or str(uuid.uuid4()),
        name=payload.name.strip(), model_type=payload.model_type or "hand",
        version=payload.version or "", file_path=payload.file_path or DEFAULT_MODEL_REL,
        is_active=payload.is_active, meta=payload.meta or {},
        created_at=payload.created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/{model_id}/activate", response_model=MessageResponse)
def activate_model(model_id: str, db: Session = Depends(get_db)):
    row = db.query(ModelRegistryModel).filter(ModelRegistryModel.id == model_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Model not found")
    for other in db.query(ModelRegistryModel).filter(
            ModelRegistryModel.model_type == row.model_type).all():
        other.is_active = (other.id == model_id)
    db.commit()
    return MessageResponse(message="Model activated")


@router.delete("/{model_id}", response_model=MessageResponse)
def delete_model(model_id: str, db: Session = Depends(get_db)):
    row = db.query(ModelRegistryModel).filter(ModelRegistryModel.id == model_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Model not found")
    db.delete(row)
    db.commit()
    return MessageResponse(message="Model deleted")
