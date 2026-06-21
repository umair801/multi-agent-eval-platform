'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV_ITEMS = [
  { href: '/',          label: 'Chat',      icon: '💬' },
  { href: '/traces',    label: 'Traces',    icon: '🔍' },
  { href: '/approvals', label: 'Approvals', icon: '✅' },
  { href: '/metrics',   label: 'Metrics',   icon: '📊' },
]

export default function NavBar() {
  const pathname = usePathname()

  return (
    <nav style={{
      background: '#ffffff',
      borderBottom: '1px solid var(--border)',
      padding: '0 32px',
      display: 'flex',
      alignItems: 'center',
      height: '56px',
      gap: '8px',
      position: 'sticky',
      top: 0,
      zIndex: 100,
      boxShadow: 'var(--shadow-sm)',
    }}>
      {/* Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginRight: '24px' }}>
        <div style={{
          width: '28px', height: '28px',
          background: 'var(--accent-blue)',
          borderRadius: '6px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '14px',
        }}>⬡</div>
        <div>
          <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.02em' }}>
            Datawebify
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', letterSpacing: '0.04em', marginTop: '-2px' }}>
            Eval Platform
          </div>
        </div>
      </div>

      {/* Divider */}
      <div style={{ width: '1px', height: '28px', background: 'var(--border)', marginRight: '16px' }} />

      {/* Nav links */}
      <div style={{ display: 'flex', gap: '2px', flex: 1 }}>
        {NAV_ITEMS.map(item => {
          const active = pathname === item.href
          return (
            <Link key={item.href} href={item.href} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '7px 16px',
              borderRadius: '6px',
              fontSize: '13px',
              fontWeight: active ? 600 : 500,
              color: active ? 'var(--accent-blue)' : 'var(--text-secondary)',
              background: active ? 'var(--accent-blue-light)' : 'transparent',
              textDecoration: 'none',
              transition: 'all 0.15s',
            }}>
              <span>{item.icon}</span>
              {item.label}
            </Link>
          )
        })}
      </div>

      {/* Status indicator */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '6px',
        background: 'var(--accent-green-light)',
        border: '1px solid rgba(5, 150, 105, 0.2)',
        borderRadius: '20px',
        padding: '4px 12px',
      }}>
        <span style={{
          width: '6px', height: '6px',
          borderRadius: '50%',
          background: 'var(--accent-green)',
          display: 'inline-block',
        }} />
        <span style={{ color: 'var(--accent-green)', fontSize: '11px', fontWeight: 600 }}>API Live</span>
      </div>
    </nav>
  )
}