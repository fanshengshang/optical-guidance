import { useEffect, useState } from 'react'
import { Alert, Button, Card, Popconfirm, Space, Spin, Typography, message } from 'antd'
import GuideConfigForm from '../components/GuideConfigForm'
import { settingsApi } from '../services/api'
import type { GuideConfig, GuideFieldMeta, GuideSettings } from '../types'

function errDetail(err: unknown): string {
  const d = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return d ? String(d) : '操作失败，请稍后重试'
}

const SettingsPage: React.FC = () => {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [fields, setFields] = useState<GuideFieldMeta[]>([])
  const [config, setConfig] = useState<GuideConfig>({})
  const [dirty, setDirty] = useState(false)

  const apply = (data: GuideSettings) => {
    setFields(data.fields ?? [])
    setConfig(data.config ?? {})
    setDirty(false)
  }

  const load = async () => {
    setLoading(true)
    try {
      const res = await settingsApi.getGuide()
      apply(res.data as GuideSettings)
    } catch (err) {
      message.error(errDetail(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await settingsApi.saveGuide(config)
      apply(res.data as GuideSettings)
      message.success('已保存全局引导参数（下次启动工序生效）')
    } catch (err) {
      message.error(errDetail(err))
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    setSaving(true)
    try {
      const res = await settingsApi.resetGuide()
      apply(res.data as GuideSettings)
      message.success('已恢复内置默认参数')
    } catch (err) {
      message.error(errDetail(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <Typography.Title level={4}>系统设置</Typography.Title>
      <Typography.Paragraph type="secondary">
        这里是<strong>全局默认</strong>引导参数，对所有工序生效。单个工序可在「工序编排」里开启
        <strong> 自定义参数</strong> 来单独覆盖，覆盖后该工序不再跟随这里的设置。
      </Typography.Paragraph>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        title="参数由后端字段定义驱动"
        description="新增 / 调整可配项在后端 core/guide_config.py 的 FIELDS 里声明，本页会自动出现对应控件，无需改前端。"
      />

      <Card
        title="引导参数"
        extra={
          <Space>
            <Popconfirm
              title="恢复默认？"
              description="将清除已保存的全局覆盖值，回到内置默认。"
              okText="恢复"
              cancelText="取消"
              onConfirm={handleReset}
            >
              <Button disabled={loading || saving}>恢复默认</Button>
            </Popconfirm>
            <Button
              type="primary"
              loading={saving}
              disabled={loading || !dirty}
              onClick={handleSave}
            >
              保存
            </Button>
          </Space>
        }
      >
        {loading ? (
          <div style={{ padding: 32, textAlign: 'center' }}>
            <Spin />
          </div>
        ) : (
          <>
            <GuideConfigForm
              fields={fields}
              value={config}
              onChange={(next) => {
                setConfig(next)
                setDirty(true)
              }}
            />
            {dirty && (
              <Typography.Text type="warning" style={{ display: 'block', marginTop: 12 }}>
                有未保存的修改
              </Typography.Text>
            )}
            <Typography.Text type="secondary" style={{ display: 'block', marginTop: 12, fontSize: 12 }}>
              提示：鼠标悬停在参数名上可查看说明。运行中修改不会打断当前工序，下次启动生效。
            </Typography.Text>
          </>
        )}
      </Card>
    </div>
  )
}

export default SettingsPage
