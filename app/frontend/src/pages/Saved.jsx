import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getArticles } from '../lib/api'
import ArticleCard from '../components/ArticleCard'
import { Bookmark } from 'lucide-react'

export default function Saved() {
  const [page, setPage] = useState(1)
  const queryClient = useQueryClient()

  const params = { page, per_page: 20, read_later: true }

  const { data, isLoading } = useQuery({
    queryKey: ['articles', params],
    queryFn: () => getArticles(params),
  })

  const handleUpdate = (updated) => {
    queryClient.setQueryData(['articles', params], (old) => {
      if (!old) return old
      // If unsaved, remove from list
      if (!updated.read_later) {
        return {
          ...old,
          items: old.items.filter((a) => a.id !== updated.id),
          total: old.total - 1,
        }
      }
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

  return (
    <div className="max-w-6xl mx-auto px-4 py-4">
      <div className="flex items-center gap-2 mb-4">
        <Bookmark className="w-5 h-5 text-accent" />
        <h1 className="font-display text-xl font-semibold text-white">Saved</h1>
        {data && (
          <span className="ml-1 text-sm text-gray-400">({data.total})</span>
        )}
      </div>

      {isLoading ? (
        <div className="text-center text-gray-500 py-10">Loading…</div>
      ) : data?.items?.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <Bookmark className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p className="font-display text-lg">Nothing saved yet</p>
          <p className="text-sm mt-1">Bookmark articles from your feed to read later</p>
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
    </div>
  )
}
