# -*- coding: utf-8 -*-
"""运行时编排：读帧 -> 手部检测 -> 投影坐标换算 -> 引擎判定 -> 投影/记录。

一个后台线程持有摄像头；投影页与前端预览都从这里的共享状态取数据，
避免多个读者抢同一个 VideoCapture。
"""
import math
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from .. import config
from ..core import guide_config
from ..core.engine import GuidanceEngine, Step, Target
from ..core.geometry import cam_to_proj, proj_to_cam
from ..models.database import (CalibrationModel, CameraModel, EventModel,
                               ProcessModel, RunModel, SessionLocal, TargetModel)
from . import recorder, settings_service, video_service
from .hand_service import build_detector
from .projector_service import projector_service
from .video_service import encode_jpeg, placeholder_frame

# 语义：hint = 当前该取（蓝），green = 拿对（绿），red = 拿错（红），warn = 误触（橙）
COLOR_BGR = {"green": (74, 222, 128), "red": (68, 68, 239),
             "hint": (246, 130, 59), "warn": (120, 180, 220), None: (160, 160, 160)}

# 连续读不到帧多久就判定「取流异常」（不再是"运行中"的假象）
NO_FRAME_TIMEOUT_SEC = 2.0
NO_FRAME_MESSAGE = "摄像头读不到帧（可能被其他程序占用），请停止后重试"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class GuidanceService:
    def __init__(self):
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._stop_reason: Optional[str] = None

        self._source = None
        self._detector = None
        self._run_token = None
        self._engine: Optional[GuidanceEngine] = None
        self._guide: Dict[str, Any] = {}     # 本轮生效的引导配置（投影端也要读）
        self._run_id: Optional[str] = None
        self._process_id: Optional[str] = None
        self._process_name = ""
        self._camera_id: Optional[str] = None
        # 投影开始/结束提示（本次运行沿用）
        self._start_hint = ""
        self._start_hint_sec = 3.0
        self._end_hint = ""
        self._end_hint_sec = 3.0

        self._H = None
        self._Hinv = None
        self._calibrated = False
        self._calib_warning = ""      # 当前标定的可信性警告（非空即不可信）

        self._latest_jpeg: Optional[bytes] = None
        self._latest_raw: Optional[np.ndarray] = None
        self._seq = 0
        self._fps = 0.0
        self._message = "未启动"
        self._source_ok = False
        self._source_desc = ""
        self._no_frame_since: Optional[float] = None
        self._hand_detected = False
        self._hand_xy = None
        self._hand_cam_last = None
        self._colors: Dict[str, Optional[str]] = {}
        self._last_event: Optional[str] = None
        self._hand_target: Optional[str] = None
        self._progress: Optional[float] = None   # 手在当前目标位的停留进度 0..1
        self._wrong_count = 0
        self._cycle = 1                          # 当前循环轮次（从 1 开始）
        self._cycle_wrap = False                 # 一轮完成后的过渡标志（等手离开所有料位）

    # ─────────────── 查询 ───────────────
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def current_calibration(self) -> Optional[CalibrationModel]:
        db = SessionLocal()
        try:
            return (db.query(CalibrationModel)
                    .filter(CalibrationModel.is_current == True)  # noqa: E712
                    .order_by(CalibrationModel.created_at.desc()).first())
        finally:
            db.close()

    def load_calibration(self) -> bool:
        row = self.current_calibration()
        if not row or not row.homography_inv:
            self._H = self._Hinv = None
            self._calibrated = False
            self._calib_warning = ""
            return False
        self._H = np.asarray(row.homography, dtype=np.float64)
        self._Hinv = np.asarray(row.homography_inv, dtype=np.float64)
        self._calibrated = True
        self._calib_warning = row.warning or ""
        return True

    def _targets_from_db(self, only_enabled: bool = True) -> List[Target]:
        db = SessionLocal()
        try:
            q = db.query(TargetModel)
            if only_enabled:
                q = q.filter(TargetModel.enabled == True)  # noqa: E712
            rows = q.order_by(TargetModel.order_index, TargetModel.name).all()
            return [Target(id=t.id, name=t.name, x=t.x, y=t.y, r=t.r,
                           shape=t.shape, w=t.w, h=t.h, color=t.color) for t in rows]
        finally:
            db.close()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            eng = self._engine
            return {
                "running": self.running,
                "run_id": self._run_id,
                "process_id": self._process_id,
                "process_name": self._process_name,
                "camera_id": self._camera_id,
                "step_index": eng.step_index if eng else 0,
                "step_total": eng.step_total if eng else 0,
                "step_text": eng.step_text() if eng else "",
                "cycle": self._cycle,
                "target_id": eng.target_id if eng else None,
                "hand_detected": self._hand_detected,
                "hand_xy": list(self._hand_xy) if self._hand_xy else None,
                "progress": self._progress,
                "colors": dict(self._colors),
                "last_event": self._last_event,
                "wrong_count": self._wrong_count,
                "calibrated": self._calibrated,
                "detector": self._detector.name if self._detector else "",
                "message": self._message,
                "fps": round(self._fps, 1),
                "source_ok": self._source_ok,
                "source_desc": self._source_desc,
            }

    def latest_jpeg(self) -> Optional[bytes]:
        return self._latest_jpeg

    # ─────────────── 空闲预览 ───────────────
    def refresh_idle_projector(self, message: str = "等待启动"):
        """未运行时也让投影页显示取料位轮廓，方便摆位对齐。"""
        targets = self._targets_from_db()
        # 空闲态没有「工序覆盖」，动画参数取全局配置，保证预览与实际一致
        guide = self._guide
        if not guide:
            db = SessionLocal()
            try:
                guide = settings_service.load_global_guide(db)
            except Exception:
                guide = None
            finally:
                db.close()
        projector_service.update_guide(
            targets=[t.to_dict() for t in targets],
            colors={}, step_index=0, step_total=0,
            step_text="", hand_xy=None, progress=None, flash=None,
            message=message, guide=guide)

    def preview_stream(self, camera_id: Optional[str]):
        """未启动运行时的纯画面预览（不跑模型）。"""
        db = SessionLocal()
        try:
            cam = None
            if camera_id:
                cam = db.query(CameraModel).filter(CameraModel.id == camera_id).first()
            if cam is None:
                cam = db.query(CameraModel).order_by(CameraModel.created_at).first()
            cam_info = None if cam is None else (cam.id, cam.source_type,
                                                 cam.source_url, cam.width, cam.height)
        finally:
            db.close()

        if cam_info is None:
            yield video_service.mjpeg_chunk(encode_jpeg(
                placeholder_frame("未配置摄像头")))
            return
        # 每轮都重新 open 一遍：运行停止时会把摄像头释放掉，
        # 这里能自动重新打开，空闲预览不会一直卡在「无画面」。
        retry_delay = 0.5          # open 失败时的退避起点，成功即复位
        while True:
            started = time.monotonic()
            src = video_service.video_manager.open(*cam_info)
            if not src.is_open:
                jpeg = encode_jpeg(placeholder_frame(src.description or "摄像头打不开"))
            else:
                retry_delay = 0.5
                frame = src.read()
                if frame is None:
                    # 相机帧率低于推流帧率时会有空挡，用 1 秒内的最近帧顶上；
                    # 超过 1 秒没新帧就老实显示占位，不糊弄成冻结画面。
                    frame = src.latest(max_age=1.0)
                jpeg = (encode_jpeg(frame) if frame is not None
                        else encode_jpeg(placeholder_frame("摄像头无画面")))
            if jpeg:
                yield video_service.mjpeg_chunk(jpeg)
            if not src.is_open:
                # 打不开就指数退避（0.5s → 2s 封顶），别每 50ms 重造一次 DSHOW 句柄
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 2.0)
            else:
                time.sleep(max(0.005, config.STREAM_INTERVAL_SEC
                               - (time.monotonic() - started)))

    # ─────────────── 标定 ───────────────
    def run_calibration(self, camera_id: Optional[str] = None) -> dict:
        db = SessionLocal()
        try:
            cam = None
            if camera_id:
                cam = db.query(CameraModel).filter(CameraModel.id == camera_id).first()
            if cam is None:
                cam = db.query(CameraModel).order_by(CameraModel.created_at).first()
            if cam is None:
                return {"ok": False, "reason": "还没配置摄像头"}

            # 运行中先用运行时的摄像头；否则临时开一路
            src = video_service.video_manager.get(cam.id)
            temp = None
            if src is None or not src.is_open:
                temp = video_service.VideoSource(cam.source_type, cam.source_url,
                                                 cam.width, cam.height)
                src = temp
            try:
                # cv2.imwrite 不会自动建目录，先自己建好
                diag_dir = config.data_path("diagnostics",
                                            datetime.now().strftime("%Y%m"))
                diag_dir.mkdir(parents=True, exist_ok=True)
                debug_abs = str(diag_dir / f"calib_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                res = calibration_service_calibrate(src, debug_abs, cam.id)
            finally:
                if temp is not None:
                    temp.release()
            return res
        finally:
            db.close()

    # ─────────────── 启动 / 停止 ───────────────
    def start(self, process_id: str, camera_id: Optional[str] = None) -> dict:
        with self._lock:
            if self.running:
                if self._stop_evt.is_set():
                    return {"ok": False, "reason": "上一次运行正在停止，请稍候再试"}
                return {"ok": False, "reason": "已经在运行中，请先停止"}

            db = SessionLocal()
            try:
                proc = db.query(ProcessModel).filter(ProcessModel.id == process_id).first()
                if proc is None:
                    return {"ok": False, "reason": "工序不存在"}
                cam = None
                if camera_id:
                    cam = db.query(CameraModel).filter(CameraModel.id == camera_id).first()
                if cam is None:
                    cam = db.query(CameraModel).order_by(CameraModel.created_at).first()
                if cam is None:
                    return {"ok": False, "reason": "还没配置摄像头"}

                targets = self._targets_from_db()
                tmap = {t.id: t for t in targets}
                steps = []
                for i, s in enumerate(proc.steps or []):
                    tid = s.get("target_id") if isinstance(s, dict) else None
                    if not tid or tid not in tmap:
                        continue
                    steps.append(Step(len(steps), tid,
                                      s.get("name") or tmap[tid].name,
                                      s.get("target_name") or tmap[tid].name,
                                      s.get("instruction") or "",
                                      s.get("dwell_sec")))
                if not steps:
                    return {"ok": False, "reason": "工序里没有可用的取料位步骤"}

                # 标定可信性检查：已有标定但带 warning（不可信）时直接拒绝启动，
                # 否则工人会拿坏标定白干（「取完 A 不推进」正是旧标定被静默沿用导致）。
                self.load_calibration()
                if self._calibrated and self._calib_warning:
                    return {"ok": False,
                            "reason": ("当前标定不可信，请先到「投影标定」页重新标定："
                                       + self._calib_warning)}

                model_rel = DEFAULT_MODEL_REL_FROM_DB(db)
                # 检测器由运行线程自己建（见 _loop）：本机 mediapipe 的 close()
                # 跨线程会长时间阻塞，所以这里只置空、不在这里建。
                self._detector = None
                # 本轮有效引导配置 = 内置默认 ← 全局设置 ← 工序覆盖，
                # 判定阈值与动画参数都从这里来（不写死在代码里）。
                gconf = guide_config.effective(
                    settings_service.load_global_guide(db), proc.guide_config)
                self._guide = gconf
                self._engine = GuidanceEngine(
                    targets, steps, dwell=gconf["dwell_sec"],
                    detect_wrong_order=gconf["detect_wrong_order"],
                    detect_mis_touch=gconf["detect_mis_touch"],
                    mis_touch_sec=gconf["mis_touch_sec"],
                    hold_red_until_correct=gconf["hold_red_until_correct"])
                self._process_id = proc.id
                self._process_name = proc.name
                self._camera_id = cam.id
                self._start_hint = (proc.start_hint or "").strip()
                self._start_hint_sec = float(proc.start_hint_sec or 3.0)
                self._end_hint = (proc.end_hint or "").strip()
                self._end_hint_sec = float(proc.end_hint_sec or 3.0)
                self._wrong_count = 0
                self._cycle = 1
                self._cycle_wrap = False
                self._last_event = None
                # 上一轮的 fps/画面不能带到新一轮（否则启动瞬间显示陈旧数据）
                self._fps = 0.0
                self._latest_jpeg = None
                self._hand_detected = False
                self._hand_xy = None
                self._colors = {}
                self._progress = None
                self._message = "启动中…"

                run = RunModel(
                    id=str(uuid.uuid4()), process_id=proc.id, process_name=proc.name,
                    camera_id=cam.id, status="running", total_steps=len(steps),
                    started_at=_now(), created_at=_now())
                db.add(run)
                db.commit()
                self._run_id = run.id

                source = video_service.video_manager.open(
                    cam.id, cam.source_type, cam.source_url, cam.width, cam.height)
                if not source.is_open:
                    run.status = "aborted"
                    run.ended_at = _now()
                    db.commit()
                    return {"ok": False, "reason": source.description or "摄像头打开失败"}
                self._source = source
                self._source_desc = source.description
                self._source_ok = True
                self._no_frame_since = None
            finally:
                db.close()

            # 没标定过就先自动标定（设备位置可能每次都变）
            if not self._calibrated:
                self._message = "未标定，正在自动标定…"
                res = self.run_calibration(self._camera_id)
                if not res.get("ok"):
                    self._message = f"自动标定失败：{res.get('reason')}"
                else:
                    self.load_calibration()

            self._stop_evt.clear()
            self._stop_reason = None
            token = object()
            self._run_token = token
            self._message = "加载手部检测模型…"
            self._thread = threading.Thread(target=self._loop, args=(token, model_rel),
                                            name="guidance-runtime", daemon=True)
            self._thread.start()
            return {"ok": True, "run_id": self._run_id, "calibrated": self._calibrated}

    def stop(self, reason: str = "手动停止") -> dict:
        """停止本次运行。**幂等**：没在跑时也返回成功，并把资源收干净。"""
        with self._lock:
            th = self._thread
            if th is not None and th.is_alive():
                self._stop_reason = reason
                self._stop_evt.set()
        if th is not None:
            th.join(timeout=5)
        thread_stuck = th is not None and th.is_alive()
        with self._lock:
            # 线程正常退出时已经自己结过账；这里只兜住「线程没来得及收尾」的情况
            if self._run_id:
                self._finalize_run("stopped", reason)
            self._thread = None
            self._message = "运行线程未及时退出" if thread_stuck else "已停止"
            projector_service.set_idle("已停止")
            self._colors = {}
            self._hand_detected = False
            self._hand_xy = None
            self._progress = None
        # 线程还活着时不能释放摄像头（它可能正卡在阻塞读里）
        if not thread_stuck:
            self._teardown()
        return {"ok": True}

    # ─────────────── 主循环 ───────────────
    def _wait_announce(self, text: str, tone: str, sec: float):
        """显示一段开始/结束提示并停留 sec 秒，期间可被 stop_evt 立即打断。"""
        if not text or sec <= 0:
            return
        projector_service.set_announce(text, tone)
        deadline = time.monotonic() + sec
        while not self._stop_evt.is_set() and time.monotonic() < deadline:
            time.sleep(0.05)

    def _loop(self, token, model_rel):
        # 检测器按模型路径进程内缓存（见 hand_service.build_detector），
        # 这里拿到的是同一个实例，跨轮复用、不在运行结束关它。
        detector = build_detector(model_rel)
        with self._lock:
            if self._run_token is token:
                self._detector = detector
                self._message = "运行中"
        try:
            # 启动提示：先显示开始文案，再进入判定循环
            self._wait_announce(self._start_hint, "start", self._start_hint_sec)
            if self._stop_evt.is_set():
                return

            last_ts = time.monotonic()
            frames = 0
            fps_t0 = time.monotonic()
            # 检测跳帧：每 N 帧才跑一次检测，中间帧沿用上次的手位置
            detect_every = max(1, int(self._guide.get("detect_every_n_frames", 1) or 1))
            frame_no = 0
            while not self._stop_evt.is_set():
                now = time.monotonic()
                frame = self._source.read() if self._source is not None else None
                if frame is None:
                    # 读不到帧不能只 continue —— 否则 status 一直报「运行中 / fps=0」，
                    # 外面完全看不出是相机被占了还是程序卡了。
                    if self._no_frame_since is None:
                        self._no_frame_since = now
                    elif now - self._no_frame_since >= NO_FRAME_TIMEOUT_SEC:
                        with self._lock:
                            was_ok = self._source_ok
                            self._source_ok = False
                            self._message = NO_FRAME_MESSAGE
                        # 只在第一次掉线时切一次投影，别每 50ms 反复 bump
                        if was_ok:
                            projector_service.set_stale(NO_FRAME_MESSAGE)
                    time.sleep(0.05)
                    continue
                if not self._source_ok:
                    with self._lock:
                        self._source_ok = True
                        self._message = "运行中"
                self._no_frame_since = None

                hand_cam = None
                hand_proj = None
                # 跳帧：只在第 0、N、2N… 帧跑检测，其余帧沿用上一帧的手位置
                if frame_no % detect_every == 0:
                    try:
                        hand_cam = detector.detect(frame)
                    except Exception:
                        hand_cam = None
                else:
                    hand_cam = self._hand_cam_last
                if hand_cam is not None and self._Hinv is not None:
                    hand_proj = cam_to_proj(hand_cam, self._Hinv)
                self._hand_cam_last = hand_cam

                eng = self._engine
                if eng is not None and self._cycle_wrap:
                    # 轮次间过渡：等手离开所有料位再正式进入下一轮，
                    # 否则手还停在最后一格会被新一轮误判成「顺序错/拿错」。
                    if hand_proj is None or eng.target_at(hand_proj[0], hand_proj[1]) is None:
                        eng.reset()
                        self._cycle_wrap = False
                    with self._lock:
                        self._hand_xy = hand_proj
                        self._hand_detected = hand_cam is not None
                        self._hand_target = None
                        self._progress = None
                    projector_service.update_guide(
                        targets=[t.to_dict() for t in eng.targets.values()],
                        colors={}, step_index=0, step_total=eng.step_total,
                        step_text=f"第 {self._cycle - 1} 轮完成 · 请开始第 {self._cycle} 轮",
                        instruction="", hand_xy=hand_proj, progress=None,
                        flash=None, message=self._message, guide=self._guide)
                    annotated = self._annotate(frame, hand_cam, hand_proj)
                    jpeg = encode_jpeg(annotated)
                    if jpeg:
                        self._latest_jpeg = jpeg
                        self._seq += 1
                    frame_no += 1
                    time.sleep(0.005)
                    continue
                if eng is not None:
                    colors, hand_target, event, progress = eng.update(hand_proj)
                else:
                    colors, hand_target, event, progress = {}, None, None, None

                record = None
                with self._lock:
                    self._colors = colors
                    self._hand_detected = hand_cam is not None
                    self._hand_xy = hand_proj
                    self._hand_target = hand_target
                    self._progress = progress
                    if event:
                        kind, tid, event_step = event
                        tname = eng.targets[tid].name if (tid and tid in eng.targets) else ""
                        self._last_event = f"{_event_label(kind)} @ {tname or '-'}"
                        if kind in ("wrong", "wrong_order"):
                            self._wrong_count += 1
                        # 只提取快照；全帧落盘 + DB 事务放锁外，别堵 status 轮询
                        record = (kind, tid, tname, event_step, frame, self._run_id, self._cycle)
                if record is not None:
                    self._record_event(*record)

                if eng is not None:
                    flash = ("green" if event and event[0] in ("ok", "advance")
                             else ("red" if event and event[0] in ("wrong", "wrong_order")
                                   else ("warn" if event and event[0] == "mis_touch" else None)))
                    projector_service.update_guide(
                        targets=[t.to_dict() for t in eng.targets.values()],
                        colors=colors, step_index=eng.step_index, step_total=eng.step_total,
                        step_text=eng.step_text(), instruction=eng.step_instruction(),
                        hand_xy=hand_proj, progress=progress,
                        flash=flash, message=self._message, guide=self._guide)

                annotated = self._annotate(frame, hand_cam, hand_proj)
                jpeg = encode_jpeg(annotated)
                if jpeg:
                    self._latest_jpeg = jpeg
                    self._seq += 1

                frames += 1
                frame_no += 1
                if now - fps_t0 >= 1.0:
                    self._fps = frames / (now - fps_t0)
                    frames = 0
                    fps_t0 = now
                last_ts = now

                # 整条工序走完 -> 记一轮完成，回第一步继续循环（直到人工停止）
                if eng is not None and eng.at_end() and eng.satisfied:
                    self._record_cycle_done()
                    self._cycle += 1
                    self._cycle_wrap = True
                    self._message = f"第 {self._cycle - 1} 轮完成"
                    wrap_text = self._end_hint or f"第 {self._cycle - 1} 轮完成，继续下一轮"
                    self._wait_announce(wrap_text, "end", self._end_hint_sec)
                    # 不 break：下一帧进入 cycle_wrap 过渡，等手离开后回到第一步

                time.sleep(0.005)
        finally:
            # ② 只许收尾自己这一轮：旧线程晚到时（stop 已兜底 / 新运行已接管），
            #    绝不能把新一轮的 run_id / 摄像头句柄拆掉。
            #    检测器不关——进程内缓存复用，close() 在本机会长时间阻塞。
            with self._lock:
                mine = self._run_token is token
                if mine:
                    self._detector = None
                    # 循环模式：不再有「完成即 done」，run 只以 stopped（人工）/ aborted 结束
                    if self._stop_reason:
                        self._finalize_run("stopped", self._stop_reason)   # 操作员主动停止
                    else:
                        self._finalize_run("aborted", "未走完")
            if mine:
                self._teardown()

    def _annotate(self, frame, hand_cam, hand_proj):
        vis = frame.copy()
        h, w = vis.shape[:2]
        if self._H is not None:
            try:
                quad = [proj_to_cam((0, 0), self._H),
                        proj_to_cam((config.PROJ_W - 1, 0), self._H),
                        proj_to_cam((config.PROJ_W - 1, config.PROJ_H - 1), self._H),
                        proj_to_cam((0, config.PROJ_H - 1), self._H)]
                cv2.polylines(vis, [np.int32(quad)], True, (0, 200, 120), 2)
            except Exception:
                pass

        # 料位：画**真实判定范围**（投影坐标下的判定区映射回画面），而不是一个小点。
        # 之前只画 5px 的点，操作员"看起来手在圈里"和"引擎认为在圈里"完全不是一回事。
        if self._engine is not None and self._H is not None:
            Hm = np.asarray(self._H, dtype=np.float64)
            # 先把所有判定区的多边形算出来，再一次性做半透明填充，
            # 避免原来每个料位各 copy 一次全帧 + 各 addWeighted 一次（5 料位 = 6 次全帧分配）。
            polys = []
            for idx, t in enumerate(self._engine.targets.values()):
                col = COLOR_BGR.get(self._colors.get(t.id)) or (170, 170, 170)
                try:
                    pts = np.array(_outline_proj(t), dtype=np.float32).reshape(1, -1, 2)
                    poly = np.round(cv2.perspectiveTransform(pts, Hm)[0]).astype(np.int32)
                    polys.append((poly, col, t, idx))
                except Exception:
                    pass
            if polys:
                mask = np.zeros(vis.shape[:2], dtype=np.uint8)
                overlay = np.zeros_like(vis)
                for poly, col, _t, _i in polys:
                    cv2.fillPoly(mask, [poly], 255)
                    cv2.fillPoly(overlay, [poly], col)
                blended = cv2.addWeighted(overlay, 0.20, vis, 0.80, 0)
                vis = np.where(mask[..., None] > 0, blended, vis).astype(np.uint8)
            for poly, col, t, idx in polys:
                cv2.polylines(vis, [poly], True, col, 2, cv2.LINE_AA)
                cx, cy = proj_to_cam((t.x, t.y), self._H)
                cv2.drawMarker(vis, (cx, cy), col, cv2.MARKER_TILTED_CROSS, 14, 2)
                cv2.putText(vis, _ascii_label(t.name, idx), (cx + 12, cy - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2, cv2.LINE_AA)

        # 手：按「是否落在判定区内」变色 —— 灰 = 没命中（这时系统不会有任何反应）
        if hand_cam is not None:
            hit = self._hand_target is not None
            hcol = (0, 220, 0) if hit else (150, 150, 150)
            hx, hy = int(hand_cam[0]), int(hand_cam[1])
            cv2.circle(vis, (hx, hy), 14, hcol, 3, cv2.LINE_AA)
            cv2.circle(vis, (hx, hy), 2, hcol, -1)
            eng = self._engine
            if hit and eng is not None and self._hand_target in eng.targets:
                txt = "HIT " + _ascii_label(eng.targets[self._hand_target].name, 0)
            else:
                txt = "MISS - not in any pick zone"
            cv2.putText(vis, txt, (hx + 18, hy - 16), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, hcol, 2, cv2.LINE_AA)

        cv2.rectangle(vis, (0, 0), (w, 30), (28, 28, 28), -1)
        eng = self._engine
        if self._H is None:
            info = "NOT CALIBRATED - pick zones unavailable"
        elif eng is not None:
            info = "Step %d/%d   fps=%.1f" % (eng.step_index + 1, eng.step_total, self._fps)
        else:
            info = "idle   fps=%.1f" % self._fps
        cv2.putText(vis, info, (10, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (230, 230, 230), 1, cv2.LINE_AA)
        return vis

    # ─────────────── 记录 ───────────────
    def _record_event(self, kind: str, target_id: Optional[str], target_name: str,
                      event_step: int, frame, run_id: Optional[str], cycle: int):
        """落一条取料事件。锁外调用：frame / run_id / event_step / cycle 都是调用方传进来的快照。

        step_index 用事件发生时的 event_step（ok 事件是 advance 前的步序），
        不再读 self._engine.step_index —— 否则拿对即推进后 ok 会错位到下一步。
        """
        if not run_id:
            return
        snap = recorder.save_snapshot(frame, run_id, event_step, kind)
        db = SessionLocal()
        try:
            db.add(EventModel(
                id=str(uuid.uuid4()), run_id=run_id, step_index=event_step,
                cycle=cycle,
                target_id=target_id, target_name=target_name, result=kind,
                detail=_event_label(kind), snapshot_path=snap, created_at=_now()))
            run = db.query(RunModel).filter(RunModel.id == run_id).first()
            if run is not None:
                if kind == "ok":
                    # 循环模式：done_steps 累计总完成步数（跨轮）
                    run.done_steps = (run.done_steps or 0) + 1
                elif kind in ("wrong", "wrong_order"):
                    run.wrong_count = (run.wrong_count or 0) + 1
            db.commit()
        finally:
            db.close()

    def _record_cycle_done(self):
        """记一条「第 N 轮完成」事件，并把 run.cycles 更新为已完成轮数。"""
        if not self._run_id:
            return
        db = SessionLocal()
        try:
            db.add(EventModel(
                id=str(uuid.uuid4()), run_id=self._run_id,
                step_index=0, cycle=self._cycle,
                target_id=None, target_name="",
                result="cycle_done",
                detail=f"第 {self._cycle} 轮完成",
                snapshot_path=None, created_at=_now()))
            run = db.query(RunModel).filter(RunModel.id == self._run_id).first()
            if run is not None:
                run.cycles = self._cycle
            db.commit()
        finally:
            db.close()

    def _finalize_run(self, status: str, detail: str = "",
                      done_steps: Optional[int] = None):
        if not self._run_id:
            return
        db = SessionLocal()
        try:
            run = db.query(RunModel).filter(RunModel.id == self._run_id).first()
            if run is not None:
                run.status = status
                run.ended_at = _now()
                if done_steps is None and self._engine is not None:
                    done_steps = self._engine.step_index
                if done_steps is not None:
                    run.done_steps = max(run.done_steps or 0, done_steps)
            db.commit()
        finally:
            db.close()
            self._run_id = None

    def _teardown(self):
        """释放本次运行占用的摄像头句柄。可重复调用。

        摄像头必须真的放开 —— 否则 VideoSource 留在 video_manager 里，
        相机一直被占着（/api/cameras/scan 扫不到、别的程序也用不了）。
        检测器不在这里关：它进程内缓存复用，close() 在本机会长时间阻塞。
        """
        with self._lock:
            cam_id = self._camera_id
            self._source = None
            self._source_ok = False
            self._source_desc = ""
            self._no_frame_since = None
            self._camera_id = None
        if cam_id:
            video_service.video_manager.close(cam_id)

    def shutdown(self):
        try:
            self.stop("服务关闭")
        except Exception:
            pass


def _outline_proj(t) -> List[tuple]:
    """料位判定区在**投影坐标**里的边界点（引擎判定用的就是这块）。"""
    if t.shape == "rect":
        hw, hh = t.w / 2.0, t.h / 2.0
        return [(t.x - hw, t.y - hh), (t.x + hw, t.y - hh),
                (t.x + hw, t.y + hh), (t.x - hw, t.y + hh)]
    return [(t.x + t.r * math.cos(i * 2 * math.pi / 72),
             t.y + t.r * math.sin(i * 2 * math.pi / 72)) for i in range(72)]


def _ascii_label(text: str, idx: int = 0) -> str:
    """cv2.putText 只认 ASCII，中文会画成方块。
    这里降级：中文名（如「料盒 A」）只保留其中的 ASCII 部分，全中文则回落到 T1/T2/…"""
    cleaned = "".join(ch for ch in str(text or "")
                      if ch.isascii() and ch.isprintable()).strip()
    return cleaned or ("T%d" % (idx + 1))


def _event_label(kind: str) -> str:
    return {"ok": "拿对", "wrong": "拿错", "wrong_order": "顺序错",
            "mis_touch": "误触", "advance": "进入下一步",
            "cycle_done": "本轮完成"}.get(kind, kind)


def DEFAULT_MODEL_REL_FROM_DB(db) -> str:
    """取当前激活的手部模型路径；没有就回落到内置默认。"""
    from ..models.database import ModelRegistryModel
    row = (db.query(ModelRegistryModel)
           .filter(ModelRegistryModel.model_type == "hand",
                   ModelRegistryModel.is_active == True)  # noqa: E712
           .first())
    if row and row.file_path:
        return row.file_path
    from .hand_service import DEFAULT_MODEL_REL
    return DEFAULT_MODEL_REL


def calibration_service_calibrate(src, debug_abs, camera_id):
    """薄封装：跑标定 + 落库 + 刷新内存中的 H/Hinv。"""
    from . import calibration_service
    res = calibration_service.calibrate(src, debug_abs)
    if not res.get("ok"):
        return res
    rel = None
    if debug_abs:
        try:
            rel = config.data_relative(debug_abs)
        except Exception:
            rel = None
    db = SessionLocal()
    try:
        for old in db.query(CalibrationModel).filter(CalibrationModel.is_current == True).all():  # noqa: E712
            old.is_current = False
        db.add(CalibrationModel(
            id=str(uuid.uuid4()), camera_id=camera_id, proj_size=res["proj_size"],
            homography=res["homography"], homography_inv=res["homography_inv"],
            quad_cam=res["quad_cam"], area=res["area"],
            debug_image_path=rel, warning=res.get("warning", "") or "",
            is_current=True, created_at=_now()))
        db.commit()
    finally:
        db.close()
    res["stored"] = True
    return res


guidance_service = GuidanceService()
