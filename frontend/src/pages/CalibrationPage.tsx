import { useEffect, useState } from 'react'
import { Alert, Button, Card, Descriptions, Empty, Select, Space, Table, Tag, Typography, message } from 'antd'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { calibrationApi, calibrationOverlayUrl } from '../services/api'
import { useAppStore } from '../stores/appStore'
import type { Calibration } from '../types'

function errDetail(err: unknown): string {
  const d = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return d ? String(d) : '操作失败，请稍后重试'
}

const CalibrationPage: React.FC = () => {
  const { cameras, selectedCameraId, setSelectedCameraId, loadCameras } = useAppStore()
  const [current, setCurrent] = useState<Calibration | null>(null)
  const [list, setList] = useState<Calibration[]>([])
  const [calibrating, setCalibrating] = useState(false)
  const [overlayFailed, setOverlayFailed] = useState(false)

  const refresh = async () => {
    try {
      const c = await calibrationApi.current()
      setCurrent((c.data as Calibration) ?? null)
      setOverlayFailed(false)
    } catch {
      /* 暂无标定结果 */
    }
    try {
      const l = await calibrationApi.list()
      setList((l.data as Calibration[]) ?? [])
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    void loadCameras()
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadCameras])

  const handleRun = async () => {
    if (!selectedCameraId) {
      message.error('请先在上方选择摄像头')
      return
    }
    setCalibrating(true)
    try {
      const res = await calibrationApi.run(selectedCameraId)
      const data = res.data as Calibration
      message.success(`标定完成，投影区面积 ${data.area}`)
      // 运行返回的是标定结果体，缺 id/createdAt/isCurrent，回读一次拿到完整记录
      await refresh()
    } catch (err) {
      message.error(errDetail(err))
    } finally {
      setCalibrating(false)
    }
  }

  const quad = current?.quadCam ?? []
  const points: [number, number][] = quad.length
    ? [
        ...quad.map((p) => [p[0], p[1]] as [number, number]),
        [quad[0][0], quad[0][1]] as [number, number],
      ]
    : []

  const option: EChartsOption = {
    title: { text: '投影区在摄像头画面中的四角', left: 'center' },
    tooltip: { trigger: 'item' },
    grid: { left: 50, right: 20, top: 50, bottom: 40 },
    xAxis: { type: 'value', name: 'x', scale: true },
    yAxis: { type: 'value', name: 'y', inverse: true, scale: true },
    series: [
      {
        type: 'line',
        data: points,
        showSymbol: true,
        symbolSize: 12,
        lineStyle: { width: 2, color: '#1890ff' },
        itemStyle: { color: '#1890ff' },
        label: {
          show: true,
          formatter: (p) => `P${(p.dataIndex ?? 0) + 1}`,
          position: 'top',
        },
      },
    ],
  }

  return (
    <div>
      <Typography.Title level={4}>投影标定</Typography.Title>
      <Typography.Paragraph type="secondary">
        投影仪与摄像头的摆放位置每次都可能变动，因此启动时需要做一次对齐：投影依次打全黑/全白画面，
        摄像头各拍一帧，据此求解投影区到摄像头画面的单应矩阵（homography）。
      </Typography.Paragraph>

      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="标定的作用"
          description="标定后系统才能把投影坐标正确映射到摄像头看到的真实工作台位置，从而精准地把引导光打在取料位上。"
        />

        <Card>
          <Space wrap>
            <Select
              style={{ width: 220 }}
              placeholder="选择摄像头"
              value={selectedCameraId ?? undefined}
              onChange={(v) => setSelectedCameraId(v)}
              options={cameras.map((c) => ({ value: c.id, label: c.name }))}
            />
            <Button type="primary" loading={calibrating} onClick={handleRun}>
              开始标定
            </Button>
          </Space>
        </Card>

        <Card title="当前标定结果">
          <Descriptions column={2} size="small">
            <Descriptions.Item label="标定时间">{current?.createdAt || '—'}</Descriptions.Item>
            <Descriptions.Item label="投影分辨率">
              {current ? current.projSize.join(' × ') : '—'}
            </Descriptions.Item>
            <Descriptions.Item label="投影区面积">
              {current ? String(current.area) : '—'}
            </Descriptions.Item>
            <Descriptions.Item label="是否当前">
              <Tag color={current?.isCurrent ? 'green' : 'default'}>
                {current?.isCurrent ? '是' : '否'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="四角（摄像头坐标）">
              {current && quad.length
                ? quad.map((p, i) => `P${i + 1}(${p[0]}, ${p[1]})`).join('  ')
                : '—'}
            </Descriptions.Item>
          </Descriptions>

          {current?.warning ? (
            <Alert
              style={{ marginTop: 12 }}
              type="error"
              showIcon
              message="此标定不可信，请勿直接用于工序"
              description={`${current.warning}（在此状态下跑工序，取料判定不会触发。）`}
            />
          ) : null}

          <div style={{ marginTop: 16 }}>
            {quad.length ? (
              <ReactECharts option={option} style={{ height: 360 }} notMerge />
            ) : (
              <Empty description="暂无标定四角数据" />
            )}
          </div>
        </Card>

        <Card title="标定自检图">
          <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
            标定完成后自动生成的核对图，用来一眼判断标定到底对不对：
          </Typography.Paragraph>
          <ul style={{ margin: '0 0 12px 20px', color: '#595959', fontSize: 13 }}>
            <li>
              <b>亮区</b>：投影光真正打到的地方（真实投影范围）
            </li>
            <li>
              <b>青色框</b>：标定<b>认为</b>的投影区
            </li>
            <li>
              <b>琥珀色圈</b>：各料位在画面里的真实判定范围（<b>引擎判定用的就是这块</b>）
            </li>
          </ul>
          <Alert
            type={current?.warning ? 'error' : 'success'}
            showIcon
            style={{ marginBottom: 12 }}
            message={
              current?.warning
                ? '判定：不可信 —— 青色框没有压在亮区上，请重新摆位后再次标定'
                : '判定：正常 —— 青色框应与亮区基本重合，琥珀圈应落在对应料位上'
            }
          />
          {current && !overlayFailed ? (
            <img
              src={calibrationOverlayUrl(current.id)}
              alt="标定自检图"
              style={{ width: '100%', maxWidth: 960, borderRadius: 6, border: '1px solid #f0f0f0' }}
              onError={() => setOverlayFailed(true)}
            />
          ) : (
            <Empty
              description={
                current
                  ? '这张标定的过程图已不在磁盘上（或该标定来自旧版本），重新标定一次即可生成'
                  : '还没有标定记录'
              }
            />
          )}
        </Card>

        <Card title="标定历史">
          <Table<Calibration>
            size="small"
            rowKey="id"
            dataSource={list}
            pagination={false}
            columns={[
              {
                title: '标定时间',
                dataIndex: 'createdAt',
                render: (v: string) => (v ? v.slice(0, 19).replace('T', ' ') : '—'),
              },
              {
                title: '摄像头',
                dataIndex: 'cameraId',
                render: (v?: string | null) => v || '—',
              },
              {
                title: '投影分辨率',
                render: (_: unknown, c: Calibration) => c.projSize.join(' × '),
              },
              { title: '投影区面积', dataIndex: 'area' },
              {
                title: '告警',
                dataIndex: 'warning',
                render: (w: string) =>
                  w ? <Tag color="orange">有</Tag> : <Tag color="default">无</Tag>,
              },
              {
                title: '当前',
                dataIndex: 'isCurrent',
                render: (b: boolean) => (
                  <Tag color={b ? 'green' : 'default'}>{b ? '是' : '否'}</Tag>
                ),
              },
            ]}
          />
        </Card>
      </Space>
    </div>
  )
}

export default CalibrationPage
