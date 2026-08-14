import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Zap, AlertCircle } from 'lucide-react'
import { getAuthConfig } from '../lib/api'

const ERRORS = {
  not_invited:
    "This Google account isn't on the invite list. Ask the owner of this Pulse to add your address.",
  bad_state: 'Sign-in expired before it finished. Please try again.',
  missing_code: 'Google did not complete the sign-in. Please try again.',
  no_email: 'Google did not share an email address with Pulse.',
  access_denied: 'Sign-in was cancelled.',
}

function GoogleMark() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.6 2.6 30.2 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.8 6.1C12.3 13.2 17.7 9.5 24 9.5z"/>
      <path fill="#4285F4" d="M46.6 24.6c0-1.6-.1-3.1-.4-4.6H24v9.1h12.7c-.6 3-2.3 5.500-4.8 7.2l7.5 5.8c4.4-4.1 7.2-10.1 7.2-17.5z"/>
      <path fill="#FBBC05" d="M10.4 28.7c-.5-1.5-.8-3-.8-4.7s.3-3.2.8-4.7l-7.8-6.1C1 16.3 0 20 0 24s1 7.7 2.6 10.8l7.8-6.1z"/>
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.5-5.8c-2.1 1.4-4.8 2.3-8.4 2.3-6.3 0-11.7-3.7-13.6-9.8l-7.8 6.1C6.5 42.6 14.6 48 24 48z"/>
    </svg>
  )
}

export default function Login() {
  const [params] = useSearchParams()
  const errorKey = params.get('error')
  const { data: config, isLoading } = useQuery({
    queryKey: ['auth-config'],
    queryFn: getAuthConfig,
    retry: false,
  })

  const message = errorKey ? ERRORS[errorKey] || `Sign-in failed (${errorKey}).` : null

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-base px-4">
      <div className="w-full max-w-sm text-center">
        <div className="flex items-center justify-center gap-2 mb-2">
          <Zap className="w-7 h-7 text-accent" />
          <span className="font-display text-3xl font-semibold text-white">Pulse</span>
        </div>
        <p className="text-sm text-gray-500 mb-8">
          Your feeds, ranked for you.
        </p>

        {message && (
          <div className="flex items-start gap-2 text-left text-sm text-gray-300 bg-bg-surface
                          border border-bg-border rounded-xl p-3 mb-5">
            <AlertCircle className="w-4 h-4 text-score-low shrink-0 mt-0.5" />
            <span>{message}</span>
          </div>
        )}

        {isLoading ? (
          <div className="text-sm text-gray-500">Loading…</div>
        ) : config?.google_enabled ? (
          <a
            href="/api/auth/login"
            className="w-full inline-flex items-center justify-center gap-2.5 px-4 py-2.5
                       rounded-lg bg-accent text-bg-base font-semibold text-sm
                       hover:bg-accent-hover transition-colors"
          >
            <GoogleMark />
            Continue with Google
          </a>
        ) : (
          <div className="text-sm text-gray-400 bg-bg-surface border border-bg-border
                          rounded-xl p-4 text-left">
            Google sign-in isn&apos;t configured on this server yet. The owner needs to set
            <code className="mx-1 px-1 rounded bg-bg-elevated text-accent text-xs">
              GOOGLE_CLIENT_ID
            </code>
            and
            <code className="mx-1 px-1 rounded bg-bg-elevated text-accent text-xs">
              GOOGLE_CLIENT_SECRET
            </code>.
          </div>
        )}

        <p className="text-xs text-gray-600 mt-8">
          Pulse is invite-only. Accounts are created by the owner.
        </p>
      </div>
    </div>
  )
}
