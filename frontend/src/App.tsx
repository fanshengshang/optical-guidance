import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ConfigProvider, Spin } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import MainLayout from './components/Layout/MainLayout'
import ErrorBoundary from './components/ErrorBoundary'

// 每个页面的动态 import 工厂抽出来，便于首屏后统一预加载。
// 否则点击侧边栏时才去拉对应 chunk，加载失败/卡顿会导致懒加载 reject → 白屏。
const loadPage = {
  monitoring: () => import('./pages/MonitoringPage'),
  target: () => import('./pages/TargetPage'),
  process: () => import('./pages/ProcessPage'),
  calibration: () => import('./pages/CalibrationPage'),
  model: () => import('./pages/ModelPage'),
  camera: () => import('./pages/CameraPage'),
  records: () => import('./pages/RecordsPage'),
  projector: () => import('./pages/ProjectorPage'),
  settings: () => import('./pages/SettingsPage'),
}

const MonitoringPage = lazy(loadPage.monitoring)
const TargetPage = lazy(loadPage.target)
const ProcessPage = lazy(loadPage.process)
const CalibrationPage = lazy(loadPage.calibration)
const ModelPage = lazy(loadPage.model)
const CameraPage = lazy(loadPage.camera)
const RecordsPage = lazy(loadPage.records)
const ProjectorPage = lazy(loadPage.projector)
const SettingsPage = lazy(loadPage.settings)

const App: React.FC = () => {
  useEffect(() => {
    const t = window.setTimeout(() => {
      void Promise.allSettled(Object.values(loadPage).map((load) => load()))
    }, 600)
    return () => window.clearTimeout(t)
  }, [])

  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <ErrorBoundary>
          <Suspense
            fallback={
              <div style={{ padding: 48, textAlign: 'center' }}>
                <Spin size="large" />
              </div>
            }
          >
            <Routes>
              {/* 投影页独立于控制台布局，全屏铺到副屏 */}
              <Route path="/projector" element={<ProjectorPage />} />
              <Route element={<MainLayout />}>
                <Route path="/" element={<Navigate to="/monitoring" replace />} />
                <Route path="/monitoring" element={<MonitoringPage />} />
                <Route path="/targets" element={<TargetPage />} />
                <Route path="/processes" element={<ProcessPage />} />
                <Route path="/calibration" element={<CalibrationPage />} />
                <Route path="/models" element={<ModelPage />} />
                <Route path="/cameras" element={<CameraPage />} />
                <Route path="/records" element={<RecordsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="*" element={<Navigate to="/monitoring" replace />} />
              </Route>
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </BrowserRouter>
    </ConfigProvider>
  )
}

export default App
