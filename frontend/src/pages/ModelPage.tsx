import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import { modelApi } from '../services/api'
import { useAppStore } from '../stores/appStore'
import type { ModelItem } from '../types'

function errDetail(err: unknown): string {
  const d = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return d ? String(d) : '操作失败，请稍后重试'
}

const ModelPage: React.FC = () => {
  const { models, loadModels } = useAppStore()
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    void loadModels()
  }, [loadModels])

  const handleActivate = async (id: string) => {
    try {
      await modelApi.activate(id)
      await loadModels()
      message.success('已激活该模型')
    } catch (err) {
      message.error(errDetail(err))
    }
  }

  const openCreate = () => {
    form.resetFields()
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
      await modelApi.create(values)
      await loadModels()
      message.success('已新建模型')
      setOpen(false)
    } catch (err) {
      message.error(errDetail(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <Typography.Title level={4}>模型</Typography.Title>
      <Typography.Paragraph type="secondary">
        管理手部检测模型与系统配置。取料位不靠模型识别，直接使用坐标配置。
      </Typography.Paragraph>

      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="只需要一个模型"
          description="本系统只需一个模型：手部检测（MediaPipe HandLandmarker）。取料位引导由坐标配置直接驱动，不依赖模型识别。"
        />

        <Card
          title="模型列表"
          extra={
            <Button type="primary" onClick={openCreate}>
              新建模型
            </Button>
          }
        >
          <Table<ModelItem>
            size="small"
            rowKey="id"
            dataSource={models}
            pagination={false}
            columns={[
              { title: '名称', dataIndex: 'name' },
              { title: '类型', dataIndex: 'modelType' },
              { title: '版本', dataIndex: 'version' },
              { title: '文件路径', dataIndex: 'filePath' },
              {
                title: '激活',
                dataIndex: 'isActive',
                render: (b: boolean) => (
                  <Tag color={b ? 'green' : 'default'}>{b ? '已激活' : '未激活'}</Tag>
                ),
              },
              {
                title: '可用',
                render: (_: unknown, m: ModelItem) => {
                  const ok = m.available !== false && !!m.resolvedPath
                  return <Tag color={ok ? 'green' : 'red'}>{ok ? '可用' : '文件缺失'}</Tag>
                },
              },
              { title: '解析路径', dataIndex: 'resolvedPath', render: (v?: string | null) => v || '—' },
              {
                title: '创建时间',
                dataIndex: 'createdAt',
                render: (v: string) => (v ? v.slice(0, 19).replace('T', ' ') : '—'),
              },
              {
                title: '操作',
                render: (_: unknown, m: ModelItem) => (
                  <Space>
                    <a
                      onClick={() => handleActivate(m.id)}
                      style={m.isActive ? { color: '#aaa', pointerEvents: 'none' } : undefined}
                    >
                      {m.isActive ? '已激活' : '激活'}
                    </a>
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      </Space>

      <Modal
        title="新建模型"
        open={open}
        onOk={handleOk}
        onCancel={() => setOpen(false)}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如：手部检测" />
          </Form.Item>
          <Form.Item name="modelType" label="类型" rules={[{ required: true, message: '请输入类型' }]}>
            <Input placeholder="例如：hand-landmarker" />
          </Form.Item>
          <Form.Item name="version" label="版本" rules={[{ required: true, message: '请输入版本' }]}>
            <Input placeholder="例如：1.0.0" />
          </Form.Item>
          <Form.Item
            name="filePath"
            label="文件路径"
            rules={[{ required: true, message: '请输入文件路径' }]}
          >
            <Input placeholder="模型文件相对或绝对路径" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default ModelPage
