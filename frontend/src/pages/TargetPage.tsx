import { useEffect, useRef, useState } from 'react'
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import { PlusCircleOutlined, PlusSquareOutlined } from '@ant-design/icons'
import { configApi } from '../services/api'
import { useAppStore } from '../stores/appStore'
import type { Target } from '../types'

function errDetail(err: unknown): string {
  const d = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return d ? String(d) : '操作失败，请稍后重试'
}

const shapeLabel = (s: string) => (s === 'circle' ? '圆' : s === 'rect' ? '矩形' : s)
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

/** 拖动中的临时状态：覆盖某个料位的位置 / 大小，松手才写库。 */
interface DragState {
  id: string
  mode: 'move' | 'resize'
  x: number
  y: number
  r: number
  w: number
  h: number
}

const TargetPage: React.FC = () => {
  const { targets, loadTargets, addTarget, updateTarget, deleteTarget } = useAppStore()
  const [projSize, setProjSize] = useState<[number, number]>([1024, 768])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Target | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  // 画布自适应宽度
  const canvasRef = useRef<HTMLDivElement>(null)
  const [canvasW, setCanvasW] = useState(720)

  // 拖拽：drag 驱动渲染，dragRef 供全局 mousemove/up 读最新值（避免闭包旧值）
  const [drag, setDrag] = useState<DragState | null>(null)
  const dragRef = useRef<DragState & { grabX: number; grabY: number } | null>(null)

  useEffect(() => {
    void loadTargets()
    configApi
      .get()
      .then((res) => {
        const ps = (res.data as { projSize?: number[] })?.projSize
        if (Array.isArray(ps) && ps.length >= 2) setProjSize([ps[0], ps[1]])
      })
      .catch(() => {
        /* 取默认值 */
      })
  }, [loadTargets])

  useEffect(() => {
    const el = canvasRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width
      if (w && w > 0) setCanvasW(w)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const [pw, ph] = projSize
  const scale = pw > 0 ? canvasW / pw : 1
  const previewH = Math.round(ph * scale)

  /** 把某个料位按完整字段写回（后端 PUT 是整体替换，必须带全字段）。 */
  const persist = (t: Target) =>
    updateTarget(t.id, {
      name: t.name,
      shape: t.shape,
      x: t.x,
      y: t.y,
      r: t.r,
      w: t.w,
      h: t.h,
      orderIndex: t.orderIndex,
      color: t.color,
      enabled: t.enabled,
    })

  /** 下一个料盒名：取现有「料盒 N」里的最大数字 + 1，避免删除后重名、以及和 seed 的 A/B/C 混号。 */
  const nextName = () => {
    let max = 0
    for (const t of targets) {
      const m = /^料盒\s*(\d+)$/.exec(t.name.trim())
      if (m) max = Math.max(max, parseInt(m[1], 10))
    }
    return `料盒 ${max + 1}`
  }

  const addShape = async (shape: 'circle' | 'rect') => {
    try {
      await addTarget({
        name: nextName(),
        shape,
        x: Math.round(pw / 2),
        y: Math.round(ph / 2),
        r: 80,
        w: 160,
        h: 160,
        orderIndex: targets.reduce((m, t) => Math.max(m, t.orderIndex), -1) + 1,
        color: '#38bdf8',
        enabled: true,
      })
    } catch (err) {
      message.error(errDetail(err))
    }
  }

  const onPointerDown = (e: React.MouseEvent, t: Target, mode: 'move' | 'resize') => {
    e.preventDefault()
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    const px = (e.clientX - rect.left) / scale
    const py = (e.clientY - rect.top) / scale
    dragRef.current = {
      id: t.id,
      mode,
      grabX: t.x - px,
      grabY: t.y - py,
      x: t.x,
      y: t.y,
      r: t.r,
      w: t.w,
      h: t.h,
    }
    setDrag({ id: t.id, mode, x: t.x, y: t.y, r: t.r, w: t.w, h: t.h })

    const onMove = (ev: MouseEvent) => {
      const r2 = canvasRef.current?.getBoundingClientRect()
      const d = dragRef.current
      if (!r2 || !d) return
      const mx = (ev.clientX - r2.left) / scale
      const my = (ev.clientY - r2.top) / scale
      if (d.mode === 'move') {
        d.x = clamp(mx + d.grabX, 0, pw)
        d.y = clamp(my + d.grabY, 0, ph)
      } else {
        const cur = targets.find((x) => x.id === d.id)
        if (!cur) return
        if (cur.shape === 'circle') {
          d.r = clamp(Math.hypot(mx - cur.x, my - cur.y), 10, Math.min(pw, ph))
        } else {
          d.w = clamp(2 * Math.abs(mx - cur.x), 10, pw)
          d.h = clamp(2 * Math.abs(my - cur.y), 10, ph)
        }
      }
      setDrag({ id: d.id, mode: d.mode, x: d.x, y: d.y, r: d.r, w: d.w, h: d.h })
    }

    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      const d = dragRef.current
      dragRef.current = null
      setDrag(null)
      if (!d) return
      const cur = targets.find((x) => x.id === d.id)
      if (cur) {
        void persist({ ...cur, x: d.x, y: d.y, r: d.r, w: d.w, h: d.h })
      }
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteTarget(id)
      message.success('已删除取料位')
    } catch (err) {
      message.error(errDetail(err))
    }
  }

  const openEdit = (t: Target) => {
    setEditing(t)
    form.setFieldsValue({ name: t.name, color: t.color, orderIndex: t.orderIndex, enabled: t.enabled })
    setOpen(true)
  }

  const handleOk = async () => {
    let values: Record<string, unknown>
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    if (!editing) return
    setSaving(true)
    try {
      await persist({
        ...editing,
        name: values.name as string,
        color: values.color as string,
        orderIndex: values.orderIndex as number,
        enabled: values.enabled as boolean,
      })
      message.success('已保存取料位')
      setOpen(false)
    } catch (err) {
      message.error(errDetail(err))
    } finally {
      setSaving(false)
    }
  }

  /** 渲染单个料位（拖动时用 drag 里的临时值）。 */
  const renderShape = (t: Target) => {
    const d = drag && drag.id === t.id ? drag : null
    const x = d ? d.x : t.x
    const y = d ? d.y : t.y
    const r = d ? d.r : t.r
    const w = d ? d.w : t.w
    const h = d ? d.h : t.h
    const isRect = t.shape === 'rect'
    const fill = 'rgba(56,189,248,0.15)'
    return (
      <div key={t.id} style={{ position: 'absolute', left: 0, top: 0, pointerEvents: 'none' }}>
        <div
          onMouseDown={(e) => onPointerDown(e, t, 'move')}
          style={{
            position: 'absolute',
            left: isRect ? x * scale - (w * scale) / 2 : x * scale - r * scale,
            top: isRect ? y * scale - (h * scale) / 2 : y * scale - r * scale,
            width: isRect ? w * scale : r * 2 * scale,
            height: isRect ? h * scale : r * 2 * scale,
            border: `2px solid ${t.color}`,
            background: fill,
            borderRadius: isRect ? 4 : '50%',
            cursor: 'move',
            pointerEvents: 'auto',
          }}
        />
        {/* 大小手柄：圆在右缘，矩形在右下角 */}
        <div
          onMouseDown={(e) => onPointerDown(e, t, 'resize')}
          style={{
            position: 'absolute',
            left: (isRect ? x + w / 2 : x + r) * scale - 6,
            top: (isRect ? y + h / 2 : y) * scale - 6,
            width: 12,
            height: 12,
            background: '#fff',
            border: `2px solid ${t.color}`,
            borderRadius: '50%',
            cursor: 'nwse-resize',
            pointerEvents: 'auto',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: x * scale - 60,
            top: (isRect ? y + h / 2 : y + r) * scale + 6,
            width: 120,
            textAlign: 'center',
            color: '#cbd5e1',
            fontSize: 12,
            pointerEvents: 'none',
          }}
        >
          {t.name}
        </div>
      </div>
    )
  }

  return (
    <div>
      <Typography.Title level={4}>取料位坐标</Typography.Title>
      <Typography.Paragraph type="secondary">
        点下方按钮在画布上生成取料位，拖动中心移动位置、拖动白点调整大小；松手即保存并同步到投影页。
      </Typography.Paragraph>

      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Card
          title="取料位画布（投影坐标，可拖拽摆放）"
          extra={
            <Space>
              <Button icon={<PlusCircleOutlined />} onClick={() => addShape('circle')}>
                圆形
              </Button>
              <Button icon={<PlusSquareOutlined />} onClick={() => addShape('rect')}>
                矩形
              </Button>
            </Space>
          }
        >
          <div
            ref={canvasRef}
            style={{
              width: '100%',
              height: previewH,
              position: 'relative',
              background: '#0d1013',
              border: '1px solid #333',
              borderRadius: 8,
              overflow: 'hidden',
              userSelect: 'none',
            }}
          >
            {targets.map(renderShape)}
          </div>
          <div style={{ color: '#888', fontSize: 12, marginTop: 8 }}>
            投影分辨率 {pw}×{ph}，画布按 {scale.toFixed(3)} 等比缩放。圆拖右缘白点调半径，矩形拖右下角白点调宽高。
          </div>
        </Card>

        <Card title="取料位列表">
          <Table<Target>
            size="small"
            rowKey="id"
            dataSource={targets}
            pagination={false}
            columns={[
              { title: '名称', dataIndex: 'name' },
              { title: '形状', dataIndex: 'shape', render: (s: string) => shapeLabel(s) },
              {
                title: '坐标 (x, y)',
                render: (_: unknown, t: Target) => `(${Math.round(t.x)}, ${Math.round(t.y)})`,
              },
              {
                title: '尺寸',
                render: (_: unknown, t: Target) =>
                  t.shape === 'rect' ? `${Math.round(t.w)} × ${Math.round(t.h)}` : `r = ${Math.round(t.r)}`,
              },
              { title: '排序', dataIndex: 'orderIndex' },
              {
                title: '启用',
                dataIndex: 'enabled',
                render: (e: boolean) => (
                  <Tag color={e ? 'green' : 'default'}>{e ? '启用' : '停用'}</Tag>
                ),
              },
              {
                title: '操作',
                render: (_: unknown, t: Target) => (
                  <Space>
                    <a onClick={() => openEdit(t)}>编辑</a>
                    <Popconfirm
                      title="确认删除该取料位？"
                      okText="删除"
                      cancelText="取消"
                      onConfirm={() => handleDelete(t.id)}
                    >
                      <a>删除</a>
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      </Space>

      <Modal
        title="编辑取料位"
        open={open}
        onOk={handleOk}
        onCancel={() => setOpen(false)}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如：电容盒" />
          </Form.Item>
          <Form.Item name="color" label="颜色" rules={[{ required: true }]}>
            <Input placeholder="#38bdf8" />
          </Form.Item>
          <Space>
            <Form.Item name="orderIndex" label="排序" rules={[{ required: true }]}>
              <InputNumber min={0} />
            </Form.Item>
            <Form.Item name="enabled" label="是否启用" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  )
}

export default TargetPage
