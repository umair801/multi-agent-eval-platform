'use client'
import { useState, useEffect } from 'react'
import NavBar from '../components/NavBar'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Approval {
  id: string
  conversation_id: string
  tool_name: string
  tool_input: Record<string, unknown>
  risk_level: string
  status: string
  created_at: string
  reviewed_by?: string
  rejection_reason?: string
}

const TOOL_CONFIG: Record<string, { icon: string; color: string; bg: string; label: string }> = {
  create_refund_ticket:  { icon: '💰', color: '#d97706', bg: '#fffbeb', label: 'Refund Ticket' },
  escalate_to_human:     { icon: '🚨', color: '#dc2626', bg: '#fef2f2', label: 'Escalation' },
}

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string>('')
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' } | null>(null)

  useEffect(() => { fetchApprovals() }, [])

  async function fetchApprovals() {
    try {
      const res = await fetch(`${API}/api/v1/approvals`)
      const data = await res.json()
      setApprovals(data.pending_approvals || [])
    } catch {
      showToast('Failed to load approvals.', 'error')
    } finally {
      setLoading(false)
    }
  }

  function showToast(msg: string, type: 'success' | 'error') {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  async function handleApprove(id: string) {
    setActionLoading(id + '_approve')
    try {
      const res = await fetch(`${API}/api/v1/approvals/${id}/approve`, { method: 'POST' })
      if (res.ok) {
        showToast('Tool call approved and executed.', 'success')
        setApprovals(prev => prev.filter(a => a.id !== id))
      } else {
        showToast('Approval failed. Check backend logs.', 'error')
      }
    } catch {
      showToast('Network error.', 'error')
    } finally {
      setActionLoading('')
    }
  }

  async function handleReject(id: string) {
    setActionLoading(id + '_reject')
    try {
      const res = await fetch(
        `${API}/api/v1/approvals/${id}/reject?rejection_reason=Rejected+by+reviewer`,
        { method: 'POST' }
      )
      if (res.ok) {
        showToast('Tool call rejected.', 'success')
        setApprovals(prev => prev.filter(a => a.id !== id))
      } else {
        showToast('Rejection failed. Check backend logs.', 'error')
      }
    } catch {
      showToast('Network error.', 'error')
    } finally {
      setActionLoading('')
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <NavBar />

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', top: '72px', right: '24px', zIndex: 999,
          background: toast.type === 'success' ? '#ecfdf5' : '#fef2f2',
          border: `1px solid ${toast.type === 'success' ? 'rgba(5,150,105,0.3)' : 'rgba(220,38,38,0.3)'}`,
          color: toast.type === 'success' ? '#059669' : '#dc2626',
          borderRadius: '8px', padding: '12px 20px',
          fontSize: '13px', fontWeight: 600,
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
        }}>
          {toast.type === 'success' ? '✓' : '✕'} {toast.msg}
        </div>
      )}

      <div style={{ maxWidth: '960px', margin: '0 auto', padding: '32px 24px' }}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '28px' }}>
          <div>
            <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-primary)' }}>
              Human Approval Queue
            </h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginTop: '4px' }}>
              HIGH risk tool calls paused for human review before execution.
            </p>
          </div>
          <button onClick={fetchApprovals} style={{
            background: '#ffffff', border: '1px solid var(--border)',
            borderRadius: '8px', padding: '8px 16px',
            fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)',
            cursor: 'pointer', fontFamily: 'inherit',
          }}>
            ↻ Refresh
          </button>
        </div>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '28px' }}>
          {[
            { label: 'Pending Approvals', value: approvals.length, color: '#d97706' },
            { label: 'Refund Tickets', value: approvals.filter(a => a.tool_name === 'create_refund_ticket').length, color: '#2563eb' },
            { label: 'Escalations', value: approvals.filter(a => a.tool_name === 'escalate_to_human').length, color: '#dc2626' },
          ].map((s, i) => (
            <div key={i} style={{
              background: '#ffffff', border: '1px solid var(--border)',
              borderRadius: '10px', padding: '16px 20px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}>
              <div style={{ fontSize: '28px', fontWeight: 700, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* How it works callout */}
        <div style={{
          background: '#eff6ff', border: '1px solid rgba(37,99,235,0.2)',
          borderRadius: '10px', padding: '14px 18px',
          marginBottom: '24px',
          display: 'flex', gap: '12px', alignItems: 'flex-start',
        }}>
          <span style={{ fontSize: '16px', flexShrink: 0 }}>🔒</span>
          <div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#2563eb', marginBottom: '3px' }}>
              Safe Tool Gateway — Human-in-the-Loop
            </div>
            <div style={{ fontSize: '12px', color: '#475569', lineHeight: '1.5' }}>
              HIGH risk tools (refunds, escalations) are paused here before execution.
              LOW risk tools (profile lookups, invoice history) execute automatically.
              Approve to execute the tool call, or reject to send a refusal back to the agent.
            </div>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)', fontSize: '13px' }}>
            Loading approval queue...
          </div>
        )}

        {/* Empty state */}
        {!loading && approvals.length === 0 && (
          <div style={{
            background: '#ffffff', border: '1px solid var(--border)',
            borderRadius: '12px', padding: '60px',
            textAlign: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            <div style={{ fontSize: '36px', marginBottom: '12px' }}>✅</div>
            <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
              Queue is empty
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              No pending approvals. Try sending a refund or escalation request in the Chat tab.
            </div>
          </div>
        )}

        {/* Approval cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {approvals.map(approval => {
            const tc = TOOL_CONFIG[approval.tool_name] || {
              icon: '⚙', color: '#475569', bg: '#f8fafc', label: approval.tool_name,
            }
            const isApproving = actionLoading === approval.id + '_approve'
            const isRejecting = actionLoading === approval.id + '_reject'
            const isBusy = isApproving || isRejecting
            const timeAgo = formatTimeAgo(new Date(approval.created_at))

            return (
              <div key={approval.id} style={{
                background: '#ffffff', border: '1px solid var(--border)',
                borderRadius: '12px', overflow: 'hidden',
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
              }}>
                {/* Card header */}
                <div style={{
                  padding: '16px 20px',
                  borderBottom: '1px solid var(--border-subtle)',
                  display: 'flex', alignItems: 'center', gap: '12px',
                }}>
                  <span style={{ fontSize: '22px' }}>{tc.icon}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <span style={{
                        fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)',
                      }}>
                        {tc.label}
                      </span>
                      <span style={{
                        fontSize: '10px', fontWeight: 700,
                        padding: '2px 6px', borderRadius: '4px',
                        background: '#fef2f2', color: '#dc2626',
                        letterSpacing: '0.04em',
                      }}>
                        HIGH RISK
                      </span>
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {timeAgo} · Conv: {approval.conversation_id?.slice(0, 8)}...
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => handleReject(approval.id)}
                      disabled={isBusy}
                      style={{
                        background: '#ffffff', border: '1px solid rgba(220,38,38,0.3)',
                        borderRadius: '7px', padding: '8px 18px',
                        fontSize: '13px', fontWeight: 600,
                        color: isBusy ? 'var(--text-muted)' : '#dc2626',
                        cursor: isBusy ? 'not-allowed' : 'pointer',
                        fontFamily: 'inherit', transition: 'all 0.15s',
                      }}
                      onMouseEnter={e => !isBusy && ((e.currentTarget as HTMLElement).style.background = '#fef2f2')}
                      onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = '#ffffff'}
                    >
                      {isRejecting ? 'Rejecting...' : '✕ Reject'}
                    </button>
                    <button
                      onClick={() => handleApprove(approval.id)}
                      disabled={isBusy}
                      style={{
                        background: isBusy ? 'var(--bg-hover)' : '#059669',
                        border: 'none', borderRadius: '7px', padding: '8px 18px',
                        fontSize: '13px', fontWeight: 600,
                        color: isBusy ? 'var(--text-muted)' : '#ffffff',
                        cursor: isBusy ? 'not-allowed' : 'pointer',
                        fontFamily: 'inherit', transition: 'all 0.15s',
                      }}
                    >
                      {isApproving ? 'Approving...' : '✓ Approve'}
                    </button>
                  </div>
                </div>

                {/* Tool input details */}
                <div style={{ padding: '14px 20px', background: 'var(--bg-primary)' }}>
                  <div style={{ fontSize: '10px', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: '8px' }}>
                    TOOL PARAMETERS
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {Object.entries(approval.tool_input || {}).map(([key, val]) => (
                      <div key={key} style={{
                        background: '#ffffff', border: '1px solid var(--border)',
                        borderRadius: '6px', padding: '6px 12px',
                        display: 'flex', gap: '8px', alignItems: 'center',
                      }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>
                          {key}
                        </span>
                        <span style={{ fontSize: '12px', color: 'var(--text-primary)', fontWeight: 500 }}>
                          {String(val)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function formatTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}