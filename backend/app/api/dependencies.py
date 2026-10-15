# -*- coding: utf-8 -*-
"""依赖注入。"""
from ..models.database import SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
