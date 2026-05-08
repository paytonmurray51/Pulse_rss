import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getArticles, getFeeds } from '../lib/api'
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

export default function Home() {
  const [page, setPage] = useState(1)
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [feedId, setFeedId] = useState('')
  const queryClient = useQueryClient()

  const params = {
    page,
    per_page: 20,
    unread_only: unreadOnly || undefined,
    feed_id: feedId || undefined,
  }

  const { data, isLoading } = useQuery({
    queryKey: ['articles', params],
    queryFn: () => getArticles(params),
  })

  const { data: feeds } = useQuery({
    queryKey: ['feeds'],
    queryFn: getFeeds,
  })

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

  const handleFilterChange = (newUnread, newFeedId) => {
    setPage(1)
    if (newUnread !== undefined) setUnreadOnly(newUnread)
    if (newFeedId !== undefined) setFeedId(newFeedId)
  }

  return (
    <div className="max-w-3xl mx-auto px-3 py-4">
      {/* Filter bar */}
      <div className="sticky top-[57px] z-20 flex items-center gap-2 py-2
                     bg-bg-base/90 backdrop-blur mb-4 -mx-3 px-3">
        <button
          onClick={() => handleFilterChange(!unreadOnly, undefined)}
          className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors
            ${!unreadOnly
              ? 'bg-amber-500/20 text-amber-pulse border border-amber-500/30'
              : 'text-gray-400 hover:text-gray-200'}`}
        >
          All
        </button>
        <button
          onClick={() => handleFilterChange(!unreadOnly, undefined)}
          className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors
            ${unreadOnly
              ? 'bg-amber-500/20 text-amber-pulse border border-amber-500/30'
              : 'text-gray-400 hover:text-gray-200'}`}
        >
          Unread
        </button>

        {feeds && feeds.length > 0 && (
          <select
            value={feedId}
            onChange={(e) => handleFilterChange(undefined, e.target.value)}
            className="ml-auto input-field w-auto text-xs py-1.5"
          >
            <option value="">All sources</option>
            {feeds.map((f) => (
              <option key={f.id} value={f.id}>{f.name}</option>
            ))}
          </select>
        )}
      </div>

      {/* Article list */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} />)}
        </div>
      ) : data?.items?.length === 0 ? (
        <div className="text-center text-gray-500 py-20">
          <p className="text-lg font-display">No articles yet</p>
          <p className="text-sm mt-2">Add a feed and click Refresh to get started</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
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
