import { Divider, InputNumber, Switch, Tooltip, Typography } from 'antd'
import type { GuideConfig, GuideFieldMeta } from '../types'

/**
 * 引导参数表单：完全由后端字段元信息（core/guide_config.py 的 FIELDS）驱动渲染。
 * 新增一个可配项 = 后端 FIELDS 加一条，这里/设置页无需改动。
 *
 * 键名约定：后端是 snake_case，经 api.ts 拦截器转成 camelCase，
 * 所以这里用 camel(field.key) 取值 / 写值。
 */
export const keyToCamel = (key: string) =>
  key.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase())

const GROUPS_ORDER = ['引导动画', '判定', '检错']

interface Props {
  fields: GuideFieldMeta[]
  value: GuideConfig
  onChange: (next: GuideConfig) => void
  disabled?: boolean
}

const GuideConfigForm: React.FC<Props> = ({ fields, value, onChange, disabled }) => {
  const set = (key: string, v: boolean | number) => onChange({ ...value, [key]: v })

  // 按 group 归组，未在 GROUPS_ORDER 里的排后面
  const groups = Array.from(new Set(fields.map((f) => f.group)))
  groups.sort((a, b) => {
    const ia = GROUPS_ORDER.indexOf(a)
    const ib = GROUPS_ORDER.indexOf(b)
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
  })

  return (
    <div>
      {groups.map((g, gi) => (
        <div key={g}>
          {gi > 0 && <Divider style={{ margin: '12px 0' }} />}
          <Typography.Text strong style={{ fontSize: 13 }}>
            {g}
          </Typography.Text>
          <div style={{ marginTop: 8 }}>
            {fields
              .filter((f) => f.group === g)
              .map((f) => {
                const k = keyToCamel(f.key)
                const cur = value[k]
                return (
                  <div
                    key={f.key}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      padding: '6px 0',
                    }}
                  >
                    <Tooltip title={f.doc}>
                      <span
                        style={{
                          flex: 1,
                          minWidth: 0,
                          color: '#595959',
                          cursor: 'help',
                          borderBottom: '1px dashed #d9d9d9',
                        }}
                      >
                        {f.doc}
                      </span>
                    </Tooltip>
                    {f.type === 'bool' ? (
                      <Switch
                        size="small"
                        checked={Boolean(cur)}
                        disabled={disabled}
                        onChange={(v) => set(k, v)}
                      />
                    ) : (
                      <InputNumber
                        size="small"
                        style={{ width: 120 }}
                        value={cur as number}
                        min={f.min}
                        max={f.max}
                        step={f.type === 'int' ? 1 : 0.01}
                        disabled={disabled}
                        onChange={(v) => {
                          if (v === null || v === undefined) return
                          set(k, f.type === 'int' ? Math.round(Number(v)) : Number(v))
                        }}
                      />
                    )}
                  </div>
                )
              })}
          </div>
        </div>
      ))}
    </div>
  )
}

export default GuideConfigForm
