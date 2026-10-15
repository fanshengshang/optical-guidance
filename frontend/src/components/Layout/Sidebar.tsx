import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Button, Menu, Tooltip } from 'antd'
import type { MenuProps } from 'antd'
import {
  AimOutlined,
  BlockOutlined,
  DeploymentUnitOutlined,
  FundProjectionScreenOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MonitorOutlined,
  RadarChartOutlined,
  SettingOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'

type MenuItem = Required<MenuProps>['items'][number]

const menuItems: MenuItem[] = [
  {
    key: '/monitoring-group',
    type: 'group',
    label: '运行与监控',
    children: [
      { key: '/monitoring', icon: <MonitorOutlined />, label: '实时监控与引导' },
    ],
  },
  {
    key: '/config-group',
    type: 'group',
    label: '引导配置',
    children: [
      { key: '/targets', icon: <AimOutlined />, label: '取料位坐标' },
      { key: '/processes', icon: <DeploymentUnitOutlined />, label: '工序编排' },
    ],
  },
  {
    key: '/device-group',
    type: 'group',
    label: '设备与模型',
    children: [
      { key: '/calibration', icon: <FundProjectionScreenOutlined />, label: '投影标定' },
      { key: '/cameras', icon: <VideoCameraOutlined />, label: '摄像头' },
      { key: '/models', icon: <BlockOutlined />, label: '模型' },
    ],
  },
  {
    key: '/trace-group',
    type: 'group',
    label: '生产追溯',
    children: [
      { key: '/records', icon: <RadarChartOutlined />, label: '运行记录' },
    ],
  },
  {
    key: '/system-group',
    type: 'group',
    label: '系统',
    children: [
      { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
    ],
  },
]

const Sidebar: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  const openProjector = () => {
    window.open('/projector', '_blank', 'noopener')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          padding: collapsed ? '16px 0' : '16px 16px 16px 20px',
          gap: 8,
        }}
      >
        {!collapsed && (
          <div
            style={{
              fontWeight: 700,
              fontSize: 15,
              color: '#1890ff',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
            }}
            title="光学引导系统"
          >
            光学引导系统
          </div>
        )}
        <Tooltip title={collapsed ? '展开侧边栏' : '折叠侧边栏'}>
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed((v) => !v)}
          />
        </Tooltip>
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        <Menu
          mode="inline"
          inlineCollapsed={collapsed}
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => {
            if (key.startsWith('/')) navigate(key)
          }}
          style={{ borderInlineEnd: 'none' }}
        />
      </div>

      <div style={{ padding: collapsed ? '12px 8px' : '12px 16px' }}>
        <Tooltip title="投影页请在副屏全屏打开（启动脚本会自动处理）">
          <Button block={!collapsed} icon={<FundProjectionScreenOutlined />} onClick={openProjector}>
            {!collapsed && '打开投影页'}
          </Button>
        </Tooltip>
      </div>
    </div>
  )
}

export default Sidebar
