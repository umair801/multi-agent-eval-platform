'use client'
import { useState, useEffect } from 'react'
import NavBar from '../components/NavBar'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Metrics {
  avg_latency_ms: number
  avg_cost_per_turn_usd: number
  task_success_rate: number
  tool_approval_rate: number
  escalation_rate: number
  total_conversations: number
  total_tool_calls: number
  flagged_conversations: number
}

interface Failures {
  failure_categories: Record<string, number>
  top_failing_intents: Record<string, number>
  total_flagged: number
}

const FAILURE_COLORS = [
  '#dc2626', '#d97706', '#7c3aed', '#0891b2', '#059669', '#475569',
]

const CATEGORY_LABELS: Record<string, string> = {
  hallucination:    'Hallucination',
  missing_tool:     'Missing Tool Call',
  wrong_intent:     'Wrong Intent',
  policy_violation: 'Policy Violation',
  escalation_error: 'Escalation Error',
  none:             'No Failure',
}

function MetricCard({
  label, value, sub, color, icon,
}: {
  label: string; value: string | number; sub?: string; color?: string; icon?: string
}) {
  return (
    <div style={{
      background: '#ffffff', border: '1px solid var(--border)',
      borderRadius: '12px', padding: '20px 24px',
      boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px', fontWeight: 500 }}>
            {label}
          </div>
          <div style={{ fontSize: '28px', fontWeight: 700, color: color || 'var(--text-primary)', lineHeight: 1 }}>
            {value}
          </div>
          {sub && (
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '6px' }}>
              {sub}
            </div>
          )}
        </div>
        {icon && <span style={{ fontSize: '24px', opacity: 0.7 }}>{icon}</span>}
      </div>
    </div>
  )
}

function PieChart({ data, colors }: { data: { label: string; value: number; color: string }[]; colors: string[] }) {
  const total = data.reduce((s, d) => s + d.value, 0)
  if (total === 0) return (
    <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)', fontSize: '13px' }}>
      No failure data yet.
    </div>
  )

  // Simple SVG pie chart
  let cumulative = 0
  const radius = 80
  const cx = 100, cy = 100
  const slices = data.map((d, i) => {
    const pct = d.value / total
    const startAngle = cumulative * 2 * Math.PI - Math.PI / 2
    cumulative += pct
    const endAngle = cumulative * 2 * Math.PI - Math.PI / 2
    const x1 = cx + radius * Math.cos(startAngle)
    const y1 = cy + radius * Math.sin(startAngle)
    const x2 = cx + radius * Math.cos(endAngle)
    const y2 = cy + radius * Math.sin(endAngle)
    const largeArc = pct > 0.5 ? 1 : 0
    return {
      path: `M ${cx} ${cy} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} Z`,
      color: d.color,
      label: d.label,
      value: d.value,
      pct: Math.round(pct * 100),
    }
  })

  return (
    <div style={{ display: 'flex', gap: '32px', alignItems: 'center', flexWrap: 'wrap' }}>
      <svg width="200" height="200" viewBox="0 0 200 200">
        {slices.map((s, i) => (
          <path key={i} d={s.path} fill={s.color} stroke="#ffffff" strokeWidth="2" />
        ))}
        {/* Center hole */}
        <circle cx={cx} cy={cy} r="40" fill="#ffffff" />
        <text x={cx} y={cy - 6} textAnchor="middle" fontSize="18" fontWeight="700" fill="var(--text-primary)">
          {total}
        </text>
        <text x={cx} y={cy + 12} textAnchor="middle" fontSize="9" fill="#94a3b8">
          total
        </text>
      </svg>

      {/* Legend */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {slices.map((s, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '10px', height: '10px', borderRadius: '2px',
              background: s.color, flexShrink: 0,
            }} />
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {s.label}
            </div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-primary)', marginLeft: 'auto', paddingLeft: '16px' }}>
              {s.value} <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>({s.pct}%)</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function BarChart({ data }: { data: { label: string; value: number; color: string }[] }) {
  const max = Math.max(...data.map(d => d.value), 1)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {data.map((d, i) => (
        <div key={i}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{d.label}</span>
            <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-primary)' }}>{d.value}</span>
          </div>
          <div style={{
            height: '8px', background: 'var(--bg-primary)',
            borderRadius: '4px', overflow: 'hidden',
          }}>
            <div style={{
              height: '100%',
              width: `${(d.value / max) * 100}%`,
              background: d.color,
              borderRadius: '4px',
              transition: 'width 0.6s ease',
            }} />
          </div>
        </div>
      ))}
    </div>
  )
}

export default function MetricsPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [failures, setFailures] = useState<Failures | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => { fetchAll() }, [])

  async function fetchAll() {
    setLoading(true)
    try {
      const [mRes, fRes] = await Promise.all([
        fetch(`${API}/api/v1/metrics`),
        fetch(`${API}/api/v1/failures`),
      ])
      const [mData, fData] = await Promise.all([mRes.json(), fRes.json()])
      setMetrics(mData)
      setFailures(fData)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  // Build pie chart data from failure categories
  const pieData = failures
    ? Object.entries(failures.failure_categories)
        .filter(([, v]) => v > 0)
        .map(([k, v], i) => ({
          label: CATEGORY_LABELS[k] || k,
          value: v,
          color: FAILURE_COLORS[i % FAILURE_COLORS.length],
        }))
    : []

  // Build bar chart data from failing intents
  const barData = failures
    ? Object.entries(failures.top_failing_intents)
        .sort(([, a], [, b]) => b - a)
        .map(([k, v], i) => ({
          label: k.replace('_', ' '),
          value: v,
          color: FAILURE_COLORS[i % FAILURE_COLORS.length],
        }))
    : []

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <NavBar />
      <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '32px 24px' }}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '28px' }}>
          <div>
            <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-primary)' }}>
              Platform Metrics
            </h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginTop: '4px' }}>
              Real-time performance metrics and failure analysis across all conversations.
            </p>
          </div>
          <button onClick={fetchAll} style={{
            background: '#ffffff', border: '1px solid var(--border)',
            borderRadius: '8px', padding: '8px 16px',
            fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)',
            cursor: 'pointer', fontFamily: 'inherit',
          }}>
            ↻ Refresh
          </button>
        </div>

        {loading && (
          <div style={{ textAlign: 'center', padding: '80px', color: 'var(--text-muted)', fontSize: '13px' }}>
            Loading metrics...
          </div>
        )}

        {!loading && metrics && (
          <>
            {/* KPI Grid */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: '12px',
              marginBottom: '28px',
            }}>
              <MetricCard
                label="Total Conversations"
                value={metrics.total_conversations}
                icon="💬"
              />
              <MetricCard
                label="Task Success Rate"
                value={`${(metrics.task_success_rate * 100).toFixed(1)}%`}
                color={metrics.task_success_rate >= 0.7 ? '#059669' : metrics.task_success_rate >= 0.5 ? '#d97706' : '#dc2626'}
                icon="✅"
                sub={metrics.task_success_rate >= 0.7 ? 'Good' : metrics.task_success_rate >= 0.5 ? 'Needs improvement' : 'Critical'}
              />
              <MetricCard
                label="Avg Latency"
                value={`${Math.round(metrics.avg_latency_ms)}ms`}
                color={metrics.avg_latency_ms < 5000 ? '#059669' : '#d97706'}
                icon="⚡"
              />
              <MetricCard
                label="Avg Cost / Turn"
                value={`$${metrics.avg_cost_per_turn_usd.toFixed(4)}`}
                icon="💰"
              />
            </div>

            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: '12px',
              marginBottom: '32px',
            }}>
              <MetricCard
                label="Total Tool Calls"
                value={metrics.total_tool_calls}
                icon="⚙️"
              />
              <MetricCard
                label="Tool Approval Rate"
                value={`${(metrics.tool_approval_rate * 100).toFixed(1)}%`}
                color="#2563eb"
                icon="🔐"
              />
              <MetricCard
                label="Escalation Rate"
                value={`${(metrics.escalation_rate * 100).toFixed(1)}%`}
                color={metrics.escalation_rate > 0.2 ? '#dc2626' : '#475569'}
                icon="🚨"
              />
              <MetricCard
                label="Flagged Conversations"
                value={metrics.flagged_conversations}
                color={metrics.flagged_conversations > 0 ? '#d97706' : '#059669'}
                icon="🚩"
              />
            </div>

            {/* Charts row */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '28px' }}>

              {/* Failure category pie */}
              <div style={{
                background: '#ffffff', border: '1px solid var(--border)',
                borderRadius: '12px', padding: '24px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
              }}>
                <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
                  Failure Categories
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '20px' }}>
                  Distribution of flagged conversation failure types
                </div>
                <PieChart data={pieData} colors={FAILURE_COLORS} />
              </div>

              {/* Top failing intents bar chart */}
              <div style={{
                background: '#ffffff', border: '1px solid var(--border)',
                borderRadius: '12px', padding: '24px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
              }}>
                <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
                  Top Failing Intents
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '20px' }}>
                  Failed conversation count by intent category
                </div>
                {barData.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)', fontSize: '13px' }}>
                    No failed conversations yet.
                  </div>
                ) : (
                  <BarChart data={barData} />
                )}
              </div>
            </div>

            {/* Health summary */}
            <div style={{
              background: '#ffffff', border: '1px solid var(--border)',
              borderRadius: '12px', padding: '20px 24px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}>
              <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '16px' }}>
                System Health Summary
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {[
                  {
                    label: 'Task Success Rate',
                    ok: metrics.task_success_rate >= 0.6,
                    detail: `${(metrics.task_success_rate * 100).toFixed(1)}% — target ≥ 60%`,
                  },
                  {
                    label: 'Average Latency',
                    ok: metrics.avg_latency_ms < 10000,
                    detail: `${Math.round(metrics.avg_latency_ms)}ms — target < 10,000ms`,
                  },
                  {
                    label: 'Cost Efficiency',
                    ok: metrics.avg_cost_per_turn_usd < 0.05,
                    detail: `$${metrics.avg_cost_per_turn_usd.toFixed(4)} per turn — target < $0.05`,
                  },
                  {
                    label: 'Flagged Rate',
                    ok: (metrics.flagged_conversations / Math.max(metrics.total_conversations, 1)) < 0.3,
                    detail: `${metrics.flagged_conversations} of ${metrics.total_conversations} conversations flagged`,
                  },
                ].map((item, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: '12px',
                    padding: '10px 14px',
                    background: 'var(--bg-primary)', borderRadius: '8px',
                  }}>
                    <span style={{ fontSize: '14px' }}>{item.ok ? '✅' : '⚠️'}</span>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', minWidth: '180px' }}>
                      {item.label}
                    </span>
                    <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {item.detail}
                    </span>
                    <span style={{
                      marginLeft: 'auto',
                      fontSize: '11px', fontWeight: 700,
                      padding: '2px 8px', borderRadius: '4px',
                      background: item.ok ? '#ecfdf5' : '#fffbeb',
                      color: item.ok ? '#059669' : '#d97706',
                    }}>
                      {item.ok ? 'PASS' : 'WARN'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}