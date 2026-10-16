import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Steps,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import GuideConfigForm from '../components/GuideConfigForm'
import { settingsApi } from '../services/api'
import { useAppStore } from '../stores/appStore'
import type { GuideConfig, GuideFieldMeta, GuideSettings, ProcessItem, ProcessStep } from '../types'

function errDetail(err: unknown): string {
  const d = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return d ? String(d) : '操作失败，请稍后重试'
}

const ProcessPage: React.FC = () => {
  const { processes, targets, loadProcesses, addProcess, updateProcess, deleteProcess } =
    useAppStore()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<ProcessItem | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()
  const [viewId, setViewId] = useState<string | null>(null)

  // 引导参数：字段元信息 + 全局有效配置（用作工序覆盖的初值）
  const [fields, setFields] = useState<GuideFieldMeta[]>([])
  const [globalCfg, setGlobalCfg] = useState<GuideConfig>({})
  const [useCustom, setUseCustom] = useState(false)
  const [cfg, setCfg] = useState<GuideConfig>({})

  useEffect(() => {
    void loadProcesses()
  }, [loadProcesses])

  useEffect(() => {
    void (async () => {
      try {
        const res = await settingsApi.getGuide()
        const data = res.data as GuideSettings
        setFields(data.fields ?? [])
        setGlobalCfg(data.config ?? {})
      } catch {
        // 后端未就绪时静默；保存工序时若未加载到字段也不影响
      }
    })()
  }, [])

  useEffect(() => {
    if (!viewId && processes.length) setViewId(processes[0].id)
  }, [processes, viewId])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({
      name: '',
      note: '',
      steps: [],
      startHint: '',
      startHintSec: 3,
      endHint: '',
      endHintSec: 3,
    })
    setUseCustom(false)
    setCfg({})
    setOpen(true)
  }

  const openEdit = (p: ProcessItem) => {
    setEditing(p)
    form.setFieldsValue({
      name: p.name,
      note: p.note ?? '',
      steps: p.steps.map((s) => ({ ...s })),
      startHint: p.startHint ?? '',
      startHintSec: p.startHintSec ?? 3,
      endHint: p.endHint ?? '',
      endHintSec: p.endHintSec ?? 3,
    })
    const has = Boolean(p.guideConfig && Object.keys(p.guideConfig).length)
    setUseCustom(has)
    setCfg(has ? ({ ...(p.guideConfig as GuideConfig) }) : {})
    setOpen(true)
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteProcess(id)
      message.success('已删除工序')
    } catch (err) {
      message.error(errDetail(err))
    }
  }

  const handleOk = async () => {
    let values: {
      name: string
      note?: string
      steps?: ProcessStep[]
      startHint?: string
      startHintSec?: number
      endHint?: string
      endHintSec?: number
    }
    try {
      values = (await form.validateFields()) as typeof values
    } catch {
      return
    }
    const steps: ProcessStep[] = (values.steps ?? []).map((s, i) => ({
      order: i,
      targetId: s.targetId,
      targetName: s.targetName,
      name: s.name,
      instruction: s.instruction ?? '',
      dwellSec: s.dwellSec ?? null,
    }))
    const payload = {
      name: values.name,
      note: values.note ?? null,
      steps,
      startHint: values.startHint ?? null,
      startHintSec: values.startHintSec ?? 3,
      endHint: values.endHint ?? null,
      endHintSec: values.endHintSec ?? 3,
      // 开启自定义才写覆盖，否则 null → 运行时继承全局默认
      guideConfig: useCustom ? cfg : null,
    }
    setSaving(true)
    try {
      if (editing) {
        await updateProcess(editing.id, payload)
        message.success('已保存工序')
      } else {
        await addProcess(payload)
        message.success('已新建工序')
      }
      setOpen(false)
    } catch (err) {
      message.error(errDetail(err))
    } finally {
      setSaving(false)
    }
  }

  const viewProc = processes.find((p) => p.id === viewId)
  const stepItems = (viewProc?.steps ?? []).map((s) => ({
    title: s.name,
    description: s.targetName,
  }))

  return (
    <div>
      <Typography.Title level={4}>工序编排</Typography.Title>
      <Typography.Paragraph type="secondary">
        一个工序由若干有序步骤组成，每个步骤对应一个取料位。运行时按步骤顺序引导工人依次取料。
      </Typography.Paragraph>

      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Card
          title="工序列表"
          extra={
            <Button type="primary" onClick={openCreate}>
              新建工序
            </Button>
          }
        >
          <Table<ProcessItem>
            size="small"
            rowKey="id"
            dataSource={processes}
            pagination={false}
            columns={[
              { title: '名称', dataIndex: 'name' },
              {
                title: '步骤数',
                render: (_: unknown, p: ProcessItem) => p.steps.length,
              },
              {
                title: '步骤摘要',
                render: (_: unknown, p: ProcessItem) => (
                  <Space size={4} wrap>
                    {p.steps.length ? (
                      p.steps.map((s) => (
                        <Tag key={s.targetId + s.name} color="blue">
                          {s.name}
                        </Tag>
                      ))
                    ) : (
                      <span style={{ color: '#999' }}>无步骤</span>
                    )}
                  </Space>
                ),
              },
              {
                title: '引导参数',
                render: (_: unknown, p: ProcessItem) =>
                  p.guideConfig && Object.keys(p.guideConfig).length ? (
                    <Tag color="purple">自定义</Tag>
                  ) : (
                    <Tag>跟随全局</Tag>
                  ),
              },
              {
                title: '备注',
                render: (_: unknown, p: ProcessItem) => p.note || '—',
              },
              {
                title: '创建时间',
                dataIndex: 'createdAt',
                render: (v: string) => (v ? v.slice(0, 19).replace('T', ' ') : '—'),
              },
              {
                title: '操作',
                render: (_: unknown, p: ProcessItem) => (
                  <Space>
                    <a onClick={() => openEdit(p)}>编辑</a>
                    <Popconfirm
                      title="确认删除该工序？"
                      okText="删除"
                      cancelText="取消"
                      onConfirm={() => handleDelete(p.id)}
                    >
                      <a>删除</a>
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        </Card>

        <Card title="工序步骤预览">
          <Select
            style={{ width: 240, marginBottom: 16 }}
            placeholder="选择工序查看步骤"
            value={viewId ?? undefined}
            onChange={(v) => setViewId(v)}
            options={processes.map((p) => ({ value: p.id, label: p.name }))}
          />
          <Steps
            current={-1}
            items={stepItems.length ? stepItems : [{ title: '暂无步骤' }]}
          />
        </Card>
      </Space>

      <Modal
        title={editing ? '编辑工序' : '新建工序'}
        open={open}
        onOk={handleOk}
        onCancel={() => setOpen(false)}
        confirmLoading={saving}
        destroyOnHidden
        width={760}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="工序名称" rules={[{ required: true, message: '请输入工序名称' }]}>
            <Input placeholder="例如：主板装配" />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>
          <Form.Item label="步骤（按顺序取料）" style={{ marginBottom: 8 }}>
            <Form.List name="steps">
              {(fields, { add, remove }) => (
                <>
                  {fields.length > 0 && (
                    <div
                      style={{
                        display: 'flex',
                        gap: 8,
                        padding: '4px 12px',
                        color: '#8c8c8c',
                        fontSize: 12,
                        marginBottom: 4,
                      }}
                    >
                      <span style={{ width: 180, flex: 'none' }}>取料位</span>
                      <span style={{ width: 160, flex: 'none' }}>步骤名</span>
                      <span style={{ width: 100, flex: 'none' }}>停留秒数</span>
                      <span style={{ flex: 1 }}>提示词</span>
                      <span style={{ width: 48, flex: 'none' }} />
                    </div>
                  )}
                  {fields.map((field) => (
                    <div
                      key={field.key}
                      style={{
                        border: '1px solid #e5e5e5',
                        borderRadius: 8,
                        padding: '8px 12px',
                        marginBottom: 8,
                      }}
                    >
                      <Space align="baseline" style={{ display: 'flex' }}>
                        <Form.Item
                          {...field}
                          name={[field.name, 'targetId']}
                          rules={[{ required: true, message: '请选择取料位' }]}
                          style={{ marginBottom: 4 }}
                        >
                          <Select
                            style={{ width: 180 }}
                            placeholder="取料位"
                            options={targets.map((t) => ({ value: t.id, label: t.name }))}
                            onChange={(v) => {
                              const t = targets.find((x) => x.id === v)
                              form.setFieldValue(['steps', field.name, 'targetName'], t?.name ?? '')
                            }}
                          />
                        </Form.Item>
                        <Form.Item
                          {...field}
                          name={[field.name, 'name']}
                          rules={[{ required: true, message: '请输入步骤名' }]}
                          style={{ marginBottom: 4 }}
                        >
                          <Input style={{ width: 160 }} placeholder="步骤名" />
                        </Form.Item>
                        <Form.Item
                          {...field}
                          name={[field.name, 'dwellSec']}
                          style={{ marginBottom: 4 }}
                        >
                          <InputNumber
                            style={{ width: 100 }}
                            min={0.02}
                            max={2}
                            step={0.01}
                            placeholder="默认"
                          />
                        </Form.Item>
                        <Button danger onClick={() => remove(field.name)}>
                          删除
                        </Button>
                      </Space>
                      <Form.Item
                        {...field}
                        name={[field.name, 'instruction']}
                        style={{ marginBottom: 0 }}
                      >
                        <Input
                          placeholder="提示词（投影屏显示给工人看，可留空）"
                        />
                      </Form.Item>
                    </div>
                  ))}
                  <Button
                    onClick={() =>
                      add({ targetId: undefined, targetName: '', name: '', instruction: '', dwellSec: null })
                    }
                  >
                    添加步骤
                  </Button>
                </>
              )}
            </Form.List>
          </Form.Item>

          <Divider plain style={{ marginTop: 4 }}>
            投影提示
          </Divider>
          <Space align="start" style={{ display: 'flex', flexWrap: 'wrap' }}>
            <Form.Item name="startHint" label="开始提示（启动时显示，可留空）" style={{ marginBottom: 8 }}>
              <Input style={{ width: 300 }} placeholder="例如：准备开始，请就位" />
            </Form.Item>
            <Form.Item name="startHintSec" label="停留秒数" style={{ marginBottom: 8 }}>
              <InputNumber min={1} max={30} step={1} style={{ width: 90 }} />
            </Form.Item>
          </Space>
          <Space align="start" style={{ display: 'flex', flexWrap: 'wrap' }}>
            <Form.Item name="endHint" label="结束提示（完成时显示，可留空）" style={{ marginBottom: 8 }}>
              <Input style={{ width: 300 }} placeholder="例如：工序完成，辛苦了" />
            </Form.Item>
            <Form.Item name="endHintSec" label="停留秒数" style={{ marginBottom: 8 }}>
              <InputNumber min={1} max={30} step={1} style={{ width: 90 }} />
            </Form.Item>
          </Space>

          <Divider plain style={{ marginTop: 4 }}>
            引导参数
          </Divider>
          <Space align="center" style={{ marginBottom: 8 }}>
            <Switch
              checked={useCustom}
              onChange={(next) => {
                setUseCustom(next)
                if (next && !Object.keys(cfg).length) setCfg({ ...globalCfg })
              }}
            />
            <span>自定义引导参数（覆盖全局默认）</span>
          </Space>
          {useCustom ? (
            fields.length ? (
              <GuideConfigForm fields={fields} value={cfg} onChange={setCfg} />
            ) : (
              <Alert type="warning" showIcon title="未取到参数字段，请确认后端已启动" />
            )
          ) : (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              未自定义，运行时继承「系统设置」里的全局默认参数。
            </Typography.Text>
          )}
        </Form>
      </Modal>
    </div>
  )
}

export default ProcessPage
