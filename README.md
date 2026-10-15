# 光学引导系统（Optical Guidance）

摄像头看手 + 投影仪投光的**事前引导**系统。

工人面前没有屏幕：投影仪把引导信息直接投到工作台/料盒上，**当前该取哪个料盒、
拿对给绿光、拿错给红光**；操作员在另一台（或同一台电脑的另一个窗口）通过浏览器
控制台配置与监控。

## 一、整体架构

Web 版：浏览器前端 + 本地 FastAPI 后端，投影端就是一个全屏的浏览器 kiosk 页。

```
┌──────────────┐   MJPEG /api/runtime/stream   ┌─────────────────────┐
│  浏览器控制台  │ <───────────────────────────> │  FastAPI 后端 :8002  │
│  (5174)      │   REST /api/*                 │  SQLAlchemy + SQLite │
└──────────────┘                               │  ├ 引导引擎 engine    │
┌──────────────┐   GET /api/projector/state    │  ├ 摄像头 video_svc   │
│ 投影端 kiosk  │ <──────────────────────────── │  ├ 手部 hand_svc      │
│  副屏全屏      │     轮询 ~10Hz               │  └ 标定 calib_svc     │
└──────────────┘                               └──────────┬──────────┘
                                                          │ DSHOW
                                                   ┌──────┴──────┐
                                                   │ USB 摄像头   │
                                                   │ + 投影仪(副屏)│
                                                   └─────────────┘
```

- **后端**：FastAPI + SQLAlchemy + SQLite + Uvicorn，监听 `127.0.0.1:8002`。
- **前端**：React 19 + Vite + Ant Design v6 + Zustand + TypeScript，监听 `127.0.0.1:5174`。
- **端口与其它本地服务错开**（本系统用 8002 / 5174），可同时开着互不干扰。
- **只用一个模型**：一个手部检测模型（MediaPipe HandLandmarker）。料盒不做识别，
  直接在投影坐标系里存坐标（`targets` 表存 `x / y / r`）。

## 二、它做什么

1. 摄像头实时检测手的位置；
2. 把「手在摄像头画面里的位置」经单应矩阵换算到「投影画面坐标」；
3. 引导引擎按当前工序步骤，判断手伸向的料盒对不对；
4. 投影端把对应料盒点亮成**绿（对）/ 红（错）**，并提示当前步骤该取的料盒。

## 三、目录结构

```
optical-guidance/
├─ 启动光学引导系统.bat / 关闭光学引导系统.bat   # 双击即用
├─ backend/                                      # FastAPI 后端
│  ├─ app/
│  │  ├─ config.py              # 端口 8002、投影 1024x768、数据目录契约
│  │  ├─ main.py                # lifespan / CORS / 静态挂载 / 路由注册
│  │  ├─ seed.py                # 开箱数据（1 个手部模型、1 路摄像头、3 个料盒、示例工序）
│  │  ├─ api/                   # 见下方「接口一览」
│  │  ├─ core/engine.py         # 纯逻辑判定引擎（停留防抖、换盒重计时、步骤推进）
│  │  ├─ core/guide_config.py   # 引导参数定义/校验/合并（动画·判定·检错，全可配）
│  │  ├─ core/geometry.py       # cam_to_proj / proj_to_cam / safe_inv
│  │  ├─ models/               # database.py(ORM) / schemas.py / dependencies.py
│  │  └─ services/             # video / hand / calibration / projector / guidance / recorder
│  │                            #  + settings_service（全局引导参数读写）
│  ├─ model_registry/hand-mediapipe/hand_landmarker.task   # 唯一模型
│  └─ requirements.txt
├─ frontend/                                     # React 前端
│  ├─ src/pages/               # Monitoring / Target / Process / Calibration / Model / Records / Projector / Settings
│  ├─ src/stores/appStore.ts   # Zustand 全局状态
│  └─ src/services/            # axios 实例 + 各域 API
├─ scripts/runtime/
│  ├─ launcher.py              # 真正干活的启动/停止器（Python）
│  └─ start-/stop-optical-guidance.ps1          # 兼容入口，转交 launcher.py
├─ legacy_desktop/             # 旧 tkinter 桌面原型（已归档，仅作参考）
└─ optical-guidance-data/      # 运行数据（见下）
```

## 四、启动 / 停止

**一键**（推荐）：

- 双击 `启动光学引导系统.bat`：建/复用独立 `.venv` → 装依赖 → 清 8002/5174 端口 →
  后台起后端与前端 → 探测副屏（投影仪）并用 Edge kiosk 全屏打开投影页 →
  主屏打开控制台页。
- 双击 `关闭光学引导系统.bat`：按端口 + 记录的 PID 清干净残留进程与投影页浏览器。

**手动**：

```bash
.venv\Scripts\python.exe scripts\runtime\launcher.py start
.venv\Scripts\python.exe scripts\runtime\launcher.py stop
```

打开地址：

| 用途 | 地址 |
|---|---|
| 控制台（运行与监控） | http://127.0.0.1:5174/monitoring |
| 摄像头管理 | http://127.0.0.1:5174/cameras |
| 投影端 kiosk 页 | http://127.0.0.1:5174/projector |
| 接口文档 | http://127.0.0.1:8002/docs |

> **为什么编排逻辑在 Python 而不是 PowerShell？**
> Windows PowerShell 5.1 在环境里同时存在 `Path` 与 `PATH` 两个大小写不同的键时，
> `Start-Process` 只要带 `-RedirectStandardOutput / -RedirectStandardError` 就会抛
> `已添加项。字典中的关键字:"Path"所添加的关键字:"PATH"`，后台服务根本起不来
> （实测归一化 `$env:PATH` 也无效）。改用 Python `subprocess` 派生进程后：
> 日志落盘、PID 记进 `run-state.json`、进程可脱离启动控制台存活，全部可控。
> 两个 `.ps1` 只保留为兼容入口。

## 五、数据目录约定

`optical-guidance-data/` 一级目录固定（数据库里只存**相对路径**，统一走
`config.data_path()` / `data_relative()`）：

| 子目录 | 内容 |
|---|---|
| `snapshots/` | 运行中抓拍的快照 |
| `recordings/` | 录像 / 运行记录 |
| `diagnostics/` | 标定调试图（light / dark / diff / 标定四角） |

另有 `optical-guidance-data/run-state.json` 记录本次启动的进程 PID，供停止脚本精确清理。

项目根目录下的 `.projector-profile/` 是投影页浏览器的专用 profile（启动时自动生成；
浏览器正常退出会自清，被强杀时会残留几十 MB，停掉系统后可随手删）。

## 六、接口一览

| 前缀 | 说明 |
|---|---|
| `GET /health`、`GET /api/config` | 健康检查、前端读取的运行时配置 |
| `/api/cameras` | 摄像头 CRUD + `GET /scan` 枚举设备 |
| `/api/models` | 模型 CRUD + `POST /{id}/activate` 激活 |
| `/api/targets` | 料盒取料位 CRUD（投影坐标 x/y/r） |
| `/api/processes` | 工序 CRUD（步骤以 JSON 存；可带工序级引导参数 `guide_config` 覆盖） |
| `/api/settings` | `GET /guide` 读全局引导参数（含字段元信息）、`PUT /guide` 保存、`DELETE /guide` 恢复默认 |
| `/api/calibration` | `POST /run` 触发标定、`GET /current` 当前标定 |
| `/api/runtime` | `start` / `stop` / `status` / `snapshot` / `stream`(MJPEG) |
| `/api/projector` | `GET /state` 投影端轮询的引导状态；`POST /preview-targets` 把当前取料位轮廓推到投影（摆位核对用） |
| `/api/records` | 运行记录 `runs` / 详情 / 统计 / 删除 |

## 七、引导参数（管理人员可调，不写死）

取料引导的**动画、判定、检错**参数全部集中在后端 `core/guide_config.py` 的 `FIELDS` 里声明，
运行时按 **内置默认 ← 全局设置 ← 工序覆盖** 三层合并出有效配置，代码里没有散落的硬编码阈值。

| 分组 | 参数 | 默认 | 作用 |
|---|---|---|---|
| 引导动画 | `pulse_enabled` | 开 | 当前该取的料盒做呼吸 / 脉冲 |
| | `pulse_period_ms` | 1200 | 脉冲周期（300–3000ms） |
| | `ring_enabled` | 开 | 显示停留进度环（环走满即判定拿对） |
| | `arrow_enabled` | 关 | 从手位置指向目标料盒的引导箭头 |
| 判定 | `dwell_sec` | 0.12 | 手停留多久算「拿对」（0.02–2.0s） |
| 检错 | `detect_wrong_order` | 开 | 检测顺序错（伸向后序步骤才该取的料盒） |
| | `detect_mis_touch` | 开 | 检测误触（进了目标位没停够就离开） |
| | `mis_touch_sec` | 0.05 | 误触的最短停留（0–1.0s） |
| | `hold_red_until_correct` | 开 | 拿错后持续标红直到纠正 |

**在哪里调**：

- **系统设置页（`/settings`）** → 全局默认，对所有工序生效；
- **工序编排页（`/processes` → 编辑某工序）** → 打开「自定义引导参数」开关后单独覆盖，
  关闭则跟随全局。

新增一个可配项 = 往 `FIELDS` 加一条（key / type / default / min / max / group / doc），
**前端表单自动出现对应控件，不需要改前端代码**（字段元信息由 `GET /api/settings/guide` 下发）。

## 八、为什么每次启动要标定

投影仪和摄像头的位置**不固定**。启动后触发一次自动对齐：投影仪依次打全黑、全白，
摄像头各拍一帧，两帧差分找出「投影覆盖区域」，取四角求**单应矩阵 H**：

```
H    : 投影坐标(1024x768) -> 摄像头坐标
Hinv : 摄像头坐标 -> 投影坐标
```

这样料盒只要定义在投影坐标系里，设备怎么挪，标定一次就能对上。差分法对台面颜色、
环境光都不敏感，比找彩色标记稳。

标定服务里带**假性成功防护**：差分图均值 < 3 或 99.5 分位 < 20（说明投影光没照进
摄像头视野）直接判失败并给出原因；四角有 ≥2 条边贴着画面边缘时标记 `warning`。

## 九、独立性

本系统是一个**完全自包含**的独立项目：自己的目录、自己的 `.venv`
（`include-system-site-packages=false`）、自己的端口（8002 / 5174）、
自己的数据目录、自己的数据库。所有代码、配置与依赖都在项目内部，
不依赖、也不引用任何其它系统。

## 十、当前状态与后续

- ✅ 后端 25 个 API 端点注册正常；前端 `tsc` 零错误、`vite build` 通过。
- ✅ 一键启动 / 停止脚本实测可用（启动 → 副屏 kiosk 投影页渲染正常 → 停止 → 端口释放）。
- ✅ 运行时链路实测跑通：启动运行 → DSHOW 取流（1280×720）→ MediaPipe HandLandmarker
  → 引擎推进（第 1/3 步：取A）→ 投影页料盒 A 亮绿 + 控制台实时画面带投影响应四角标注。
- ✅ 摄像头生命周期已收紧：`stop()` 会真正释放句柄（否则相机被一直占着，
  连 `/api/cameras/scan` 都扫不到）；连续 2 秒读不到帧会把状态置成明确报错，
  不再出现「显示运行中 / fps=0」的黑洞；全黑的假分辨率（本机 1920×1080）会被跳过。
- ✅ 已补「摄像头管理页」（`/cameras`）：扫描本机设备、按序号一键新建、增删改、切换当前选用。
- ✅ **前端白屏防护（本轮）**：路由页面前端没有错误边界时，任何页面在渲染时抛异常或懒加载
  chunk 拉取失败，React 会卸载整棵树 → 整屏白屏（连侧边栏都没了，正是「点侧边栏变空白」的
  表现）。现已加两层 `ErrorBoundary`（App 顶层 + MainLayout 内容区）：单页出错只影响内容区，
  显示可读错误 + 重试按钮，侧边栏仍可点其他菜单；并在首屏渲染后**后台预加载**其余页面 chunk，
  把「点击时才拉 chunk」的失败窗口消掉。
- ✅ 判定引擎修了一处误判：手从已拿对的料盒**直接滑到下一个**料盒（中间没有一帧落在空白区）
  时，原先会把下一步该拿的那格误判成「拿错」，现已改为先推进一步再判定。
- ✅ 运行结束状态修正：走完最后一步会置 `done` 且 `done_steps=总步数`；手动停止置 `stopped`
  （追溯页已加中文标签），停止后释放相机与检测器。
- ✅ **修掉停止卡死**：本机 mediapipe 1.1.0 的 `HandLandmarker.close()` 会长时间阻塞在内部
  executor 上（线程栈已实证），导致每次「停止→再启动」都卡 5 秒并报「运行线程未及时退出」、
  摄像头句柄泄漏、下一次启动「取流异常」。现已把检测器改为**进程内缓存复用**（`hand_service.
  build_detector` 按模型路径缓存），`close()` 置为 no-op，运行线程结束只释放摄像头不关检测器。
  实测 stop 0.27s 返回、连续 3 轮 start/stop 无残留线程、无摄像头泄漏、检测器复用、fps 正常。
- ✅ 统计口径修正：准确率只用「取料判定」事件（ok/wrong）算，不再被 `advance` 推进事件稀释。
- ✅ **引导参数可配置（本轮）**：动画（脉冲 / 进度环 / 引导箭头）、判定（停留阈值）、
  检错（顺序错 / 误触 / 拿错持续标红）全部抽成 `core/guide_config.py` 的字段，支持
  「全局默认 ← 工序覆盖」两层；新增「系统设置」页与工序级参数面板，管理人员自行调整，
  不用改代码。引擎已按参数返回**停留进度 0..1**传给投影端画进度环，并新增
  `wrong_order` / `mis_touch` 两类事件（记录与统计已同步）。
  实测：后端 5 项联调全过（参数读写 / 越界夹取 / 未知键过滤 / 工序覆盖往返 / 恢复默认）；
  前端 8 个侧边栏入口点击均不白屏，设置页 6 开关 + 3 数值控件渲染正常、改值保存后重载仍为
  `dwell_sec=0.42`、恢复默认回 `0.12`，控制台零真错误。
- ✅ 环境：`.venv`（system Python 3.12）内 opencv-python 5.0.0.93 / mediapipe 1.1.0 /
  numpy 2.5.3 / Pillow 12.3；摄像头走 **DSHOW** 后端（MSMF 本机不可用），分辨率自动降级。
- ⏳ 待做：
  - 用手实机验证红/绿切换与步骤推进（真人在摄像头前操作）；
  - 标定物理摆位：投影光需完整落进摄像头视野（代码已有失败判据，需配合摆位）；
  - 料盒位置按真实台面重排；投影光对摄像头识别的干扰评估；非同轴视差修正。

### 已知坑

- **摄像头是独占资源**：运行中、以及控制台页开着实时预览时，都占着相机；
  此时 `/api/cameras/scan` 会扫不到设备（这是正常的，不是坏了）。
  要让别的程序用相机，得先「停止运行」并把挂着预览的控制台页关掉。
- **本机 1920×1080 这档能打开、能读、但整帧全黑**（假分辨率），降级候选里已把它排到最后。
- **Edge kiosk 被遮挡窗口会被 Windows 节流**（定时器降到 1 次/秒、绘制层丢弃），
  表现为投影出来一片白。所以启动参数里必须带
  `--disable-backgrounding-occluded-windows --disable-renderer-backgrounding
  --disable-background-timer-throttling --disable-features=CalculateNativeWinOcclusion`。
- **`--reload` 的子进程容易变孤儿**继续占着摄像头，所以后端不以 reload 方式启动。
- 上一轮程序没退干净会占住摄像头导致新进程黑屏——先跑一次停止脚本。
