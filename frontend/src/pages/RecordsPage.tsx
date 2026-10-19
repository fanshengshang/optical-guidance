import { useEffect, useState } from 'react'
import {
  Card,
  Drawer,
  Image,
  Popconfirm,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import { recordApi } from '../services/api'
import { toStaticUrl } from '../services/runtime'
import type { RecordEvent, RecordStats, RunDetail, RunItem } from '../types'

function errDetail(err: unknown): string {
  const d = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return d ? String(d) : '操作失败，请稍后重试'
}

const fmt = (s?: string | null) => (s ? s.slice(0, 19).replace('T', ' ') : '—')

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  done: { color: 'success', label: '完成' },
  running: { color: 'processing', label: '运行中' },
  stopped: { color: 'warning', label: '手动停止' },
  aborted: { color: 'error', label: '异常中止' },
}

const statusColor = (s: string) => STATUS_MAP[s]?.color ?? 'default'
const statusLabel = (s: string) => STATUS_MAP[s]?.label ?? s

const resultColor = (r: string) =>
  r === 'ok'
    ? 'green'
    : r === 'wrong'
      ? 'error'
      : r === 'cycle_done'
        ? 'blue'
        : r === 'mis_touch'
          ? 'warning'
          : 'default'

const resultLabel = (r: string) =>
  (
    {
      ok: '拿对',
      wrong: '拿错',
      wrong_order: '顺序错',
      mis_touch: '误触',
      cycle_done: '本轮完成',
    } as Record<string, string>
  )[r] ?? r

const RecordsPage: React.FC = () => {
  const [stats, setStats] = useState<RecordStats | null>(null)
  const [runs, setRuns] = useState<RunItem[]>([])
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailRun, setDetailRun] = useState<RunItem | null>(null)
  const [detailEvents, setDetailEvents] = useState<RecordEvent[]>([])
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    const load = async () => {
      try {
        const s = await recordApi.stats()
        setStats(s.data as RecordStats)
      } catch {
        /* ignore */
      }
      try {
        const r = await recordApi.runs(100)
        setRuns((r.data as RunItem[]) ?? [])
      } catch {
        /* ignore */
      }
    }
    void load()
    const timer = window.setInterval(() => {
      recordApi
        .stats()
        .then((s) => setStats(s.data as RecordStats))
        .catch(() => {
          /* ignore */
        })
    }, 3000)
    return () => window.clearInterval(timer)
  }, [])

  const openDetail = async (id: string, run: RunItem) => {
    setDetailRun(run)
    setDetailOpen(true)
    setDetailLoading(true)
    try {
      const res = await recordApi.run(id)
      setDetailEvents(((res.data as RunDetail)?.events) ?? [])
    } catch (err) {
      message.error(errDetail(err))
    } finally {
      setDetailLoading(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await recordApi.deleteRun(id)
      setRuns((rs) => rs.filter((r) => r.id !== id))
      message.success('已删除运行记录')
    } catch (err) {
      message.error(errDetail(err))
    }
  }

  return (
    <div>
      <Typography.Title level={4}>运行记录</Typography.Title>
      <Typography.Paragraph type="secondary">
        查看历史运行任务的完成情况、判错次数与每步抓拍，用于生产追溯与质量分析。
      </Typography.Paragraph>

      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Card>
          <Space wrap size={32}>
            <Statistic title="累计运行" value={stats?.totalRuns ?? 0} />
            <Statistic title="完成" value={stats?.doneRuns ?? 0} valueStyle={{ color: '#16a34a' }} />
            <Statistic
              title="异常中止"
              value={stats?.abortedRuns ?? 0}
              valueStyle={{ color: '#dc2626' }}
            />
            <Statistic title="判错次数" value={stats?.wrongEvents ?? 0} />
            <Statistic title="准确率" value={stats?.accuracy ?? 0} suffix="%" precision={1} />
          </Space>
        </Card>

        <Card title="运行任务">
          <Table<RunItem>
            size="small"
            rowKey="id"
            dataSource={runs}
            pagination={{ pageSize: 10 }}
            columns={[
              { title: '工序', dataIndex: 'processName' },
              {
                title: '状态',
                dataIndex: 'status',
                render: (s: string) => <Tag color={statusColor(s)}>{statusLabel(s)}</Tag>,
              },
              { title: '轮次', dataIndex: 'cycles' },
              { title: '完成步数', dataIndex: 'doneSteps' },
              { title: '拿错次数', dataIndex: 'wrongCount' },
              { title: '开始时间', dataIndex: 'startedAt', render: (v: string) => fmt(v) },
              {
                title: '结束时间',
                dataIndex: 'endedAt',
                render: (v?: string | null) => fmt(v),
              },
              {
                title: '操作',
                render: (_: unknown, r: RunItem) => (
                  <Space>
                    <a onClick={() => openDetail(r.id, r)}>查看详情</a>
                    <Popconfirm
                      title="确认删除该记录？"
                      okText="删除"
                      cancelText="取消"
                      onConfirm={() => handleDelete(r.id)}
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

      <Drawer
        title={`运行详情 - ${detailRun?.processName ?? ''}`}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={760}
      >
        <Table<RecordEvent>
          size="small"
          rowKey="id"
          loading={detailLoading}
          dataSource={detailEvents}
          pagination={false}
          columns={[
            { title: '轮次', dataIndex: 'cycle' },
            { title: '步骤', dataIndex: 'stepIndex' },
            { title: '取料位', dataIndex: 'targetName' },
            {
              title: '结果',
              dataIndex: 'result',
              render: (r: string) => <Tag color={resultColor(r)}>{resultLabel(r)}</Tag>,
            },
            { title: '说明', dataIndex: 'detail' },
            { title: '时间', dataIndex: 'createdAt', render: (v: string) => fmt(v) },
            {
              title: '抓拍',
              render: (_: unknown, e: RecordEvent) =>
                e.snapshotUrl ? (
                  <Image src={toStaticUrl(e.snapshotUrl)} width={80} />
                ) : (
                  '—'
                ),
            },
          ]}
        />
      </Drawer>
    </div>
  )
}

export default RecordsPage
