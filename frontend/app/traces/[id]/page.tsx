'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import NavBar from '../../components/NavBar'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface TraceStep {
  id: string
  agent_name: string
  step_type: string
  prompt_text: string
  model_response: string
  tool_name: string
  tool_input: Record<string, unknown>
  tool_output: Record<string, unknown>
  latency_ms: number
  token_count_input: number
  token_count_output: number
  cost_usd: number
  error: string
  timestamp: string
}

interface Conversation {
  id: string
  user_message: string
  intent: string
  outcome: string
  total_cost_usd: number
  total_latency_ms: number
  created_at: string
}

const STEP_TYPE_CONFIG: Record<string, { color: string; bg: string; icon: string }> = {
  prompt_sent:        { color: '#2563eb', bg: '#eff6ff',  icon: '→' },
  model_response:     { color: '#059669', bg: '#ecfdf5',  icon: '◎' },
  tool_call:          { color: '#d97706', bg: '#fffbeb',  icon: '⚙' },
  tool_result:        { color: '#7c3aed', bg: '#f5f3ff',  icon: '✓' },
  routing_decision:   { color: '#0891b2', bg: '#ecfeff',  icon: '⇢' },
}

const AGENT_COLORS: Record<string, string> = {
  router_agent:       '#2563eb',
  billing_agent:      '#059669',
  policy_agent:       '#7c3aed',
  tool_executor_agent:'#d97706',
  response_agent:     '#0891b2',
  eval_safety_agent:  '#dc2626',
}

export default function TraceDetailPage({ params }: { params: { id: string } }) {
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [steps, setSteps] = useState<TraceStep[]>([])
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [replaying, setReplaying] = useState(false)
  const [replayResult, setReplayResult] = useState<string>('')

  useEffect(() => { fetchTrace() }, [])

  async function fetchTrace() {
    try {
      const res = await fetch(`${API}/api/v1/conversations/${params.id}/trace`)
      const data = await res.json()
      setConversation(data.conversation)
      setSteps(data.steps || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function replayConversation() {
    if (!conversation) return
    setReplaying(true)
    setReplayResult('')
    try {
      const res = await fetch(`${API}/api/v1/conversations/${params.id}/replay`, {
        method: 'POST',
      })
      const data = await res.json()
      setReplayResult(data.response || data.final_response || 'Replay complete.')
    } catch (e) {
      setReplayResult('Replay failed. Check backend logs.')
    } finally {
      setReplaying(false)
    }
  }

  function toggleExpand(id: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  if (loading) return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <NavBar />
      <div style={{ textAlign: 'center', padding: '80px', color: 'var(--text-muted)' }}>
        Loading trace...
      </div>
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <NavBar />
      <div style={{ maxWidth: '960px', margin: '0 auto', padding: '32px 24px' }}>

        {/* Back link */}
        <Link href="/traces" style={{
          fontSize: '13px', color: 'var(--accent-blue)',
          textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '4px',
          marginBottom: '20px',
        }}>
          ← Back to traces
        </Link>

        {/* Conversation summary */}
        {conversation && (
          <div style={{
            background: '#ffffff', border: '1px solid var(--border)',
            borderRadius: '12px', padding: '20px 24px',
            marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px', letterSpacing: '0.04em' }}>
                  USER MESSAGE
                </div>
                <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '12px' }}>
                  "{conversation.user_message}"
                </div>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '4px', background: '#eff6ff', color: '#2563eb', fontWeight: 600 }}>
                    {conversation.intent?.replace('_', ' ') || 'unknown'}
                  </span>
                  <span style={{
                    fontSize: '11px', padding: '2px 8px', borderRadius: '4px', fontWeight: 600,
                    background: conversation.outcome === 'resolved' ? '#ecfdf5' : conversation.outcome === 'flagged' ? '#fffbeb' : '#fef2f2',
                    color: conversation.outcome === 'resolved' ? '#059669' : conversation.outcome === 'flagged' ? '#d97706' : '#dc2626',
                  }}>
                    {conversation.outcome}
                  </span>
                  {conversation.total_latency_ms && (
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {Math.round(conversation.total_latency_ms)}ms
                    </span>
                  )}
                  {conversation.total_cost_usd && (
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      ${conversation.total_cost_usd.toFixed(5)}
                    </span>
                  )}
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {steps.length} steps
                  </span>
                </div>
              </div>

              {/* Replay button */}
              <button onClick={replayConversation} disabled={replaying} style={{
                background: replaying ? 'var(--bg-hover)' : 'var(--accent-blue)',
                color: replaying ? 'var(--text-muted)' : '#ffffff',
                border: 'none', borderRadius: '8px',
                padding: '10px 20px', fontSize: '13px', fontWeight: 600,
                cursor: replaying ? 'not-allowed' : 'pointer',
                fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: '8px',
                whiteSpace: 'nowrap',
              }}>
                {replaying ? '⟳ Replaying...' : '▶ Replay'}
              </button>
            </div>

            {/* Replay result */}
            {replayResult && (
              <div style={{
                marginTop: '16px', padding: '14px 16px',
                background: 'var(--bg-primary)', border: '1px solid var(--border)',
                borderRadius: '8px', fontSize: '13px', color: 'var(--text-primary)',
              }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px', fontWeight: 600 }}>
                  REPLAY RESULT
                </div>
                {replayResult}
              </div>
            )}
          </div>
        )}

        {/* Steps */}
        <div style={{ marginBottom: '8px', fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.06em' }}>
          AGENT TRACE — {steps.length} STEPS
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {steps.map((step, i) => {
            const stc = STEP_TYPE_CONFIG[step.step_type] || { color: '#475569', bg: '#f8fafc', icon: '•' }
            const agentColor = AGENT_COLORS[step.agent_name] || '#475569'
            const isExpanded = expanded.has(step.id || String(i))
            const hasDetail = step.prompt_text || step.model_response || step.tool_input || step.tool_output || step.error

            return (
              <div key={step.id || i} style={{
                background: '#ffffff', border: '1px solid var(--border)',
                borderRadius: '10px', overflow: 'hidden',
                boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
              }}>
                {/* Step header */}
                <div
                  onClick={() => hasDetail && toggleExpand(step.id || String(i))}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '12px',
                    padding: '12px 16px',
                    cursor: hasDetail ? 'pointer' : 'default',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => hasDetail && ((e.currentTarget as HTMLElement).style.background = 'var(--bg-primary)')}
                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = '#ffffff'}
                >
                  {/* Step number */}
                  <div style={{
                    width: '24px', height: '24px', borderRadius: '50%',
                    background: 'var(--bg-primary)', border: '1px solid var(--border)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '10px', fontWeight: 700, color: 'var(--text-muted)',
                    flexShrink: 0,
                  }}>
                    {i + 1}
                  </div>

                  {/* Agent badge */}
                  <span style={{
                    fontSize: '11px', fontWeight: 700,
                    padding: '2px 8px', borderRadius: '4px',
                    background: `${agentColor}12`,
                    color: agentColor,
                    whiteSpace: 'nowrap',
                  }}>
                    {step.agent_name?.replace('_agent', '').replace('_', ' ') || 'unknown'}
                  </span>

                  {/* Step type badge */}
                  <span style={{
                    fontSize: '11px', fontWeight: 600,
                    padding: '2px 8px', borderRadius: '4px',
                    background: stc.bg, color: stc.color,
                    whiteSpace: 'nowrap',
                  }}>
                    {stc.icon} {step.step_type?.replace('_', ' ') || 'unknown'}
                  </span>

                  {/* Tool name */}
                  {step.tool_name && (
                    <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {step.tool_name}
                    </span>
                  )}

                  {/* Error indicator */}
                  {step.error && (
                    <span style={{
                      fontSize: '11px', padding: '2px 8px', borderRadius: '4px',
                      background: '#fef2f2', color: '#dc2626', fontWeight: 600,
                    }}>
                      ✕ error
                    </span>
                  )}

                  {/* Metrics */}
                  <div style={{ marginLeft: 'auto', display: 'flex', gap: '12px', alignItems: 'center' }}>
                    {step.latency_ms && (
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        {Math.round(step.latency_ms)}ms
                      </span>
                    )}
                    {step.cost_usd && (
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        ${step.cost_usd.toFixed(5)}
                      </span>
                    )}
                    {hasDetail && (
                      <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {isExpanded ? '▲' : '▼'}
                      </span>
                    )}
                  </div>
                </div>

                {/* Expanded detail */}
                {isExpanded && hasDetail && (
                  <div style={{
                    borderTop: '1px solid var(--border-subtle)',
                    padding: '16px',
                    background: 'var(--bg-primary)',
                    display: 'flex', flexDirection: 'column', gap: '12px',
                  }}>
                    {step.error && (
                      <DetailBlock label="ERROR" value={step.error} color="#dc2626" bg="#fef2f2" />
                    )}
                    {step.prompt_text && (
                      <DetailBlock label="PROMPT SENT" value={step.prompt_text} />
                    )}
                    {step.model_response && (
                      <DetailBlock label="MODEL RESPONSE" value={step.model_response} />
                    )}
                    {step.tool_input && (
                      <DetailBlock label="TOOL INPUT" value={JSON.stringify(step.tool_input, null, 2)} mono />
                    )}
                    {step.tool_output && (
                      <DetailBlock label="TOOL OUTPUT" value={JSON.stringify(step.tool_output, null, 2)} mono />
                    )}
                    {(step.token_count_input || step.token_count_output) && (
                      <div style={{ display: 'flex', gap: '16px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          Tokens in: <strong style={{ color: 'var(--text-secondary)' }}>{step.token_count_input}</strong>
                        </span>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          Tokens out: <strong style={{ color: 'var(--text-secondary)' }}>{step.token_count_output}</strong>
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {steps.length === 0 && !loading && (
          <div style={{
            background: '#ffffff', border: '1px solid var(--border)',
            borderRadius: '12px', padding: '48px',
            textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px',
          }}>
            No trace steps found for this conversation.
          </div>
        )}
      </div>
    </div>
  )
}

function DetailBlock({
  label, value, mono = false, color, bg,
}: {
  label: string; value: string; mono?: boolean; color?: string; bg?: string
}) {
  return (
    <div>
      <div style={{ fontSize: '10px', fontWeight: 700, color: color || 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: '6px' }}>
        {label}
      </div>
      <pre style={{
        fontSize: '12px',
        color: color || 'var(--text-primary)',
        background: bg || '#ffffff',
        border: '1px solid var(--border)',
        borderRadius: '6px',
        padding: '10px 12px',
        overflowX: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        fontFamily: mono ? 'var(--font-mono, monospace)' : 'inherit',
        lineHeight: '1.6',
        margin: 0,
      }}>
        {value}
      </pre>
    </div>
  )
}