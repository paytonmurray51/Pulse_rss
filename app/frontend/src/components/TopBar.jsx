import { useState, useRef, useEffect } from 'react'
import { Zap, RefreshCw, LogOut, ShieldCheck } from 'lucide-react'
import { refreshFeeds } from '../lib/api'
import { useAuth } from '../lib/auth'

function UserMenu() {
  const { user, signOut, isAdmin } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  if (!user) return null
  const initial = (user.name || user.email || '?').charAt(0).toUpperCase()

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-8 h-8 rounded-full overflow-hidden border border-bg-border
                   flex items-center justify-center bg-bg-elevated text-xs font-semibold
                   text-gray-300 hover:border-accent/40 transition-colors"
        title={user.email}
      >
        {user.picture
          ? <img src={user.picture} alt="" className="w-full h-full object-cover"
                 referrerPolicy="no-referrer" />
          : initial}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-56 bg-bg-elevated border border-bg-border
                        rounded-xl shadow-xl p-1 z-50 animate-fade-in">
          <div className="px-3 py-2 border-b border-bg-border mb-1">
            <p className="text-sm text-gray-200 truncate">{user.name || user.email}</p>
            <p className="text-xs text-gray-500 truncate">{user.email}</p>
            {isAdmin && (
              <span className="inline-flex items-center gap-1 mt-1.5 text-[10px] uppercase
                               tracking-wider text-accent">
                <ShieldCheck className="w-3 h-3" /> Admin
              </span>
            )}
          </div>
          <button
            onClick={signOut}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm
                       text-gray-300 hover:bg-bg-border transition-colors"
          >
            <LogOut className="w-4 h-4" /> Sign out
          </button>
        </div>
      )}
    </div>
  )
}

export default function TopBar({ stats, onRefreshed }) {
  const [refreshing, setRefreshing] = useState(false)
  const [note, setNote] = useState('')

  const handleRefresh = async () => {
    if (refreshing) return
    setRefreshing(true)
    setNote('')
    try {
      // Runs inline now and reports what happened, rather than firing a
      // background task and guessing with a fixed delay.
      const result = await refreshFeeds()
      setNote(result.message)
      onRefreshed?.()
      setTimeout(() => setNote(''), 6000)
    } catch (e) {
      setNote(e.message || 'Refresh failed')
      setTimeout(() => setNote(''), 8000)
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <header className="sticky top-0 z-30 bg-bg-base/80 backdrop-blur border-b border-bg-border">
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="flex items-center gap-2 shrink-0">
          <Zap className="w-5 h-5 text-accent" />
          <span className="font-display text-lg font-semibold text-white">Pulse</span>
        </div>

        <div className="hidden sm:flex items-center gap-4 flex-1 justify-center text-sm">
          {stats && (
            <>
              <span className="text-gray-400">
                <span className="text-white font-medium">{stats.unread_articles}</span> unread
              </span>
              {stats.avg_score != null && (
                <span className="text-gray-400">
                  avg <span className="text-white font-medium">{stats.avg_score}</span>
                </span>
              )}
              <span className="text-gray-400">
                <span className="text-white font-medium">{stats.articles_today}</span> today
              </span>
              {stats.unscored_articles > 0 && (
                <span className="text-gray-500">
                  {stats.unscored_articles} unscored
                </span>
              )}
            </>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="btn-ghost flex items-center gap-2 text-sm"
            title="Fetch new articles and score them for you"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{refreshing ? 'Syncing…' : 'Refresh'}</span>
          </button>
          <UserMenu />
        </div>
      </div>

      {note && (
        <p className="px-4 pb-2 text-xs text-gray-400 animate-fade-in">{note}</p>
      )}
    </header>
  )
}
