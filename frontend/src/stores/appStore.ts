import { create } from 'zustand'
import { cameraApi, modelApi, processApi, targetApi } from '../services/api'
import type { Camera, ModelItem, ProcessItem, Target } from '../types'

const PROCESS_KEY = 'opticalGuidance.selectedProcessId'
const CAMERA_KEY = 'opticalGuidance.selectedCameraId'

const getStored = (key: string) => {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

const setStored = (key: string, value: string | null) => {
  try {
    if (value) window.localStorage.setItem(key, value)
    else window.localStorage.removeItem(key)
  } catch {
    // 忽略隐私模式下的写入失败
  }
}

interface AppState {
  cameras: Camera[]
  models: ModelItem[]
  targets: Target[]
  processes: ProcessItem[]
  selectedProcessId: string | null
  selectedCameraId: string | null

  loadCameras: () => Promise<void>
  loadModels: () => Promise<void>
  loadTargets: () => Promise<void>
  loadProcesses: () => Promise<void>
  setSelectedProcessId: (id: string | null) => void
  setSelectedCameraId: (id: string | null) => void

  addTarget: (data: unknown) => Promise<void>
  updateTarget: (id: string, data: unknown) => Promise<void>
  deleteTarget: (id: string) => Promise<void>

  addProcess: (data: unknown) => Promise<void>
  updateProcess: (id: string, data: unknown) => Promise<void>
  deleteProcess: (id: string) => Promise<void>
}

export const useAppStore = create<AppState>((set, get) => ({
  cameras: [],
  models: [],
  targets: [],
  processes: [],
  selectedProcessId: getStored(PROCESS_KEY),
  selectedCameraId: getStored(CAMERA_KEY),

  loadCameras: async () => {
    try {
      const res = await cameraApi.list()
      set((s) => {
        const list = res.data as Camera[]
        const stillThere = list.some((c) => c.id === s.selectedCameraId)
        const next = stillThere ? s.selectedCameraId : (list[0]?.id ?? null)
        setStored(CAMERA_KEY, next)
        return { cameras: list, selectedCameraId: next }
      })
    } catch {
      // 后端还没起来时保持安静
    }
  },

  loadModels: async () => {
    try {
      const res = await modelApi.list()
      set({ models: res.data as ModelItem[] })
    } catch {
      /* ignore */
    }
  },

  loadTargets: async () => {
    try {
      const res = await targetApi.list()
      set({ targets: res.data as Target[] })
    } catch {
      /* ignore */
    }
  },

  loadProcesses: async () => {
    try {
      const res = await processApi.list()
      set((s) => {
        const list = res.data as ProcessItem[]
        const stillThere = list.some((p) => p.id === s.selectedProcessId)
        const next = stillThere ? s.selectedProcessId : (list[0]?.id ?? null)
        setStored(PROCESS_KEY, next)
        return { processes: list, selectedProcessId: next }
      })
    } catch {
      /* ignore */
    }
  },

  setSelectedProcessId: (id) => {
    setStored(PROCESS_KEY, id)
    set({ selectedProcessId: id })
  },

  setSelectedCameraId: (id) => {
    setStored(CAMERA_KEY, id)
    set({ selectedCameraId: id })
  },

  addTarget: async (data) => {
    const res = await targetApi.create(data)
    set((s) => ({ targets: [...s.targets, res.data as Target] }))
  },
  updateTarget: async (id, data) => {
    // 乐观更新：先用本地值立即重绘，避免拖拽松手时图形闪回旧位置
    const prev = get().targets
    set((s) => ({ targets: s.targets.map((t) => (t.id === id ? ({ ...t, ...(data as Partial<Target>) }) : t)) }))
    try {
      const res = await targetApi.update(id, data)
      set((s) => ({ targets: s.targets.map((t) => (t.id === id ? (res.data as Target) : t)) }))
    } catch (err) {
      set({ targets: prev }) // 失败回滚
      throw err
    }
  },
  deleteTarget: async (id) => {
    await targetApi.delete(id)
    set((s) => ({ targets: s.targets.filter((t) => t.id !== id) }))
  },

  addProcess: async (data) => {
    const res = await processApi.create(data)
    set((s) => ({ processes: [...s.processes, res.data as ProcessItem] }))
  },
  updateProcess: async (id, data) => {
    const res = await processApi.update(id, data)
    set((s) => ({ processes: s.processes.map((p) => (p.id === id ? (res.data as ProcessItem) : p)) }))
  },
  deleteProcess: async (id) => {
    await processApi.delete(id)
    set((s) => ({ processes: s.processes.filter((p) => p.id !== id) }))
  },
}))
