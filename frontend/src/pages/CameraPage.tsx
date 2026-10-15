import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import { cameraApi } from '../services/api'
import { useAppStore } from '../stores/appStore'
import type { Camera, ScanDevice } from '../types'

function errDetail(err: unknown): string {
  const d = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return d ? String(d) : '操作失败，请稍后重试'
}

const SOURCE_TYPES = [
  { value: 'local_device', label: '本机摄像头' },
  { value: 'rtsp', label: '网络摄像头 (RTSP)' },
  { value: 'file', label: '视频文件' },
]

const CameraPage: React.FC = () => {
  const { cameras, selectedCameraId, loadCameras, setSelectedCameraId } = useAppStore()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Camera | null>(null)
  const [saving, setSaving] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [devices, setDevices] = useState<ScanDevice[]>([])
  const [form] = Form.useForm()

  useEffect(() => {
    void loadCameras()
  }, [loadCameras])

  const handleScan = async () => {
    setScanning(true)
    try {
      const res = await cameraApi.scan()
      const list = (res.data?.devices ?? []) as ScanDevice[]
      setDevices(list)
      if (list.length === 0) {
        message.warning('没有扫描到可用摄像头（可能被其他程序占用）')
      } else {
        message.success(`扫描到 ${list.length} 个可用摄像头`)
      }
    } catch (err) {
      message.error(errDetail(err))
    } finally {
      setScanning(false)
    }
  }

  const openCreate = (preset?: Partial<Camera>) => {
    setEditing(null)
    form.resetFields()
    if (preset) form.setFieldsValue(preset)
    setOpen(true)
  }

  const openEdit = (cam: Camera) => {
    setEditing(cam)
    form.setFieldsValue({
      name: cam.name,
      sourceType: cam.sourceType,
      sourceUrl: cam.sourceUrl,
      width: cam.width,
      height: cam.height,
      note: cam.note ?? '',
    })
    setOpen(true)
  }

  const handleOk = async () => {
    let values: Record<string, unknown>
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    setSaving(true)
    try {
      if (editing) {
        await cameraApi.update(editing.id, values)
        message.success('已保存修改')
      } else {
        await cameraApi.create(values)
        message.success('已新增摄像头')
      }
      await loadCameras()
      setOpen(false)
    } catch (err) {
      message.error(errDetail(err))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (cam: Camera) => {
    try {
      await cameraApi.delete(cam.id)
      if (selectedCameraId === cam.id) setSelectedCameraId(null)
      await loadCameras()
      message.success('已删除')
    } catch (err) {
      message.error(errDetail(err))
    }
  }

  return (
    <div>
      <Typography.Title level={4}>摄像头</Typography.Title>
      <Typography.Paragraph type="secondary">
        配置系统使用的摄像头。本机 USB 摄像头按「设备序号」识别，换机位或换设备后序号可能改变，可用下方扫描确认。
      </Typography.Paragraph>

      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="warning"
          showIcon
          message="扫描会短暂占用摄像头"
          description="扫描时系统会逐个打开本机摄像头读一帧，运行引导期间请勿扫描，否则可能打断取流。"
        />

        <Card
          title="本机设备扫描"
          extra={
            <Button onClick={handleScan} loading={scanning}>
              扫描本机设备
            </Button>
          }
        >
          {devices.length === 0 ? (
            <span style={{ color: '#999' }}>尚未扫描。点击右上角「扫描本机设备」查看可用序号。</span>
          ) : (
            <Space wrap size={8}>
              {devices.map((d) => (
                <Tag
                  key={d.index}
                  color="blue"
                  style={{ cursor: 'pointer', padding: '4px 10px' }}
                  onClick={() =>
                    openCreate({
                      name: `摄像头 ${d.index}`,
                      sourceType: 'local_device',
                      sourceUrl: String(d.index),
                      width: Number(d.resolution.split('x')[0]) || 1280,
                      height: Number(d.resolution.split('x')[1]) || 720,
                    })
                  }
                >
                  序号 {d.index} · {d.resolution}
                </Tag>
              ))}
              <span style={{ color: '#999', fontSize: 12 }}>（点击可直接按该设备新建配置）</span>
            </Space>
          )}
        </Card>

        <Card
          title="已配置摄像头"
          extra={
            <Button type="primary" onClick={() => openCreate()}>
              新增摄像头
            </Button>
          }
        >
          <Table<Camera>
            size="small"
            rowKey="id"
            dataSource={cameras}
            pagination={false}
            columns={[
              {
                title: '名称',
                dataIndex: 'name',
                render: (v: string, cam: Camera) => (
                  <Space>
                    {v}
                    {selectedCameraId === cam.id && <Tag color="green">当前选用</Tag>}
                  </Space>
                ),
              },
              {
                title: '来源',
                dataIndex: 'sourceType',
                render: (v: string) => SOURCE_TYPES.find((s) => s.value === v)?.label ?? v,
              },
              { title: '地址/序号', dataIndex: 'sourceUrl' },
              {
                title: '分辨率',
                render: (_: unknown, cam: Camera) => `${cam.width} × ${cam.height}`,
              },
              { title: '备注', dataIndex: 'note', render: (v?: string | null) => v || '—' },
              {
                title: '操作',
                render: (_: unknown, cam: Camera) => (
                  <Space>
                    <a
                      onClick={() => setSelectedCameraId(cam.id)}
                      style={selectedCameraId === cam.id ? { color: '#aaa', pointerEvents: 'none' } : undefined}
                    >
                      {selectedCameraId === cam.id ? '已选用' : '选用'}
                    </a>
                    <a onClick={() => openEdit(cam)}>编辑</a>
                    <Popconfirm
                      title="删除该摄像头配置？"
                      description="只删除配置记录，不影响设备本身。"
                      okText="删除"
                      okButtonProps={{ danger: true }}
                      cancelText="取消"
                      onConfirm={() => handleDelete(cam)}
                    >
                      <a style={{ color: '#ff4d4f' }}>删除</a>
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      </Space>

      <Modal
        title={editing ? '编辑摄像头' : '新增摄像头'}
        open={open}
        onOk={handleOk}
        onCancel={() => setOpen(false)}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={{ sourceType: 'local_device', sourceUrl: '0', width: 1280, height: 720 }}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如：工位摄像头" />
          </Form.Item>
          <Form.Item name="sourceType" label="来源类型" rules={[{ required: true }]}>
            <Select options={SOURCE_TYPES} />
          </Form.Item>
          <Form.Item
            name="sourceUrl"
            label="地址 / 设备序号"
            rules={[{ required: true, message: '请输入地址或设备序号' }]}
            extra="本机摄像头填序号（如 0、1）；网络摄像头填 rtsp:// 地址；文件填视频路径。"
          >
            <Input placeholder="0" />
          </Form.Item>
          <Space size={12}>
            <Form.Item name="width" label="宽" rules={[{ required: true, message: '请输入宽度' }]}>
              <InputNumber min={160} max={4096} placeholder="1280" />
            </Form.Item>
            <Form.Item name="height" label="高" rules={[{ required: true, message: '请输入高度' }]}>
              <InputNumber min={120} max={2160} placeholder="720" />
            </Form.Item>
          </Space>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default CameraPage
