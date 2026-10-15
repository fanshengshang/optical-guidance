# -*- coding: utf-8 -*-
"""生产追溯：运行记录与逐步事件。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..models.database import EventModel, RunModel
from ..models.schemas import (EventResponse, MessageResponse, RunDetailResponse,
                              RunResponse)
from .dependencies import get_db

router = APIRouter(prefix="/api/records", tags=["records"])


def _snapshot_url(rel: Optional[str]) -> Optional[str]:
    return f"/static/{rel}" if rel else None


def _event_out(row: EventModel) -> EventResponse:
    return EventResponse(
        id=row.id, run_id=row.run_id, step_index=row.step_index,
        target_id=row.target_id, target_name=row.target_name, result=row.result,
        detail=row.detail, snapshot_path=row.snapshot_path,
        snapshot_url=_snapshot_url(row.snapshot_path), created_at=row.created_at)


@router.get("/runs", response_model=List[RunResponse])
def list_runs(limit: int = Query(100, ge=1, le=1000),
              status: Optional[str] = None,
              db: Session = Depends(get_db)):
    q = db.query(RunModel)
    if status:
        q = q.filter(RunModel.status == status)
    return q.order_by(RunModel.created_at.desc()).limit(limit).all()


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    row = db.query(RunModel).filter(RunModel.id == run_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    events = (db.query(EventModel).filter(EventModel.run_id == run_id)
              .order_by(EventModel.created_at, EventModel.step_index).all())
    return RunDetailResponse(
        id=row.id, process_id=row.process_id, process_name=row.process_name,
        camera_id=row.camera_id, status=row.status, total_steps=row.total_steps,
        done_steps=row.done_steps, wrong_count=row.wrong_count,
        started_at=row.started_at, ended_at=row.ended_at, created_at=row.created_at,
        events=[_event_out(e) for e in events])


@router.delete("/runs/{run_id}", response_model=MessageResponse)
def delete_run(run_id: str, db: Session = Depends(get_db)):
    row = db.query(RunModel).filter(RunModel.id == run_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    db.delete(row)
    db.commit()
    return MessageResponse(message="Run deleted")


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """总览统计：累计运行数、完成率、拿错次数。"""
    runs = db.query(RunModel).all()
    total = len(runs)
    done = sum(1 for r in runs if r.status == "done")
    wrong = sum(int(r.wrong_count or 0) for r in runs)
    events = db.query(EventModel).all()
    ok_events = sum(1 for e in events if e.result == "ok")
    wrong_events = sum(1 for e in events if e.result == "wrong")
    # 准确率只看「取料判定」事件（ok/wrong）；advance 是流程推进，不该稀释分母
    decisions = ok_events + wrong_events
    return {
        "total_runs": total,
        "done_runs": done,
        "running_runs": sum(1 for r in runs if r.status == "running"),
        "aborted_runs": sum(1 for r in runs if r.status == "aborted"),
        "total_wrong": wrong,
        "total_events": len(events),
        "wrong_events": wrong_events,
        "accuracy": round(ok_events / decisions * 100, 1) if decisions else 100.0,
    }
