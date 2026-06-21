'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import NavBar from '../components/NavBar'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Conversation {
  id: string
  session_id: string
  user_message: string
  intent: string
  outcome: string
  total_cost_usd: number
  total_latency_ms: number
  total_tokens_in: number
  total_tokens_out: number
  turn_count: number
  created_at: string
  updated_at: string
}

const OUTCOME_CONFIG: Record<string, { color: string; bg: string }> = {
  resolved: { color: '#059669', bg: '#ecfdf5' },
  flagged:  { color: '#d97706', bg: '#fffbeb' },
  pending:  { color: '#2563eb', bg: '#eff6ff' },
  failed:   { color: '#dc2626', bg: '#fef2f2' },
}

const INTENT_CONFIG: Record<string, { color: string; bg: string }> = {
  billing_query:  { color: '#2563eb', bg: '#eff6ff' },
  refund_request: { color: '#d97706', bg: '#fffbeb' },
  policy_check:   { color: '#7c3aed', bg: '#f5f3ff' },
  escalation:     { color: '#dc2626', bg: '#fef2f2' },
  general:        { color: '#475569', bg: '#f8fafc' },
}

function Badge({ label, color, bg }: { label: string; color: string; bg: string }) {
  return (
    <span style={{
      fontSize: '11px', fontWeight: 600,
      padding: '2px 8px', borderRadius: '4px',
      background: bg, color,
      whiteSpace: 'nowrap',
    }}>{label}</span>
  )
}

export default function TracesPage() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => { fetchConversations() }, [])

  async function fetchConversations() {
    try {
      const res = await fetch(`${API}/api/v1/conversations?limit=50`)
      const data = await res.json()
      setConversations(data.conversations || data || [])
    } catch (e) {
      setError('Failed to load conversations. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <NavBar />
      <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '32px 24px' }}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '28px' }}>
          <div>
            <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-primary)' }}>
              Conversation Traces
            </h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginTop: '4px' }}>
              Click any conversation to inspect the full agent trace step by step.
            </p>
          </div>
          <button onClick={fetchConversations} style={{
            background: '#ffffff', border: '1px solid var(--border)',
            borderRadius: '8px', padding: '8px 16px',
            fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)',
            cursor: 'pointer', fontFamily: 'inherit',
          }}>
            ↻ Refresh
          </button>
        </div>

        {/* Stats bar */}
        {conversations.length > 0 && (
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
            gap: '12px', marginBottom: '24px',
          }}>
            {[
              { label: 'Total Conversations', value: conversations.length },
              { label: 'Resolved', value: conversations.filter(c => c.outcome === 'resolved').length, color: '#059669' },
              { label: 'Flagged', value: conversations.filter(c => c.outcome === 'flagged').length, color: '#d97706' },
              { label: 'Failed', value: conversations.filter(c => c.outcome === 'failed').length, color: '#dc2626' },
            ].map((stat, i) => (
              <div key={i} style={{
                background: '#ffffff', border: '1px solid var(--border)',
                borderRadius: '10px', padding: '16px 20px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
              }}>
                <div style={{ fontSize: '24px', fontWeight: 700, color: stat.color || 'var(--text-primary)' }}>
                  {stat.value}
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Content */}
        {loading && (
          <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>
            Loading conversations...
          </div>
        )}

        {error && (
          <div style={{
            background: '#fef2f2', border: '1px solid rgba(220,38,38,0.2)',
            borderRadius: '8px', padding: '16px', color: '#dc2626', fontSize: '13px',
          }}>{error}</div>
        )}

        {!loading && !error && conversations.length === 0 && (
          <div style={{
            background: '#ffffff', border: '1px solid var(--border)',
            borderRadius: '12px', padding: '60px',
            textAlign: 'center',
          }}>
            <div style={{ fontSize: '32px', marginBottom: '12px' }}>🔍</div>
            <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
              No traces yet
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              Send a message in the Chat tab to generate your first trace.
            </div>
          </div>
        )}

        {/* Table */}
        {conversations.length > 0 && (
          <div style={{
            background: '#ffffff', border: '1px solid var(--border)',
            borderRadius: '12px', overflow: 'hidden',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            {/* Table header */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: '2fr 120px 100px 90px 90px 80px 80px',
              padding: '12px 20px',
              background: 'var(--bg-primary)',
              borderBottom: '1px solid var(--border)',
              fontSize: '11px', fontWeight: 600,
              color: 'var(--text-muted)', letterSpacing: '0.06em',
            }}>
              <div>MESSAGE</div>
              <div>INTENT</div>
              <div>OUTCOME</div>
              <div>LATENCY</div>
              <div>COST</div>
              <div>TOKENS</div>
              <div>TIME</div>
            </div>

            {/* Rows */}
            {conversations.map((conv, i) => {
              const oc = OUTCOME_CONFIG[conv.outcome] || OUTCOME_CONFIG.failed
              const ic = INTENT_CONFIG[conv.intent] || INTENT_CONFIG.general
              const date = new Date(conv.created_at)
              const timeAgo = formatTimeAgo(date)

              return (
                <Link key={conv.id} href={`/traces/${conv.id}`} style={{ textDecoration: 'none' }}>
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: '2fr 120px 100px 90px 90px 80px 80px',
                    padding: '14px 20px',
                    borderBottom: i < conversations.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                    alignItems: 'center',
                    cursor: 'pointer',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--bg-primary)'}
                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = '#ffffff'}
                  >
                    <div style={{
                      color: 'var(--text-primary)', fontSize: '13px',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      paddingRight: '16px',
                    }}>
                      {conv.user_message}
                    </div>
                    <div>
                      <Badge label={conv.intent?.replace('_', ' ') || 'unknown'} color={ic.color} bg={ic.bg} />
                    </div>
                    <div>
                      <Badge label={conv.outcome || 'unknown'} color={oc.color} bg={oc.bg} />
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {conv.total_latency_ms ? `${Math.round(conv.total_latency_ms)}ms` : '—'}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {conv.total_cost_usd ? `$${conv.total_cost_usd.toFixed(4)}` : '—'}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {(conv.total_tokens_in || 0) + (conv.total_tokens_out || 0)}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {timeAgo}
                    </div>
                  </div>
                </Link>
              )
            })}
          </div>
        )}
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