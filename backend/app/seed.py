# -*- coding: utf-8 -*-
"""开箱即用的初始数据：一个手部模型、一路摄像头、三个取料位、一条示例工序。

只在对应表为空时写入，不会覆盖用户自己配的数据。
"""
import uuid
from datetime import datetime

from . import config
from .models.database import (CameraModel, ModelRegistryModel, ProcessModel,
                              SessionLocal, TargetModel)
from .services.hand_service import DEFAULT_MODEL_REL

NOW = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731


def seed_if_empty():
    db = SessionLocal()
    try:
        created = []

        if db.query(ModelRegistryModel).count() == 0:
            db.add(ModelRegistryModel(
                id=str(uuid.uuid4()), name="手部检测模型", model_type="hand",
                version="mediapipe-1.1.0", file_path=DEFAULT_MODEL_REL,
                is_active=True,
                meta={"framework": "mediapipe", "task": "hand_landmarker",
                      "note": "本系统只需这一个模型"},
                created_at=NOW()))
            created.append("model: 手部检测模型")

        if db.query(CameraModel).count() == 0:
            db.add(CameraModel(
                id=str(uuid.uuid4()), name="工位摄像头",
                source_type="local_device", source_url="0",
                width=config.CAM_DEFAULT_WIDTH, height=config.CAM_DEFAULT_HEIGHT,
                note="本机 USB 摄像头，值为设备序号",
                created_at=NOW()))
            created.append("camera: 工位摄像头")

        target_ids = []
        if db.query(TargetModel).count() == 0:
            # 默认一排三个取料位，摆在投影坐标系（1024x768）的下半部
            layout = [("料盒 A", 220, 560), ("料盒 B", 512, 560), ("料盒 C", 804, 560)]
            for i, (name, x, y) in enumerate(layout):
                tid = str(uuid.uuid4())
                target_ids.append(tid)
                db.add(TargetModel(
                    id=tid, name=name, shape="circle", x=x, y=y, r=130,
                    w=200, h=200, order_index=i, color="#38bdf8",
                    enabled=True, created_at=NOW()))
            created.append("targets: 料盒 A/B/C")

        if db.query(ProcessModel).count() == 0:
            # session 是 autoflush=False，先把上面的取料位刷进事务再查，否则查到空
            db.flush()
            rows = db.query(TargetModel).order_by(TargetModel.order_index).limit(3).all()
            steps = [{"order": i, "target_id": t.id, "target_name": t.name,
                      "name": f"取{t.name[-1] if t.name else i + 1}"}
                     for i, t in enumerate(rows)]
            if steps:
                db.add(ProcessModel(
                    id=str(uuid.uuid4()), name="示例工序",
                    steps=steps, note="依次从三个料盒取料",
                    created_at=NOW()))
                created.append("process: 示例工序")

        db.commit()
        return created
    finally:
        db.close()
