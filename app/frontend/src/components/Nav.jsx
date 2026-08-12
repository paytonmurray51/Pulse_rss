import { NavLink } from 'react-router-dom'
import { Rss, Bookmark, Radio, Settings } from 'lucide-react'

const LINKS = [
  { to: '/', icon: Radio, label: 'Feed' },
  { to: '/saved', icon: Bookmark, label: 'Saved' },
  { to: '/feeds', icon: Rss, label: 'Sources' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

function NavItem({ to, icon: Icon, label, vertical = false }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        `nav-item ${isActive ? 'active' : ''} ${vertical ? 'flex-row gap-3 w-full px-3 py-2.5 rounded-lg hover:bg-bg-elevated' : ''}`
      }
    >
      <Icon className="w-5 h-5" />
      <span>{label}</span>
    </NavLink>
  )
}

export function BottomNav() {
  return (
    <nav className="sm:hidden fixed bottom-0 inset-x-0 z-40
                    bg-bg-surface/90 backdrop-blur border-t border-bg-border
                    flex items-center justify-around px-2 py-2 safe-area-pb">
      {LINKS.map((l) => (
        <NavItem key={l.to} {...l} />
      ))}
    </nav>
  )
}

export function Sidebar() {
  return (
    <aside className="hidden sm:flex flex-col w-16 shrink-0 sticky top-0 h-screen
                      bg-bg-surface border-r border-bg-border pt-16 pb-4 gap-1 items-center">
      {LINKS.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          end={l.to === '/'}
          title={l.label}
          className={({ isActive }) =>
            `flex flex-col items-center gap-1 p-2 rounded-lg text-xs transition-colors
             ${isActive ? 'text-accent' : 'text-gray-500 hover:text-gray-300 hover:bg-bg-elevated'}`
          }
        >
          <l.icon className="w-5 h-5" />
          <span className="text-[10px]">{l.label}</span>
        </NavLink>
      ))}
    </aside>
  )
}
