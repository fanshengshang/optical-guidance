import { useEffect, useRef, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Progress,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from 'antd'
import { runtimeApi } from '../services/api'
import { toAbsoluteApiUrl } from '../services/runtime'
import { useAppStore } from '../stores/appStore'
import type { RuntimeStatus } from '../types'

function errDetail(err: unknown): string {
  const d = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return d ? String(d) : '操作失败，请稍后重试'
}

const COLOR_INFO: Record<string, { bg: string; border: string; text: string }> = {
  green: { bg: '#16a34a', border: '#16a34a', text: '拿对' },
  red: { bg: '#dc2626', border: '#dc2626', text: '拿错' },
  hint: { bg: 'transparent', border: '#22c55e', text: '提示' },
  warn: { bg: '#f59e0b', border: '#f59e0b', text: '警告' },
}

const LEGEND = [
  { c: '#16a34a', t: '绿 = 拿对' },
  { c: '#dc2626', t: '红 = 拿错' },
  { c: '#22c55e', t: '淡绿描边 = 提示' },
  { c: '#f59e0b', t: '琥珀 = 警告' },
  { c: '#d1d5db', t: '灰 = 未激活' },
]

const MonitoringPage: React.FC = () => {
  const {
    processes,
    cameras,
    targets,
    selectedProcessId,
    selectedCameraId,
    setSelectedProcessId,
    setSelectedCameraId,
    loadCameras,
    loadProcesses,
    loadTargets,
  } = useAppStore()

  const [status, setStatus] = useState<RuntimeStatus | null>(null)
  const [nonce, setNonce] = useState(0)
  const [startBusy, setStartBusy] = useState(false)
  const [stopBusy, setStopBusy] = useState(false)

  const bumpNonce = () => setNonce((n) => n + 1)

  useEffect(() => {
    void loadCameras()
    void loadProcesses()
    void loadTargets()
  }, [loadCameras, loadProcesses, loadTargets])

  useEffect(() => {
    let alive = true
    const timer = window.setInterval(async () => {
      try {
        const res = await runtimeApi.status()
        if (alive) setStatus(res.data as RuntimeStatus)
      } catch {
        /* 后端未连接时保持静默 */
      }
    }, 500)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [])

  const handleStart = async () => {
    if (!selectedProcessId) {
      message.error('请先在上方选择工序')
      return
    }
    if (!selectedCameraId) {
      message.error('请先在上方选择摄像头')
      return
    }
    setStartBusy(true)
    try {
      await runtimeApi.start(selectedProcessId, selectedCameraId)
      bumpNonce()
      message.success('已开始运行（如未标定将自动标定）')
    } catch (err) {
      message.error(errDetail(err))
    } finally {
      setStartBusy(false)
    }
  }

  const handleStop = async () => {
    setStopBusy(true)
    try {
      await runtimeApi.stop()
      bumpNonce()
      message.success('已停止运行')
    } catch (err) {
      message.error(errDetail(err))
    } finally {
      setStopBusy(false)
    }
  }

  const running = status?.running ?? false
  // 工序自动走完后端流自然结束，multipart 连接被服务端关闭，<img> 会停在最后一帧。
  // 手动 start/stop 已 bump nonce，这里补上 running true→false 时再 bump 一次，画面切回预览流。
  const prevRunningRef = useRef(false)
  useEffect(() => {
    const was = prevRunningRef.current
    prevRunningRef.current = running
    if (was && !running) bumpNonce()
  }, [running])
  const streamSrc = selectedCameraId
    ? toAbsoluteApiUrl(`/api/runtime/stream?cameraId=${selectedCameraId}&v=${nonce}`)
    : ''

  const total = status?.stepTotal ?? 0
  const idx = status?.stepIndex ?? 0
  const percent = total > 0 ? Math.round(((idx + 1) / total) * 100) : 0

  const colorOf = (id: string) => {
    const c = status?.colors?.[id] ?? null
    return COLOR_INFO[c ?? ''] ?? { bg: 'transparent', border: '#d1d5db', text: '未激活' }
  }

  return (
    <div>
      <Typography.Title level={4}>实时监控与引导</Typography.Title>
      <Typography.Paragraph type="secondary">
        系统通过摄像头识别手的位置，并在投影屏上用红/绿光引导工人拿取正确的料。
      </Typography.Paragraph>

      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        {!running && (
          <Alert
            type="info"
            showIcon
            message="当前未运行"
            description="选择工序与摄像头后，点击「开始运行」即可启动引导。"
          />
        )}
        {status && !status.calibrated && (
          <Alert
            type="warning"
            showIcon
            message="尚未标定"
            description="投影仪与摄像头位置可能已变动，点「开始运行」会自动做一次投影-摄像头对齐标定。"
          />
        )}
        {running && status && !status.sourceOk && (
          <Alert
            type="error"
            showIcon
            message="摄像头读不到画面"
            description={`${status.message || '取流异常'}${status.sourceDesc ? `（${status.sourceDesc}）` : ''}。常见原因是摄像头被其他程序占用，请停止后关闭占用方再重试。`}
          />
        )}

        <Card>
          <Space wrap>
            <Select
              style={{ width: 220 }}
              placeholder="选择工序"
              value={selectedProcessId ?? undefined}
              onChange={(v) => setSelectedProcessId(v)}
              options={processes.map((p) => ({ value: p.id, label: p.name }))}
            />
            <Select
              style={{ width: 220 }}
              placeholder="选择摄像头"
              value={selectedCameraId ?? undefined}
              onChange={(v) => {
                setSelectedCameraId(v)
                bumpNonce()
              }}
              options={cameras.map((c) => ({ value: c.id, label: c.name }))}
            />
            <Button type="primary" loading={startBusy} disabled={running} onClick={handleStart}>
              开始运行
            </Button>
            <Button danger loading={stopBusy} disabled={!running} onClick={handleStop}>
              停止运行
            </Button>
            <Tag color={running ? 'green' : 'default'}>{running ? '运行中' : '已停止'}</Tag>
          </Space>
        </Card>

        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 520px', minWidth: 320 }}>
            <Card title="摄像头实时画面">
              {streamSrc ? (
                <img
                  src={streamSrc}
                  alt=""
                  style={{
                    width: '100%',
                    maxHeight: 480,
                    objectFit: 'contain',
                    background: '#000',
                    borderRadius: 8,
                    display: 'block',
                  }}
                />
              ) : (
                <Alert type="info" showIcon message="请先在上方选择摄像头以查看实时画面" />
              )}
              <div style={{ marginTop: 8, color: '#888', fontSize: 12 }}>
                操作方式：将手伸入取料位区域，系统检测到手后投影对应颜色光。绿=拿对，红=拿错，请按投影引导取料。
              </div>
            </Card>
          </div>

          <div
            style={{
              flex: '1 1 360px',
              minWidth: 300,
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
            }}
          >
            <Card title="运行状态">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="轮次">
                  <Tag color="blue">第 {status?.cycle ?? 1} 轮</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="当前步骤">{status?.stepText || '—'}</Descriptions.Item>
                <Descriptions.Item label="进度">
                  <Progress
                    percent={percent}
                    format={() => `${idx + 1} / ${total}`}
                  />
                </Descriptions.Item>
                <Descriptions.Item label="检测到手">
                  <Tag color={status?.handDetected ? 'green' : 'default'}>
                    {status?.handDetected ? '是' : '否'}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="帧率">{status?.fps ?? 0} FPS</Descriptions.Item>
                <Descriptions.Item label="取流">
                  <Tag color={status?.sourceOk ? 'green' : 'red'}>
                    {status?.sourceOk ? '正常' : '异常'}
                  </Tag>
                  <span style={{ marginLeft: 8, color: '#888', fontSize: 12 }}>
                    {status?.sourceDesc || '—'}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="判错次数">{status?.wrongCount ?? 0}</Descriptions.Item>
                <Descriptions.Item label="检测器">{status?.detector || '—'}</Descriptions.Item>
                <Descriptions.Item label="已标定">
                  <Tag color={status?.calibrated ? 'green' : 'red'}>
                    {status?.calibrated ? '是' : '否'}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="状态消息">{status?.message || '—'}</Descriptions.Item>
                <Descriptions.Item label="最近事件">{status?.lastEvent || '—'}</Descriptions.Item>
              </Descriptions>
            </Card>

            <Card title="取料位状态">
              <Space wrap size={8}>
                {targets.map((t) => {
                  const info = colorOf(t.id)
                  const light = info.bg === 'transparent'
                  return (
                    <div
                      key={t.id}
                      style={{
                        width: 104,
                        border: `2px solid ${info.border}`,
                        background: info.bg,
                        borderRadius: 8,
                        padding: '8px 6px',
                        color: light ? '#555' : '#fff',
                        textAlign: 'center',
                      }}
                    >
                      <div style={{ fontWeight: 600, fontSize: 12 }}>{t.name}</div>
                      <div style={{ fontSize: 12 }}>{info.text}</div>
                    </div>
                  )
                })}
                {targets.length === 0 && <span style={{ color: '#999' }}>暂无取料位</span>}
              </Space>
              <Space wrap size={12} style={{ marginTop: 12 }}>
                {LEGEND.map((l) => (
                  <span key={l.t} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#666' }}>
                    <span style={{ width: 12, height: 12, background: l.c, border: '1px solid #ccc', borderRadius: 2, display: 'inline-block' }} />
                    {l.t}
                  </span>
                ))}
              </Space>
            </Card>
          </div>
        </div>
      </Space>
    </div>
  )
}

export default MonitoringPage
