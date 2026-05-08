import { useState } from 'react'
import { Zap, RefreshCw } from 'lucide-react'
import { refreshFeeds } from '../lib/api'

export default function TopBar({ stats, onRefreshed }) {
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = async () => {
    if (refreshing) return
    setRefreshing(true)
    try {
      await refreshFeeds()
      await new Promise((r) => setTimeout(r, 2000))
      onRefreshed?.()
    } catch (e) {
      console.error(e)
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 px-4 py-3
                       bg-bg-base/80 backdrop-blur border-b border-bg-border">
      {/* Logo */}
      <div className="flex items-center gap-2 shrink-0">
        <Zap className="w-5 h-5 text-amber-pulse" />
        <span className="font-display text-lg font-semibold text-white">Pulse</span>
      </div>

      {/* Center stats (desktop) */}
      <div className="hidden sm:flex items-center gap-4 flex-1 justify-center text-sm">
        {stats && (
          <>
            <span className="text-gray-400">
              <span className="text-white font-medium">{stats.unread_articles}</span> unread
            </span>
            {stats.avg_score != null && (
              <span className="text-indigo-400">
                avg <span className="font-medium">{stats.avg_score}</span>
              </span>
            )}
            <span className="text-gray-400">
              <span className="text-white font-medium">{stats.articles_today}</span> today
            </span>
          </>
        )}
      </div>

      {/* Refresh */}
      <div className="ml-auto">
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="btn-ghost flex items-center gap-2 text-sm"
          title="Refresh feeds"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">{refreshing ? 'Refreshing…' : 'Refresh'}</span>
        </button>
      </div>
    </header>
  )
}
