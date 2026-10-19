import { useEffect, useRef, useState } from 'react'
import { projectorApi } from '../services/api'
import type { ProjectorState, ProjectorTarget } from '../types'

/**
 * 投影页：全屏铺到副屏（由启动脚本用浏览器 kiosk 模式打开）。
 * 按固定节奏拉取后端状态并渲染 —— 标定的全黑/全白、运行时的红绿引导都只是不同的 mode。
 *
 * 引导动画（脉冲 / 进度环 / 箭头）全部由后端下发的有效配置驱动，
 * 管理人员可在「系统设置 / 工序编排」里开关，前端不含写死参数。
 */
const POLL_MS = 60

const FILL: Record<string, string> = {
  green: 'rgba(22,163,74,0.95)',
  red: 'rgba(220,38,38,0.95)',
  hint: 'rgba(37,99,235,0.85)',
  warn: 'rgba(120,53,15,0.75)',
}
const STROKE: Record<string, string> = {
  green: '#22c55e',
  red: '#dc2626',
  hint: '#3b82f6',
  warn: '#f59e0b',
}

/** 与后端 Target.contains 一致的命中判定（用于把进度环画在手所在的那一格）。 */
const contains = (t: ProjectorTarget, x: number, y: number) =>
  t.shape === 'rect'
    ? Math.abs(x - t.x) <= t.w / 2 && Math.abs(y - t.y) <= t.h / 2
    : (x - t.x) ** 2 + (y - t.y) ** 2 <= t.r ** 2

const targetRadius = (t: ProjectorTarget) =>
  t.shape === 'rect' ? Math.max(t.w, t.h) / 2 : t.r

const ProjectorPage: React.FC = () => {
  const [state, setState] = useState<ProjectorState | null>(null)
  const [viewport, setViewport] = useState({
    w: window.innerWidth,
    h: window.innerHeight,
  })
  const seqRef = useRef(-1)

  useEffect(() => {
    let alive = true
    let timer: number | undefined

    const tick = async () => {
      try {
        const res = await projectorApi.state()
        const next = res.data as ProjectorState
        if (alive && next.seq !== seqRef.current) {
          seqRef.current = next.seq
          setState(next)
        }
      } catch {
        if (alive) {
          setState((prev) =>
            prev ?? {
              mode: 'error',
              projSize: [1024, 768],
              targets: [],
              colors: {},
              stepIndex: 0,
              stepTotal: 0,
              stepText: '',
              handXy: null,
              progress: null,
              flash: null,
              message: '后端未连接',
              seq: -1,
              pulseEnabled: true,
              pulsePeriodMs: 1200,
              ringEnabled: true,
              arrowEnabled: false,
            },
          )
        }
      } finally {
        if (alive) timer = window.setTimeout(tick, POLL_MS)
      }
    }
    void tick()

    const onResize = () => setViewport({ w: window.innerWidth, h: window.innerHeight })
    window.addEventListener('resize', onResize)
    return () => {
      alive = false
      if (timer) window.clearTimeout(timer)
      window.removeEventListener('resize', onResize)
    }
  }, [])

  const projSize = state?.projSize ?? [1024, 768]
  const [pw, ph] = projSize
  const scale = Math.min(viewport.w / (pw || 1024), viewport.h / (ph || 768)) || 1

  const mode = state?.mode ?? 'idle'
  // 相机掉线：判定区置灰、不再显示过期引导
  const stale = mode === 'guide_stale'
  // 待机时后端也用 guide 模式渲染料位轮廓（方便摆位），此时不该显示「模式 guide」
  const standby = !state || state.stepTotal === 0

  useEffect(() => {
    document.body.classList.add('projector-body')
    return () => document.body.classList.remove('projector-body')
  }, [])

  if (mode === 'black') {
    return <div style={{ position: 'fixed', inset: 0, background: '#000' }} />
  }
  if (mode === 'white') {
    return <div style={{ position: 'fixed', inset: 0, background: '#fff' }} />
  }
  // 开始/结束提示：全屏大字
  if (mode === 'announce' && state?.announce) {
    const tone = state.announce.tone === 'end' ? '#16a34a' : '#2563eb'
    return (
      <div
        style={{
          position: 'fixed',
          inset: 0,
          background: '#0d1013',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            maxWidth: '86%',
            textAlign: 'center',
            color: tone,
            fontSize: 72,
            fontWeight: 700,
            letterSpacing: 6,
            lineHeight: 1.35,
          }}
        >
          {state.announce.text}
        </div>
      </div>
    )
  }

  const flashColor =
    state?.flash === 'green'
      ? '#16a34a'
      : state?.flash === 'red'
        ? '#dc2626'
        : state?.flash === 'warn'
          ? '#f59e0b'
          : null

  const targets = state?.targets ?? []
  const colors = state?.colors ?? {}
  const hand = state?.handXy ?? null
  const progress = state?.progress ?? null
  const pulseMs = state?.pulsePeriodMs ?? 1200
  const ringOn = Boolean(state?.ringEnabled)
  const pulseOn = Boolean(state?.pulseEnabled)
  const arrowOn = Boolean(state?.arrowEnabled)

  // 手当前落在的取料位（进度环画在这一格上）
  const handTarget = hand ? targets.find((t) => contains(t, hand[0], hand[1])) : undefined

  // 引导箭头：固定在「当前该取」那一格的正上方，竖直向下指（不跟随手）
  const wantTarget = targets.find((t) => colors[t.id] === 'hint')
  const arrow =
    arrowOn && wantTarget
      ? (() => {
          const r = targetRadius(wantTarget)
          const tipY = wantTarget.y - r - 14          // 终点停在料位顶部边缘上方
          const topY = tipY - 64                     // 箭头总长 64
          return { x1: wantTarget.x, y1: topY, x2: wantTarget.x, y2: tipY }
        })()
      : null

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: '#0d1013',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: pw,
          height: ph,
          position: 'relative',
          transform: `scale(${scale})`,
          transformOrigin: 'center center',
          flex: '0 0 auto',
        }}
      >
        {/* 顶部步骤条 */}
        {state?.stepText && (
          <div
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              top: 44,
              textAlign: 'center',
              color: '#e5e7eb',
              fontSize: 30,
              fontWeight: 700,
              letterSpacing: 2,
            }}
          >
            {state.stepText}
          </div>
        )}

        {/* 引导提示词：管理人员在工序步骤里填的动作说明，大字号醒目显示 */}
        {!standby && state?.instruction && (
          <div
            style={{
              position: 'absolute',
              left: 40,
              right: 40,
              top: 96,
              textAlign: 'center',
              color: '#fde68a',
              fontSize: 40,
              fontWeight: 700,
              letterSpacing: 1,
              lineHeight: 1.3,
            }}
          >
            {state.instruction}
          </div>
        )}

        {/* 取料位 */}
        {targets.map((t) => {
          const c = stale ? null : (colors[t.id] ?? null)
          const fill = (c && FILL[c]) || 'transparent'
          const stroke = stale ? '#4b5563' : ((c && STROKE[c]) || t.color || '#3f4650')
          const isCurrent = !stale && c === 'hint'
          const pulse = pulseOn && isCurrent
          const wrapperStyle: React.CSSProperties = pulse
            ? { animation: `og-pulse ${pulseMs}ms ease-in-out infinite` }
            : {}
          return (
            <div
              key={t.id}
              style={{ position: 'absolute', left: 0, top: 0, ...wrapperStyle }}
            >
              {t.shape === 'rect' ? (
                <div
                  style={{
                    position: 'absolute',
                    left: t.x - t.w / 2,
                    top: t.y - t.h / 2,
                    width: t.w,
                    height: t.h,
                    background: fill,
                    border: `5px solid ${stroke}`,
                    borderRadius: 10,
                  }}
                />
              ) : (
                <div
                  style={{
                    position: 'absolute',
                    left: t.x - t.r,
                    top: t.y - t.r,
                    width: t.r * 2,
                    height: t.r * 2,
                    background: fill,
                    border: `5px solid ${stroke}`,
                    borderRadius: '50%',
                  }}
                />
              )}
              <div
                style={{
                  position: 'absolute',
                  left: t.x - 120,
                  top: (t.shape === 'rect' ? t.y + t.h / 2 : t.y + t.r) + 14,
                  width: 240,
                  textAlign: 'center',
                  color: '#cbd5e1',
                  fontSize: 22,
                }}
              >
                {t.name}
              </div>
            </div>
          )
        })}

        {/* 取流异常：判定区已置灰，中央醒目提示，别让工人误以为还在引导 */}
        {stale && (
          <div
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              top: '42%',
              textAlign: 'center',
              color: '#f59e0b',
              fontSize: 44,
              fontWeight: 700,
              letterSpacing: 4,
            }}
          >
            取流异常 · 引导已暂停
          </div>
        )}

        {/* 进度环 + 引导箭头（单层 SVG 覆盖在料位之上） */}
        {(ringOn || arrow) && (
          <svg
            width={pw}
            height={ph}
            style={{ position: 'absolute', left: 0, top: 0, pointerEvents: 'none' }}
          >
            <defs>
              <marker
                id="og-arrow"
                markerWidth="10"
                markerHeight="10"
                refX="7"
                refY="5"
                orient="auto"
              >
                <path d="M0,0 L10,5 L0,10 z" fill="#38bdf8" />
              </marker>
            </defs>

            {/* 停留进度环：手停在当前料位上，环走满即判定拿对 */}
            {ringOn && handTarget && progress != null && (
              (() => {
                const r = targetRadius(handTarget) + 10
                const C = 2 * Math.PI * r
                const p = Math.max(0, Math.min(1, progress))
                return (
                  <>
                    <circle
                      cx={handTarget.x}
                      cy={handTarget.y}
                      r={r}
                      fill="none"
                      stroke="rgba(148,163,184,0.35)"
                      strokeWidth={7}
                    />
                    <circle
                      cx={handTarget.x}
                      cy={handTarget.y}
                      r={r}
                      fill="none"
                      stroke="#22c55e"
                      strokeWidth={7}
                      strokeLinecap="round"
                      strokeDasharray={`${C * p} ${C}`}
                      transform={`rotate(-90 ${handTarget.x} ${handTarget.y})`}
                    />
                  </>
                )
              })()
            )}

            {/* 引导箭头：手 -> 当前该取的料位 */}
            {arrow && (
              <line
                x1={arrow.x1}
                y1={arrow.y1}
                x2={arrow.x2}
                y2={arrow.y2}
                stroke="#38bdf8"
                strokeWidth={6}
                strokeLinecap="round"
                markerEnd="url(#og-arrow)"
                opacity={0.9}
              />
            )}
          </svg>
        )}

        {/* 手的位置：落在判定区内 -> 绿；没命中 -> 淡灰
            （progress 只有手落在某个料位上时才有值，所以可用来判断"命中与否"） */}
        {state?.handXy && (
          <div
            style={{
              position: 'absolute',
              left: state.handXy[0] - 14,
              top: state.handXy[1] - 14,
              width: 28,
              height: 28,
              border: `3px solid ${progress != null ? '#22c55e' : 'rgba(255,255,255,0.35)'}`,
              borderRadius: '50%',
            }}
          />
        )}

        {/* 底部状态 */}
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: 20,
            textAlign: 'center',
            color: '#6b7280',
            fontSize: 18,
          }}
        >
          {standby
            ? state?.message || '等待启动'
            : `步骤 ${state?.stepIndex != null ? state.stepIndex + 1 : 1}/${state?.stepTotal ?? 0} · ${state?.message ?? ''}`}
        </div>

        {/* 判定闪边 */}
        {flashColor && (
          <div
            style={{
              position: 'absolute',
              left: 0,
              top: 0,
              right: 0,
              height: 14,
              background: flashColor,
              animation: 'og-flash 450ms ease-out forwards',
            }}
          />
        )}
      </div>
    </div>
  )
}

export default ProjectorPage
