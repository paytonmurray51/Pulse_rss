import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getArticles, getFeeds, getProfile } from '../lib/api'
import ArticleCard from '../components/ArticleCard'
import { ChevronLeft, ChevronRight } from 'lucide-react'

function Skeleton() {
  return (
    <div className="card animate-pulse">
      <div className="aspect-[16/8] bg-bg-elevated" />
      <div className="p-3 space-y-2">
        <div className="h-3 bg-bg-elevated rounded w-1/3" />
        <div className="h-4 bg-bg-elevated rounded w-full" />
        <div className="h-4 bg-bg-elevated rounded w-2/3" />
        <div className="h-3 bg-bg-elevated rounded w-full" />
        <div className="h-3 bg-bg-elevated rounded w-4/5" />
      </div>
    </div>
  )
}

const VIEWS = [
  { key: 'all', label: 'All' },
  { key: 'unread', label: 'Unread' },
  { key: 'saved', label: 'Saved' },
]

export default function Home() {
  const [page, setPage] = useState(1)
  const [view, setView] = useState('all')
  const [category, setCategory] = useState('')
  const [feedId, setFeedId] = useState('')
  const [sort, setSort] = useState('score')
  const [minScore, setMinScore] = useState(null)
  const queryClient = useQueryClient()

  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: getProfile })

  // Seed the slider from the saved threshold once, then let it be overridden
  // locally without writing back to the profile.
  useEffect(() => {
    if (profile && minScore === null) {
      setMinScore(profile.min_score_threshold ?? 5.0)
    }
  }, [profile, minScore])

  const params = {
    page,
    per_page: 20,
    unread_only: view === 'unread' || undefined,
    read_later: view === 'saved' || undefined,
    // A source is more specific than its category, so sending both would be
    // redundant at best and contradictory at worst.
    category: !feedId ? category || undefined : undefined,
    feed_id: feedId || undefined,
    sort,
    min_score: minScore ?? undefined,
  }

  const { data, isLoading } = useQuery({
    queryKey: ['articles', params],
    queryFn: () => getArticles(params),
    enabled: minScore !== null,
  })

  const { data: feeds } = useQuery({
    queryKey: ['feeds'],
    queryFn: getFeeds,
  })

  const categories = [...new Set((feeds ?? []).map((f) => f.category).filter(Boolean))].sort()
  // Narrow the source list to the chosen category so the two controls agree.
  const visibleFeeds = category
    ? (feeds ?? []).filter((f) => f.category === category)
    : (feeds ?? [])

  const totalPages = data ? Math.ceil(data.total / data.per_page) : 1

  const handleUpdate = (updated) => {
    queryClient.setQueryData(['articles', params], (old) => {
      if (!old) return old
      return {
        ...old,
        items: old.items.map((a) => (a.id === updated.id ? updated : a)),
      }
    })
  }

  const handleRemove = (id) => {
    queryClient.setQueryData(['articles', params], (old) => {
      if (!old) return old
      return {
        ...old,
        items: old.items.filter((a) => a.id !== id),
        total: old.total - 1,
      }
    })
  }

  // Any filter change invalidates the current page number.
  const reset = (fn) => (value) => { setPage(1); fn(value) }

  return (
    <div className="max-w-6xl mx-auto px-4 py-4">
      {/* Filter bar. `top-0`, not an offset for the TopBar: <main> is the
          scrolling container and the TopBar sits outside it, so a non-zero
          offset would leave a gap that article cards scroll through. */}
      <div className="sticky top-0 z-20 flex flex-wrap items-center gap-2 py-2
                     bg-bg-base/95 backdrop-blur border-b border-bg-border
                     mb-4 -mx-4 px-4">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            onClick={() => reset(setView)(v.key)}
            className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors
              ${view === v.key
                ? 'bg-accent/20 text-accent border border-accent/30'
                : 'text-gray-400 hover:text-gray-200'}`}
          >
            {v.label}
          </button>
        ))}

        <span className="w-px h-5 bg-bg-border mx-1 hidden sm:block" />

        {/* Score floor. Debounce isn't needed — onChange only fires on release
            for range inputs in every browser we target. */}
        <label className="hidden sm:flex items-center gap-2 text-xs text-gray-400">
          min
          <input
            type="range"
            min={0}
            max={9.5}
            step={0.5}
            value={minScore ?? 5}
            onChange={(e) => reset(setMinScore)(parseFloat(e.target.value))}
            className="w-24 accent-accent"
          />
          <span className="text-accent font-semibold tabular-nums w-6">
            {(minScore ?? 5).toFixed(1)}
          </span>
        </label>

        <span className="w-px h-5 bg-bg-border mx-1 hidden sm:block" />

        <select
          value={sort}
          onChange={(e) => reset(setSort)(e.target.value)}
          className="input-field w-auto text-xs py-1.5"
        >
          <option value="score">Sort: Score</option>
          <option value="newest">Sort: Newest</option>
        </select>

        {categories.length > 0 && (
          <select
            value={category}
            onChange={(e) => {
              const next = e.target.value
              reset(setCategory)(next)
              // Clear a source that no longer belongs to the chosen category,
              // otherwise the feed would silently show nothing.
              if (next && feedId) {
                const stillVisible = (feeds ?? []).some(
                  (f) => String(f.id) === String(feedId) && f.category === next
                )
                if (!stillVisible) setFeedId('')
              }
            }}
            className="ml-auto input-field w-auto text-xs py-1.5"
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        )}

        {visibleFeeds.length > 0 && (
          <select
            value={feedId}
            onChange={(e) => reset(setFeedId)(e.target.value)}
            className={`input-field w-auto text-xs py-1.5 ${categories.length ? '' : 'ml-auto'}`}
          >
            <option value="">
              {category ? `All ${category} sources` : 'All sources'}
            </option>
            {visibleFeeds.map((f) => (
              <option key={f.id} value={f.id}>{f.name}</option>
            ))}
          </select>
        )}
      </div>

      {data && (
        <p className="text-xs text-gray-500 mb-3">
          {data.total} article{data.total === 1 ? '' : 's'}
          {category && <> in {category}</>}
          {minScore > 0 && <> scoring {minScore.toFixed(1)}+</>}
        </p>
      )}

      {/* Article list */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} />)}
        </div>
      ) : data?.items?.length === 0 ? (
        <div className="text-center text-gray-500 py-20">
          <p className="text-lg font-display">No articles yet</p>
          <p className="text-sm mt-2">Add a feed and click Refresh to get started</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data?.items?.map((article) => (
            <ArticleCard
              key={article.id}
              article={article}
              onUpdate={handleUpdate}
              onRemove={handleRemove}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-6">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="btn-secondary flex items-center gap-1 disabled:opacity-40"
          >
            <ChevronLeft className="w-4 h-4" /> Previous
          </button>
          <span className="text-sm text-gray-400">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="btn-secondary flex items-center gap-1 disabled:opacity-40"
          >
            Next <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  )
}
