# -*- coding: utf-8 -*-
"""系统设置：目前是「引导参数」一份全局配置。

读写走 services/settings_service（运行时也用它），存储复用通用 settings 表。
分层：全局默认（这份）← 工序覆盖（processes.guide_config），
合并与校验逻辑在 core/guide_config.py。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core import guide_config
from ..models.schemas import GuideConfigUpdate, GuideSettingsResponse
from ..services import settings_service
from .dependencies import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/guide", response_model=GuideSettingsResponse)
def get_guide_settings(db: Session = Depends(get_db)):
    return GuideSettingsResponse(config=settings_service.load_global_guide(db),
                                 fields=guide_config.field_meta())


@router.put("/guide", response_model=GuideSettingsResponse)
def put_guide_settings(payload: GuideConfigUpdate, db: Session = Depends(get_db)):
    """整体替换全局配置：只接受认识的键，类型 / 范围不对的丢弃或夹到边界。"""
    settings_service.save_global_guide(db, payload.config)
    return GuideSettingsResponse(config=settings_service.load_global_guide(db),
                                 fields=guide_config.field_meta())


@router.delete("/guide", response_model=GuideSettingsResponse)
def reset_guide_settings(db: Session = Depends(get_db)):
    """恢复内置默认：清掉存储的覆盖值。"""
    settings_service.reset_global_guide(db)
    return GuideSettingsResponse(config=settings_service.load_global_guide(db),
                                 fields=guide_config.field_meta())
