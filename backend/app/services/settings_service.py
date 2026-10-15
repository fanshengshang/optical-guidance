# -*- coding: utf-8 -*-
"""系统设置读写（目前只有「引导参数」一份全局配置）。

放 service 层，让 api/settings.py 与运行时 guidance_service 共用同一套读写，
避免两处各写一份。存储复用通用 settings 表（key-value JSON）。
"""
from ..core import guide_config


GLOBAL_KEY = "guide_config"


def load_global_guide(db) -> dict:
    """全局有效引导配置 = 内置默认 ← settings 表里已存的值。"""
    from ..models.database import SettingModel
    row = db.query(SettingModel).filter(SettingModel.key == GLOBAL_KEY).first()
    stored = row.value if row and isinstance(row.value, dict) else {}
    return guide_config.merge(stored)


def save_global_guide(db, config: dict) -> None:
    from ..models.database import SettingModel
    clean = guide_config.sanitize(config)
    row = db.query(SettingModel).filter(SettingModel.key == GLOBAL_KEY).first()
    if row is None:
        db.add(SettingModel(key=GLOBAL_KEY, value=clean))
    else:
        row.value = clean
    db.commit()


def reset_global_guide(db) -> None:
    from ..models.database import SettingModel
    db.query(SettingModel).filter(SettingModel.key == GLOBAL_KEY).delete()
    db.commit()
