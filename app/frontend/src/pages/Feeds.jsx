import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getFeeds, createFeed, updateFeed, deleteFeed } from '../lib/api'
import { Rss, Tv2, ToggleLeft, ToggleRight, Trash2, Plus, X } from 'lucide-react'

const CATEGORIES = ['Tech', 'Engineering', 'Music', 'Outdoors', 'News', 'Science', 'Other']

function AddFeedModal({ onClose, onAdded }) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [category, setCategory] = useState('Tech')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleAdd = async () => {
    if (!name.trim() || !url.trim()) {
      setError('Name and URL are required')
      return
    }
    setError('')
    setLoading(true)
    try {
      const feed = await createFeed({ name: name.trim(), url: url.trim(), category })
      onAdded(feed)
      onClose()
    } catch (e) {
      setError(e.message || 'Failed to add feed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative z-10 w-full max-w-md bg-bg-elevated border border-bg-border
                   rounded-t-2xl sm:rounded-2xl p-5 space-y-4 animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold text-white">Add Source</h2>
          <button onClick={onClose} className="btn-ghost"><X className="w-4 h-4" /></button>
        </div>

        {error && (
          <p className="text-sm text-rose-400 bg-rose-400/10 border border-rose-400/20 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Name</label>
            <input
              className="input-field"
              placeholder="e.g. Hacker News"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">URL</label>
            <input
              type="url"
              className="input-field"
              placeholder="https://… (RSS feed or YouTube channel)"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Category</label>
            <select
              className="input-field"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex gap-3 pt-1">
          <button onClick={onClose} className="btn-secondary flex-1">Cancel</button>
          <button
            onClick={handleAdd}
            disabled={loading}
            className="btn-primary flex-1 disabled:opacity-60"
          >
            {loading ? 'Adding…' : 'Add Source'}
          </button>
        </div>
      </div>
    </div>
  )
}

function FeedRow({ feed, onToggle, onDelete }) {
  const isYoutube = feed.feed_type === 'youtube'

  return (
    <div className="flex items-center gap-3 py-3 border-b border-bg-border last:border-0">
      {isYoutube ? (
        <Tv2 className="w-5 h-5 text-red-500 shrink-0" />
      ) : (
        <Rss className="w-5 h-5 text-accent/70 shrink-0" />
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-200 truncate">{feed.name}</span>
          {feed.category && (
            <span className="tag-pill shrink-0">{feed.category}</span>
          )}
        </div>
        <p className="text-xs text-gray-500 truncate mt-0.5">{feed.url}</p>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <span className="text-xs text-gray-500">{feed.article_count}</span>
        {feed.last_fetched && (
          <span className="text-xs text-gray-600 hidden sm:inline">
            {new Date(feed.last_fetched).toLocaleDateString()}
          </span>
        )}
        <button
          onClick={() => onToggle(feed)}
          className="btn-ghost"
          title={feed.active ? 'Disable' : 'Enable'}
        >
          {feed.active
            ? <ToggleRight className="w-5 h-5 text-accent" />
            : <ToggleLeft className="w-5 h-5 text-gray-600" />}
        </button>
        <button
          onClick={() => onDelete(feed)}
          className="btn-ghost text-rose-400/60 hover:text-rose-400"
          title="Delete"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

export default function Feeds() {
  const [showAdd, setShowAdd] = useState(false)
  const queryClient = useQueryClient()

  const { data: feeds = [] } = useQuery({
    queryKey: ['feeds'],
    queryFn: getFeeds,
  })

  const handleToggle = async (feed) => {
    try {
      const updated = await updateFeed(feed.id, { active: !feed.active })
      queryClient.setQueryData(['feeds'], (old) =>
        old ? old.map((f) => (f.id === updated.id ? updated : f)) : old
      )
    } catch (e) {
      console.error(e)
    }
  }

  const handleDelete = async (feed) => {
    if (!confirm(`Delete "${feed.name}" and all its articles?`)) return
    try {
      await deleteFeed(feed.id)
      queryClient.setQueryData(['feeds'], (old) =>
        old ? old.filter((f) => f.id !== feed.id) : old
      )
    } catch (e) {
      console.error(e)
    }
  }

  const handleAdded = (feed) => {
    queryClient.setQueryData(['feeds'], (old) => (old ? [feed, ...old] : [feed]))
  }

  // Group by category
  const grouped = feeds.reduce((acc, feed) => {
    const cat = feed.category || 'Uncategorized'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(feed)
    return acc
  }, {})

  return (
    <div className="max-w-6xl mx-auto px-4 py-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Rss className="w-5 h-5 text-accent" />
          <h1 className="font-display text-xl font-semibold text-white">Sources</h1>
          <span className="text-sm text-gray-400">({feeds.length})</span>
        </div>
        <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> Add
        </button>
      </div>

      {feeds.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <Rss className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p className="font-display text-lg">No sources yet</p>
          <p className="text-sm mt-1">Add RSS feeds or YouTube channels to get started</p>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([category, categoryFeeds]) => (
            <div key={category}>
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                {category}
              </h2>
              <div className="bg-bg-surface border border-bg-border rounded-xl px-4">
                {categoryFeeds.map((feed) => (
                  <FeedRow
                    key={feed.id}
                    feed={feed}
                    onToggle={handleToggle}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {showAdd && (
        <AddFeedModal
          onClose={() => setShowAdd(false)}
          onAdded={handleAdded}
        />
      )}
    </div>
  )
}
