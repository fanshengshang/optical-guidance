import { useEffect } from 'react'
import { useLocation, Outlet } from 'react-router-dom'
import { Layout } from 'antd'
import Sidebar from './Sidebar'
import ErrorBoundary from '../ErrorBoundary'
import { useAppStore } from '../../stores/appStore'

const { Content, Sider } = Layout

const MainLayout: React.FC = () => {
  const location = useLocation()
  const { loadCameras, loadModels, loadTargets, loadProcesses } = useAppStore()

  useEffect(() => {
    void Promise.allSettled([loadCameras(), loadModels(), loadTargets(), loadProcesses()])
  }, [loadCameras, loadModels, loadTargets, loadProcesses])

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={248}
        collapsedWidth={72}
        theme="light"
        style={{
          background: '#fff',
          borderRight: '1px solid #f0f0f0',
          position: 'sticky',
          top: 0,
          left: 0,
          height: '100vh',
          zIndex: 20,
          flexShrink: 0,
        }}
      >
        <Sidebar />
      </Sider>
      <Layout>
        <Content
          style={{
            padding: 16,
            background: '#f5f5f5',
            minHeight: '100vh',
            minWidth: 0,
            overflow: 'auto',
          }}
        >
          <ErrorBoundary key={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </Content>
      </Layout>
    </Layout>
  )
}

export default MainLayout
