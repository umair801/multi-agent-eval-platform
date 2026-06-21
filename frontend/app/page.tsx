'use client'
import { useState, useRef, useEffect } from 'react'
import NavBar from './components/NavBar'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Citation { source: string; type: string }
interface Message {
  role: 'user' | 'assistant'
  content: string
  intent?: string
  citations?: Citation[]
  outcome?: string
  cost?: number
  latency?: number
  conversationId?: string
  flagged?: boolean
  error?: boolean
}

const INTENT_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
  billing_query:    { color: '#2563eb', bg: '#eff6ff', label: 'Billing' },
  refund_request:   { color: '#d97706', bg: '#fffbeb', label: 'Refund' },
  policy_check:     { color: '#7c3aed', bg: '#f5f3ff', label: 'Policy' },
  escalation:       { color: '#dc2626', bg: '#fef2f2', label: 'Escalation' },
  general:          { color: '#475569', bg: '#f8fafc', label: 'General' },
}

const EXAMPLE_PROMPTS = [
  { text: 'What is your refund policy?',                    tag: 'Policy' },
  { text: 'I was charged twice this month. Get a refund?',  tag: 'Refund' },
  { text: 'Show invoice history for customer CUST001',       tag: 'Billing' },
  { text: 'I need to escalate my billing issue urgently',   tag: 'Escalate' },
  { text: 'What are your SLA response times?',              tag: 'Policy' },
]

const TAG_COLORS: Record<string, { color: string; bg: string }> = {
  Policy:   { color: '#7c3aed', bg: '#f5f3ff' },
  Refund:   { color: '#d97706', bg: '#fffbeb' },
  Billing:  { color: '#2563eb', bg: '#eff6ff' },
  Escalate: { color: '#dc2626', bg: '#fef2f2' },
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage(text?: string) {
    const msg = (text || input).trim()
    if (!msg || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/v1/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response || data.final_response || 'No response generated.',
        intent: data.intent,
        citations: data.citations || [],
        outcome: data.outcome,
        cost: data.total_cost_usd,
        latency: data.total_latency_ms,
        conversationId: data.conversation_id,
        flagged: data.flagged,
        error: data.outcome === 'failed',
      }])
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Connection error. Is the backend running on port 8000?',
        error: true,
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <NavBar />

      <div style={{ maxWidth: '860px', margin: '0 auto', padding: '32px 24px 120px' }}>

        {/* Page header */}
        <div style={{ marginBottom: '28px' }}>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-primary)' }}>
            Multi-Agent Chat
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginTop: '4px' }}>
            Router → Billing / Policy → Tool Executor → Response → Eval Safety
          </p>
        </div>

        {/* Agent pipeline indicator */}
        <div style={{
          display: 'flex', gap: '6px', alignItems: 'center',
          marginBottom: '28px', flexWrap: 'wrap',
        }}>
          {['Router', 'Billing', 'Policy', 'Tool Exec', 'Response', 'Eval'].map((a, i, arr) => (
            <div key={a} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{
                fontSize: '11px', fontWeight: 600,
                padding: '3px 10px', borderRadius: '4px',
                background: 'var(--accent-blue-light)',
                color: 'var(--accent-blue)',
                border: '1px solid rgba(37,99,235,0.15)',
              }}>{a}</span>
              {i < arr.length - 1 && (
                <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>→</span>
              )}
            </div>
          ))}
        </div>

        {/* Empty state */}
        {messages.length === 0 && (
          <div style={{
            background: '#ffffff',
            border: '1px solid var(--border)',
            borderRadius: '12px',
            padding: '28px',
            boxShadow: 'var(--shadow-sm)',
          }}>
            <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: '16px' }}>
              TRY AN EXAMPLE
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {EXAMPLE_PROMPTS.map((p, i) => {
                const tc = TAG_COLORS[p.tag] || TAG_COLORS.Policy
                return (
                  <button key={i} onClick={() => sendMessage(p.text)} style={{
                    display: 'flex', alignItems: 'center', gap: '12px',
                    background: 'var(--bg-primary)',
                    border: '1px solid var(--border)',
                    borderRadius: '8px',
                    padding: '11px 16px',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.15s',
                    fontFamily: 'inherit',
                  }}
                  onMouseEnter={e => {
                    const el = e.currentTarget
                    el.style.borderColor = 'var(--accent-blue)'
                    el.style.background = 'var(--accent-blue-light)'
                  }}
                  onMouseLeave={e => {
                    const el = e.currentTarget
                    el.style.borderColor = 'var(--border)'
                    el.style.background = 'var(--bg-primary)'
                  }}>
                    <span style={{
                      fontSize: '10px', fontWeight: 700,
                      padding: '2px 8px', borderRadius: '4px',
                      background: tc.bg, color: tc.color,
                      whiteSpace: 'nowrap',
                    }}>{p.tag}</span>
                    <span style={{ color: 'var(--text-primary)', fontSize: '13px' }}>{p.text}</span>
                    <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: '16px' }}>›</span>
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* Messages */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {messages.map((msg, i) => (
            <div key={i} style={{
              display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
            }}>
              <div style={{ maxWidth: '78%', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{
                  fontSize: '11px', fontWeight: 600,
                  color: 'var(--text-muted)',
                  textAlign: msg.role === 'user' ? 'right' : 'left',
                  letterSpacing: '0.04em',
                }}>
                  {msg.role === 'user' ? 'You' : 'Agent'}
                </div>
                <div style={{
                  background: msg.role === 'user' ? 'var(--accent-blue)' : '#ffffff',
                  border: msg.role === 'user' ? 'none' : `1px solid ${msg.error ? 'var(--accent-red)' : 'var(--border)'}`,
                  borderRadius: msg.role === 'user' ? '12px 12px 2px 12px' : '2px 12px 12px 12px',
                  padding: '12px 16px',
                  boxShadow: 'var(--shadow-sm)',
                }}>
                  <div style={{
                    color: msg.role === 'user' ? '#ffffff' : 'var(--text-primary)',
                    fontSize: '14px', lineHeight: '1.6',
                    whiteSpace: 'pre-wrap',
                  }}>
                    {msg.content}
                  </div>

                  {/* Metadata */}
                  {msg.role === 'assistant' && (msg.intent || msg.citations?.length || msg.cost) && (
                    <div style={{
                      marginTop: '12px',
                      paddingTop: '10px',
                      borderTop: '1px solid var(--border-subtle)',
                      display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center',
                    }}>
                      {msg.intent && (() => {
                        const ic = INTENT_CONFIG[msg.intent] || INTENT_CONFIG.general
                        return (
                          <span style={{
                            fontSize: '11px', fontWeight: 600,
                            padding: '2px 8px', borderRadius: '4px',
                            background: ic.bg, color: ic.color,
                          }}>{ic.label}</span>
                        )
                      })()}

                      {msg.outcome && (
                        <span style={{
                          fontSize: '11px', fontWeight: 600,
                          padding: '2px 8px', borderRadius: '4px',
                          background: msg.outcome === 'resolved' ? 'var(--accent-green-light)' : msg.outcome === 'flagged' ? 'var(--accent-amber-light)' : 'var(--accent-red-light)',
                          color: msg.outcome === 'resolved' ? 'var(--accent-green)' : msg.outcome === 'flagged' ? 'var(--accent-amber)' : 'var(--accent-red)',
                        }}>{msg.outcome}</span>
                      )}

                      {msg.citations?.map((c, ci) => (
                        <span key={ci} style={{
                          fontSize: '11px',
                          padding: '2px 8px', borderRadius: '4px',
                          background: 'var(--accent-purple-light)',
                          color: 'var(--accent-purple)',
                          fontWeight: 500,
                        }}>
                          📎 {typeof c === 'string' ? c : c.source}
                        </span>
                      ))}

                      <div style={{ marginLeft: 'auto', display: 'flex', gap: '10px', alignItems: 'center' }}>
                        {msg.latency && (
                          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            {Math.round(msg.latency)}ms
                          </span>
                        )}
                        {msg.cost && (
                          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            ${msg.cost.toFixed(5)}
                          </span>
                        )}
                        {msg.conversationId && (
                          <a href={`/traces/${msg.conversationId}`} style={{
                            fontSize: '11px', color: 'var(--accent-blue)',
                            textDecoration: 'none', fontWeight: 600,
                          }}>
                            View trace →
                          </a>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}

          {/* Loading */}
          {loading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div style={{
                background: '#ffffff',
                border: '1px solid var(--border)',
                borderRadius: '2px 12px 12px 12px',
                padding: '14px 18px',
                boxShadow: 'var(--shadow-sm)',
                display: 'flex', alignItems: 'center', gap: '10px',
              }}>
                <div style={{ display: 'flex', gap: '4px' }}>
                  {[0,1,2].map(i => (
                    <span key={i} style={{
                      width: '6px', height: '6px', borderRadius: '50%',
                      background: 'var(--accent-blue)',
                      display: 'inline-block',
                      animation: `bounce 1.2s ease-in-out ${i*0.2}s infinite`,
                    }}/>
                  ))}
                </div>
                <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                  Routing through agents...
                </span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input bar */}
      <div style={{
        position: 'fixed', bottom: 0, left: 0, right: 0,
        background: '#ffffff',
        borderTop: '1px solid var(--border)',
        padding: '16px 24px',
        boxShadow: '0 -4px 16px rgba(0,0,0,0.06)',
      }}>
        <div style={{ maxWidth: '860px', margin: '0 auto', display: 'flex', gap: '12px', alignItems: 'flex-end' }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about billing, refunds, or support policies... (Enter to send)"
            rows={1}
            style={{
              flex: 1,
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              padding: '11px 16px',
              color: 'var(--text-primary)',
              fontSize: '14px',
              fontFamily: 'inherit',
              resize: 'none',
              outline: 'none',
              lineHeight: '1.5',
              minHeight: '44px',
              maxHeight: '120px',
              transition: 'border-color 0.15s',
            }}
            onFocus={e => e.target.style.borderColor = 'var(--accent-blue)'}
            onBlur={e => e.target.style.borderColor = 'var(--border)'}
          />
          <button
            onClick={() => sendMessage()}
            disabled={loading || !input.trim()}
            style={{
              background: loading || !input.trim() ? 'var(--bg-hover)' : 'var(--accent-blue)',
              border: 'none',
              borderRadius: '8px',
              padding: '11px 24px',
              color: loading || !input.trim() ? 'var(--text-muted)' : '#ffffff',
              fontSize: '13px',
              fontWeight: 600,
              fontFamily: 'inherit',
              cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
              height: '44px',
              transition: 'all 0.15s',
              whiteSpace: 'nowrap',
            }}
          >
            {loading ? 'Sending...' : 'Send →'}
          </button>
        </div>
      </div>

      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
          40% { transform: translateY(-4px); opacity: 1; }
        }
      `}</style>
    </div>
  )
}