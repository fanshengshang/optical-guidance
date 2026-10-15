export interface Camera {
  id: string
  name: string
  sourceType: string
  sourceUrl: string
  width: number
  height: number
  note?: string | null
  createdAt: string
}

export interface ScanDevice {
  index: number
  resolution: string
}

export interface ModelItem {
  id: string
  name: string
  modelType: string
  version: string
  filePath: string
  isActive: boolean
  meta?: Record<string, unknown> | null
  createdAt: string
  resolvedPath?: string | null
  available?: boolean
}

export interface Target {
  id: string
  name: string
  shape: 'circle' | 'rect'
  x: number
  y: number
  r: number
  w: number
  h: number
  orderIndex: number
  color: string
  enabled: boolean
  createdAt: string
}

export interface ProcessStep {
  order: number
  targetId: string
  targetName: string
  name: string
  /** 投影屏引导工人的动作提示词（可留空） */
  instruction?: string
}

export interface ProcessItem {
  id: string
  name: string
  steps: ProcessStep[]
  /** 工序级引导参数覆盖（留空则继承全局默认）；键为 camelCase */
  guideConfig?: Record<string, unknown> | null
  note?: string | null
  createdAt: string
}

/** 引导参数的一个可配项（后端 core/guide_config.py 的 FIELDS）。 */
export interface GuideFieldMeta {
  key: string
  type: 'bool' | 'int' | 'float'
  default: boolean | number
  group: string
  doc: string
  min?: number
  max?: number
}

/** 引导参数值集合（camelCase 键）。 */
export type GuideConfig = Record<string, boolean | number>

export interface GuideSettings {
  config: GuideConfig
  fields: GuideFieldMeta[]
}

export interface Calibration {
  id: string
  cameraId?: string | null
  projSize: number[]
  area: number
  quadCam: number[][]
  homography: number[][]
  homographyInv: number[][]
  debugImagePath?: string | null
  warning: string
  isCurrent: boolean
  createdAt: string
}

export interface RuntimeStatus {
  running: boolean
  runId?: string | null
  processId?: string | null
  processName: string
  cameraId?: string | null
  stepIndex: number
  stepTotal: number
  stepText: string
  targetId?: string | null
  handDetected: boolean
  handXy?: number[] | null
  progress?: number | null
  colors: Record<string, string | null>
  lastEvent?: string | null
  wrongCount: number
  calibrated: boolean
  detector: string
  message: string
  fps: number
  sourceOk: boolean
  sourceDesc: string
}

export interface ProjectorTarget {
  id: string
  name: string
  shape: 'circle' | 'rect'
  x: number
  y: number
  r: number
  w: number
  h: number
  color: string
}

export interface ProjectorState {
  mode: string
  projSize: number[]
  targets: ProjectorTarget[]
  colors: Record<string, string | null>
  stepIndex: number
  stepTotal: number
  stepText: string
  /** 当前步的引导提示词（可留空） */
  instruction?: string
  handXy?: number[] | null
  /** 手在目标位的停留进度 0..1，用于进度环 */
  progress?: number | null
  flash?: string | null
  message: string
  seq: number
  // 引导动画参数（来自有效引导配置）
  pulseEnabled: boolean
  pulsePeriodMs: number
  ringEnabled: boolean
  arrowEnabled: boolean
}

export interface RecordEvent {
  id: string
  runId: string
  stepIndex: number
  targetId?: string | null
  targetName: string
  result: string
  detail: string
  snapshotPath?: string | null
  snapshotUrl?: string | null
  createdAt: string
}

export interface RunItem {
  id: string
  processId?: string | null
  processName: string
  cameraId?: string | null
  status: string
  totalSteps: number
  doneSteps: number
  wrongCount: number
  startedAt: string
  endedAt?: string | null
  createdAt: string
}

export interface RunDetail extends RunItem {
  events: RecordEvent[]
}

export interface RecordStats {
  totalRuns: number
  doneRuns: number
  runningRuns: number
  abortedRuns: number
  totalWrong: number
  totalEvents: number
  wrongEvents: number
  accuracy: number
}
