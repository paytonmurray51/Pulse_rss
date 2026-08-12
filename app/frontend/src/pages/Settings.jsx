import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getProfile, updateProfile, getBlocks, deleteBlock } from '../lib/api'
import { X, Check, Settings as SettingsIcon } from 'lucide-react'

const SUGGESTIONS = [
  'SRE', 'DevOps', 'Kubernetes', 'Terraform', 'GCP', 'Python',
  'Overlanding', 'Off-road', 'Dallas Stars', 'Hockey',
  'Electric Guitar', 'Sourdough', 'Baking', 'AI', 'Rust',
  'Linux', 'Open Source', 'Security', 'Cloud Native', 'Homebrew',
]

export default function Settings() {
  const queryClient = useQueryClient()
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: getProfile })
  const { data: blocks = [] } = useQuery({ queryKey: ['blocks'], queryFn: getBlocks })

  const [interests, setInterests] = useState([])
  const [inputVal, setInputVal] = useState('')
  const [threshold, setThreshold] = useState(5.0)
  const [interval, setInterval] = useState(30)

  useEffect(() => {
    if (profile) {
      setInterests(profile.interests || [])
      setThreshold(profile.min_score_threshold ?? 5.0)
      setInterval(profile.refresh_interval_minutes ?? 30)
    }
  }, [profile])

  const addInterest = (val) => {
    const trimmed = val.trim()
    if (trimmed && !interests.includes(trimmed)) {
      setInterests([...interests, trimmed])
    }
    setInputVal('')
  }

  const removeInterest = (i) => {
    setInterests(interests.filter((_, idx) => idx !== i))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateProfile({ interests, min_score_threshold: threshold, refresh_interval_minutes: interval })
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (e) {
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteBlock = async (id) => {
    try {
      await deleteBlock(id)
      queryClient.setQueryData(['blocks'], (old) => old ? old.filter((b) => b.id !== id) : old)
    } catch (e) {
      console.error(e)
    }
  }

  const sources = blocks.filter((b) => b.block_type === 'source')
  const topics = blocks.filter((b) => b.block_type === 'topic')
  const unusedSuggestions = SUGGESTIONS.filter((s) => !interests.includes(s))

  return (
    <div className="max-w-2xl mx-auto px-4 py-4 space-y-8 pb-8">
      <div className="flex items-center gap-2">
        <SettingsIcon className="w-5 h-5 text-accent" />
        <h1 className="font-display text-xl font-semibold text-white">Settings</h1>
      </div>

      {/* Interests */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-300">Your Interests</h2>
        <p className="text-xs text-gray-500">
          Claude uses these to score and rank articles for you.
        </p>

        {/* Active chips */}
        <div className="flex flex-wrap gap-2">
          {interests.map((interest, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm
                         bg-accent/15 text-accent border border-accent/25"
            >
              {interest}
              <button
                onClick={() => removeInterest(i)}
                className="text-accent/60 hover:text-accent-hover transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </span>
          ))}
        </div>

        {/* Input */}
        <div className="flex gap-2">
          <input
            className="input-field flex-1"
            placeholder="Add interest (press Enter)"
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                addInterest(inputVal)
              }
            }}
          />
          <button
            onClick={() => addInterest(inputVal)}
            className="btn-secondary px-3"
          >
            Add
          </button>
        </div>

        {/* Suggestions */}
        {unusedSuggestions.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {unusedSuggestions.map((s) => (
              <button
                key={s}
                onClick={() => addInterest(s)}
                className="tag-pill hover:border-accent/30 hover:text-gray-300 transition-colors cursor-pointer"
              >
                + {s}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Score threshold */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-300">Minimum Score Threshold</h2>
        <p className="text-xs text-gray-500">
          Articles scoring below this won&apos;t appear in your feed.
        </p>
        <div className="flex items-center gap-4">
          <input
            type="range"
            min={1}
            max={9}
            step={0.5}
            value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
            className="flex-1 accent-accent"
          />
          <span className="text-accent font-semibold w-10 text-right tabular-nums">
            {threshold.toFixed(1)}
          </span>
        </div>
      </section>

      {/* Refresh interval */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-300">Refresh Interval</h2>
        <div className="flex items-center gap-4">
          <input
            type="range"
            min={5}
            max={180}
            step={5}
            value={interval}
            onChange={(e) => setInterval(parseInt(e.target.value, 10))}
            className="flex-1 accent-accent"
          />
          <span className="text-accent font-semibold w-20 text-right tabular-nums">
            {interval}m
          </span>
        </div>
      </section>

      {/* Active blocks */}
      {blocks.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-300">Active Blocks</h2>
          <p className="text-xs text-gray-500">
            Applied before AI scoring — matching content never reaches your feed.
          </p>

          {sources.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Sources</p>
              <div className="bg-bg-surface border border-bg-border rounded-xl divide-y divide-bg-border">
                {sources.map((b) => (
                  <div key={b.id} className="flex items-center justify-between px-4 py-2.5">
                    <span className="text-sm text-gray-300">{b.value}</span>
                    <button
                      onClick={() => handleDeleteBlock(b.id)}
                      className="btn-ghost text-rose-400/60 hover:text-rose-400"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {topics.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Topics</p>
              <div className="flex flex-wrap gap-2">
                {topics.map((b) => (
                  <span
                    key={b.id}
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm
                               bg-rose-500/10 text-rose-400 border border-rose-500/20"
                  >
                    {b.value}
                    <button
                      onClick={() => handleDeleteBlock(b.id)}
                      className="text-rose-400/60 hover:text-rose-300 transition-colors"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Save */}
      <div className="pt-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-primary flex items-center gap-2 disabled:opacity-60"
        >
          {saved ? (
            <>
              <Check className="w-4 h-4" /> Saved!
            </>
          ) : saving ? (
            'Saving…'
          ) : (
            'Save Settings'
          )}
        </button>
      </div>
    </div>
  )
}
