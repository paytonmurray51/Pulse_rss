import { useState } from 'react'
import { ThumbsUp, ThumbsDown, Bookmark, BookmarkCheck, ExternalLink, Ban, Tv2, Rss, Play } from 'lucide-react'
import ScoreBadge from './ScoreBadge'
import { toggleReadLater, markRead, setFeedback, createBlock } from '../lib/api'
import { formatDistanceToNow } from '../lib/dateUtils'

// ─── Block menu modal ────────────────────────────────────────────────────────

function BlockMenu({ article, onClose, onBlocked }) {
  const [loading, setLoading] = useState(false)

  const doBlock = async (blocks) => {
    setLoading(true)
    try {
      await Promise.all(blocks.map((b) => createBlock(b)))
      onBlocked()
      setTimeout(onClose, 400)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const tags = (article.ai_tags || []).slice(0, 4)

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative z-10 w-full max-w-sm bg-bg-elevated border border-bg-border
                   rounded-t-2xl sm:rounded-2xl p-4 space-y-2 animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider mb-3">Block content</p>

        <button
          disabled={loading}
          onClick={() => doBlock([{ block_type: 'source', value: article.feed_name }])}
          className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-bg-border text-sm
                     text-gray-300 transition-colors flex items-center gap-2"
        >
          <Ban className="w-4 h-4 text-rose-400 shrink-0" />
          Block &ldquo;{article.feed_name}&rdquo;
        </button>

        {tags.map((tag) => (
          <button
            key={tag}
            disabled={loading}
            onClick={() => doBlock([{ block_type: 'topic', value: tag }])}
            className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-bg-border text-sm
                       text-gray-300 transition-colors flex items-center gap-2"
          >
            <Ban className="w-4 h-4 text-orange-400 shrink-0" />
            Block topic &ldquo;{tag}&rdquo;
          </button>
        ))}

        {tags.length > 0 && (
          <button
            disabled={loading}
            onClick={() =>
              doBlock([
                { block_type: 'source', value: article.feed_name },
                ...tags.slice(0, 2).map((t) => ({ block_type: 'topic', value: t })),
              ])
            }
            className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-bg-border text-sm
                       text-rose-400 transition-colors flex items-center gap-2"
          >
            <Ban className="w-4 h-4 shrink-0" />
            Block source + topics
          </button>
        )}

        <button
          onClick={onClose}
          className="w-full text-center px-3 py-2 rounded-lg text-sm text-gray-500 hover:text-gray-300
                     transition-colors mt-2"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ─── Article card ────────────────────────────────────────────────────────────

export default function ArticleCard({ article, onUpdate, onRemove }) {
  const [showBlock, setShowBlock] = useState(false)
  const [fading, setFading] = useState(false)

  const isYoutube = article.feed_type === 'youtube'

  const handleOpen = async () => {
    try {
      const updated = await markRead(article.id)
      onUpdate?.(updated)
    } catch (e) {
      console.error(e)
    }
    window.open(article.url, '_blank', 'noopener,noreferrer')
  }

  const handleReadLater = async (e) => {
    e.stopPropagation()
    try {
      const updated = await toggleReadLater(article.id)
      onUpdate?.(updated)
    } catch (e) {
      console.error(e)
    }
  }

  const handleLike = async (e) => {
    e.stopPropagation()
    const newRating = article.user_rating === 'liked' ? '' : 'liked'
    try {
      const updated = await setFeedback(article.id, newRating)
      onUpdate?.(updated)
    } catch (e) {
      console.error(e)
    }
  }

  const handleDislike = async (e) => {
    e.stopPropagation()
    try {
      await setFeedback(article.id, 'disliked')
      setFading(true)
      setTimeout(() => onRemove?.(article.id), 600)
    } catch (e) {
      console.error(e)
    }
  }

  const handleBlocked = () => {
    setTimeout(() => onRemove?.(article.id), 400)
  }

  const timeAgo = article.published_at
    ? formatDistanceToNow(new Date(article.published_at))
    : ''

  return (
    <>
      <article
        className={`card cursor-pointer group transition-opacity duration-500
                   ${fading ? 'opacity-0' : ''}
                   ${article.is_read ? 'opacity-60' : ''}`}
        onClick={handleOpen}
      >
        {/* Thumbnail */}
        {article.thumbnail && (
          <div className="relative aspect-[16/8] overflow-hidden bg-bg-elevated">
            <img
              src={article.thumbnail}
              alt=""
              className="w-full h-full object-cover"
              loading="lazy"
              onError={(e) => { e.target.parentElement.style.display = 'none' }}
            />
            {isYoutube && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="bg-black/50 rounded-full p-3">
                  <Play className="w-6 h-6 text-white fill-white" />
                </div>
              </div>
            )}
            {/* Score badge overlay */}
            <div className="absolute top-2 right-2">
              <ScoreBadge score={article.ai_score} />
            </div>
          </div>
        )}

        <div className="p-3 space-y-2">
          {/* Meta row */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 text-xs text-gray-500 min-w-0">
              {isYoutube ? (
                <Tv2 className="w-3.5 h-3.5 text-red-500 shrink-0" />
              ) : (
                <Rss className="w-3.5 h-3.5 text-amber-500/70 shrink-0" />
              )}
              <span className="truncate">{article.feed_name}</span>
              {timeAgo && <span className="shrink-0">· {timeAgo}</span>}
            </div>
            {!article.thumbnail && <ScoreBadge score={article.ai_score} />}
          </div>

          {/* Title */}
          <h3 className="font-display text-sm font-semibold text-gray-100 line-clamp-2 leading-snug">
            {article.title}
          </h3>

          {/* Summary */}
          {article.ai_summary && (
            <p className="text-xs text-gray-400 line-clamp-2 leading-relaxed">
              {article.ai_summary}
            </p>
          )}

          {/* Tags */}
          {article.ai_tags && article.ai_tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {article.ai_tags.slice(0, 3).map((tag) => (
                <span key={tag} className="tag-pill">{tag}</span>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-1 pt-1" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={handleLike}
              className={`btn-ghost ${article.user_rating === 'liked' ? 'text-green-400' : ''}`}
              title="Like"
            >
              <ThumbsUp className={`w-4 h-4 ${article.user_rating === 'liked' ? 'fill-green-400' : ''}`} />
            </button>
            <button
              onClick={handleDislike}
              className={`btn-ghost ${article.user_rating === 'disliked' ? 'text-rose-400' : ''}`}
              title="Dislike"
            >
              <ThumbsDown className={`w-4 h-4 ${article.user_rating === 'disliked' ? 'fill-rose-400' : ''}`} />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setShowBlock(true) }}
              className="btn-ghost"
              title="Block"
            >
              <Ban className="w-4 h-4" />
            </button>
            <button
              onClick={handleReadLater}
              className={`btn-ghost ${article.read_later ? 'text-amber-pulse' : ''}`}
              title={article.read_later ? 'Remove from saved' : 'Save for later'}
            >
              {article.read_later
                ? <BookmarkCheck className="w-4 h-4 fill-amber-pulse" />
                : <Bookmark className="w-4 h-4" />}
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); handleOpen() }}
              className="btn-ghost"
              title="Open article"
            >
              <ExternalLink className="w-4 h-4" />
            </button>
          </div>
        </div>
      </article>

      {showBlock && (
        <BlockMenu
          article={article}
          onClose={() => setShowBlock(false)}
          onBlocked={handleBlocked}
        />
      )}
    </>
  )
}
