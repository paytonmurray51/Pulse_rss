import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  X, Check, Settings as SettingsIcon, Users, MessageSquarePlus,
  ShieldCheck, Send, Inbox, AlertCircle,
} from 'lucide-react'
import {
  getProfile, updateProfile, getBlocks, deleteBlock,
  getAppSettings, updateAppSettings,
  getMembers, inviteMember, revokeMember,
  submitSuggestion, getSuggestions, resolveSuggestion,
} from '../lib/api'
import { useAuth } from '../lib/auth'
import { formatDistanceToNow } from '../lib/dateUtils'

const REFRESH_OPTIONS = [
  { minutes: 360, label: 'Every 6 hours' },
  { minutes: 720, label: 'Twice a day' },
  { minutes: 1440, label: 'Once a day' },
  { minutes: 2880, label: 'Every 2 days' },
  { minutes: 10080, label: 'Once a week' },
]

const SUGGESTIONS = [
  'SRE', 'DevOps', 'Kubernetes', 'Terraform', 'GCP', 'Python',
  'Overlanding', 'Off-road', 'Dallas Stars', 'Hockey',
  'Electric Guitar', 'Sourdough', 'Baking', 'AI', 'Rust',
  'Linux', 'Open Source', 'Security', 'Cloud Native', 'Homebrew',
]

function Section({ icon: Icon, title, subtitle, children }) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
          {Icon && <Icon className="w-4 h-4 text-gray-500" />}
          {title}
        </h2>
        {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
      </div>
      {children}
    </section>
  )
}

// ─── admin: members ──────────────────────────────────────────────────────────

function MembersPanel() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')

  const { data: members = [] } = useQuery({ queryKey: ['members'], queryFn: getMembers })

  const add = async () => {
    const value = email.trim().toLowerCase()
    if (!value) return
    setError('')
    try {
      await inviteMember({ email: value })
      queryClient.invalidateQueries({ queryKey: ['members'] })
      setEmail('')
    } catch (e) {
      setError(e.message || 'Could not invite that address')
    }
  }

  const revoke = async (target) => {
    if (!confirm(`Remove access for ${target}? Their saves and settings are kept.`)) return
    try {
      await revokeMember(target)
      queryClient.invalidateQueries({ queryKey: ['members'] })
    } catch (e) {
      setError(e.message || 'Could not remove that member')
    }
  }

  return (
    <Section
      icon={Users}
      title="Members"
      subtitle="Only these Google addresses can sign in. Everyone gets their own feed and filters."
    >
      {error && (
        <p className="text-sm text-rose-400 bg-rose-400/10 border border-rose-400/20
                      rounded-lg px-3 py-2">{error}</p>
      )}

      <div className="bg-bg-surface border border-bg-border rounded-xl divide-y divide-bg-border">
        {members.map((m) => (
          <div key={m.email} className="flex items-center gap-3 px-4 py-2.5">
            <div className="w-7 h-7 rounded-full bg-bg-elevated border border-bg-border shrink-0
                            flex items-center justify-center overflow-hidden text-xs text-gray-400">
              {m.picture
                ? <img src={m.picture} alt="" className="w-full h-full object-cover"
                       referrerPolicy="no-referrer" />
                : (m.name || m.email).charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-gray-200 truncate">{m.name || m.email}</span>
                {m.is_admin && <ShieldCheck className="w-3.5 h-3.5 text-accent shrink-0" />}
              </div>
              <p className="text-xs text-gray-500 truncate">
                {m.name ? `${m.email} · ` : ''}
                {m.user_id
                  ? m.last_seen_at
                    ? `last seen ${formatDistanceToNow(new Date(m.last_seen_at))}`
                    : 'signed in'
                  : 'invited, not signed in yet'}
              </p>
            </div>
            {m.email !== user?.email && (
              <button
                onClick={() => revoke(m.email)}
                className="btn-ghost text-rose-400/60 hover:text-rose-400"
                title="Remove access"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          type="email"
          className="input-field flex-1"
          placeholder="family@gmail.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
        />
        <button onClick={add} className="btn-secondary px-3">Invite</button>
      </div>
    </Section>
  )
}

// ─── admin: scheduled sync ───────────────────────────────────────────────────

function SyncPanel() {
  const queryClient = useQueryClient()
  const { data: settings } = useQuery({ queryKey: ['app-settings'], queryFn: getAppSettings })
  const [enabled, setEnabled] = useState(false)
  const [interval, setIntervalValue] = useState(1440)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (settings) {
      setEnabled(settings.auto_refresh_enabled)
      setIntervalValue(settings.refresh_interval_minutes ?? 1440)
    }
  }, [settings])

  const save = async (next) => {
    await updateAppSettings(next)
    queryClient.invalidateQueries({ queryKey: ['app-settings'] })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <Section
      icon={SettingsIcon}
      title="Scheduled sync"
      subtitle="Off by default — Refresh syncs on demand. When on, Pulse fetches and scores for everyone who signed in recently."
    >
      <div className="flex items-center justify-between gap-4">
        <span className="text-sm text-gray-400">
          {enabled ? 'Running automatically' : 'On demand only'}
        </span>
        <button
          role="switch"
          aria-checked={enabled}
          onClick={() => { const v = !enabled; setEnabled(v); save({ auto_refresh_enabled: v }) }}
          className={`relative w-11 h-6 rounded-full shrink-0 transition-colors
            ${enabled ? 'bg-accent' : 'bg-bg-elevated border border-bg-border'}`}
        >
          <span className={`absolute top-1 w-4 h-4 rounded-full transition-transform
            ${enabled ? 'translate-x-6 bg-bg-base' : 'translate-x-1 bg-gray-500'}`} />
        </button>
      </div>

      {enabled && (
        <select
          className="input-field"
          value={interval}
          onChange={(e) => {
            const v = parseInt(e.target.value, 10)
            setIntervalValue(v)
            save({ refresh_interval_minutes: v })
          }}
        >
          {REFRESH_OPTIONS.map((o) => (
            <option key={o.minutes} value={o.minutes}>{o.label}</option>
          ))}
        </select>
      )}

      <p className="text-xs text-gray-500">
        {settings?.last_auto_refresh_at
          ? `Last scheduled sync ${formatDistanceToNow(new Date(settings.last_auto_refresh_at))}.`
          : 'No scheduled sync has run yet.'}
        {saved && <span className="text-accent ml-2">Saved</span>}
      </p>
    </Section>
  )
}

// ─── admin: suggestion inbox ─────────────────────────────────────────────────

function SuggestionInbox() {
  const queryClient = useQueryClient()
  const { data: items = [] } = useQuery({
    queryKey: ['suggestions'],
    queryFn: () => getSuggestions(false),
  })

  if (items.length === 0) return null

  const toggle = async (id) => {
    await resolveSuggestion(id)
    queryClient.invalidateQueries({ queryKey: ['suggestions'] })
  }

  return (
    <Section icon={Inbox} title={`Suggestions (${items.length})`}>
      <div className="bg-bg-surface border border-bg-border rounded-xl divide-y divide-bg-border">
        {items.map((s) => (
          <div key={s.id} className="px-4 py-3 flex gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-sm text-gray-200 whitespace-pre-wrap break-words">{s.message}</p>
              <p className="text-xs text-gray-500 mt-1">
                {s.author_name || s.author_email} · {formatDistanceToNow(new Date(s.created_at))}
                {!s.emailed && (
                  <span className="text-score-mid ml-2 inline-flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" /> not emailed
                  </span>
                )}
              </p>
            </div>
            <button
              onClick={() => toggle(s.id)}
              className="btn-ghost shrink-0 self-start"
              title="Mark resolved"
            >
              <Check className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </Section>
  )
}

// ─── everyone: suggestion form ───────────────────────────────────────────────

function SuggestionForm() {
  const [message, setMessage] = useState('')
  const [state, setState] = useState('idle')
  const [error, setError] = useState('')

  const send = async () => {
    if (message.trim().length < 3) return
    setState('sending')
    setError('')
    try {
      await submitSuggestion(message.trim())
      setMessage('')
      setState('sent')
      setTimeout(() => setState('idle'), 4000)
    } catch (e) {
      setError(e.message || 'Could not send that')
      setState('idle')
    }
  }

  return (
    <Section
      icon={MessageSquarePlus}
      title="Suggest an improvement"
      subtitle="Goes straight to the owner's inbox."
    >
      {error && (
        <p className="text-sm text-rose-400 bg-rose-400/10 border border-rose-400/20
                      rounded-lg px-3 py-2">{error}</p>
      )}
      <textarea
        className="input-field min-h-[90px] resize-y"
        placeholder="Something broken, missing, or worth adding?"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
      />
      <button
        onClick={send}
        disabled={state === 'sending' || message.trim().length < 3}
        className="btn-primary flex items-center gap-2 disabled:opacity-50"
      >
        {state === 'sent'
          ? <><Check className="w-4 h-4" /> Sent — thank you</>
          : <><Send className="w-4 h-4" /> {state === 'sending' ? 'Sending…' : 'Send suggestion'}</>}
      </button>
    </Section>
  )
}

// ─── page ────────────────────────────────────────────────────────────────────

export default function Settings() {
  const queryClient = useQueryClient()
  const { isAdmin } = useAuth()
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: getProfile })
  const { data: blocks = [] } = useQuery({ queryKey: ['blocks'], queryFn: getBlocks })

  const [interests, setInterests] = useState([])
  const [inputVal, setInputVal] = useState('')
  const [threshold, setThreshold] = useState(5.0)

  useEffect(() => {
    if (profile) {
      setInterests(profile.interests || [])
      setThreshold(profile.min_score_threshold ?? 5.0)
    }
  }, [profile])

  const addInterest = (val) => {
    const trimmed = val.trim()
    if (trimmed && !interests.includes(trimmed)) setInterests([...interests, trimmed])
    setInputVal('')
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateProfile({ interests, min_score_threshold: threshold })
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
    await deleteBlock(id)
    queryClient.setQueryData(['blocks'], (old) => old ? old.filter((b) => b.id !== id) : old)
  }

  const sources = blocks.filter((b) => b.block_type === 'source')
  const topics = blocks.filter((b) => b.block_type === 'topic')
  const unused = SUGGESTIONS.filter((s) => !interests.includes(s))

  return (
    <div className="max-w-2xl mx-auto px-4 py-4 space-y-8 pb-8">
      <div className="flex items-center gap-2">
        <SettingsIcon className="w-5 h-5 text-accent" />
        <h1 className="font-display text-xl font-semibold text-white">Settings</h1>
      </div>

      <Section title="Your interests" subtitle="Claude scores articles against these — yours only.">
        <div className="flex flex-wrap gap-2">
          {interests.map((interest, i) => (
            <span key={i} className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full
                                     text-sm bg-accent/15 text-accent border border-accent/25">
              {interest}
              <button
                onClick={() => setInterests(interests.filter((_, idx) => idx !== i))}
                className="text-accent/60 hover:text-accent-hover transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </span>
          ))}
        </div>

        <div className="flex gap-2">
          <input
            className="input-field flex-1"
            placeholder="Add interest (press Enter)"
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addInterest(inputVal) } }}
          />
          <button onClick={() => addInterest(inputVal)} className="btn-secondary px-3">Add</button>
        </div>

        {unused.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {unused.map((s) => (
              <button
                key={s}
                onClick={() => addInterest(s)}
                className="tag-pill hover:border-accent/30 hover:text-gray-300 cursor-pointer"
              >
                + {s}
              </button>
            ))}
          </div>
        )}
      </Section>

      <Section title="Minimum score" subtitle="Articles below this stay out of your feed.">
        <div className="flex items-center gap-4">
          <input
            type="range" min={1} max={9} step={0.5} value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
            className="flex-1 accent-accent"
          />
          <span className="text-accent font-semibold w-10 text-right tabular-nums">
            {threshold.toFixed(1)}
          </span>
        </div>
      </Section>

      {blocks.length > 0 && (
        <Section
          title="Your blocks"
          subtitle="Applied before scoring — matching content never reaches your feed."
        >
          {sources.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Sources</p>
              <div className="bg-bg-surface border border-bg-border rounded-xl
                              divide-y divide-bg-border">
                {sources.map((b) => (
                  <div key={b.id} className="flex items-center justify-between px-4 py-2.5">
                    <span className="text-sm text-gray-300">{b.value}</span>
                    <button onClick={() => handleDeleteBlock(b.id)}
                            className="btn-ghost text-rose-400/60 hover:text-rose-400">
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
                  <span key={b.id} className="inline-flex items-center gap-1.5 px-3 py-1
                                              rounded-full text-sm bg-rose-500/10 text-rose-400
                                              border border-rose-500/20">
                    {b.value}
                    <button onClick={() => handleDeleteBlock(b.id)}
                            className="text-rose-400/60 hover:text-rose-300">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            </div>
          )}
        </Section>
      )}

      <button
        onClick={handleSave}
        disabled={saving}
        className="btn-primary flex items-center gap-2 disabled:opacity-60"
      >
        {saved ? <><Check className="w-4 h-4" /> Saved</> : saving ? 'Saving…' : 'Save settings'}
      </button>

      <div className="border-t border-bg-border pt-8 space-y-8">
        <SuggestionForm />
      </div>

      {isAdmin && (
        <div className="border-t border-bg-border pt-8 space-y-8">
          <p className="text-[10px] uppercase tracking-wider text-gray-600">Admin</p>
          <MembersPanel />
          <SyncPanel />
          <SuggestionInbox />
        </div>
      )}
    </div>
  )
}
