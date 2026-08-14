import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getStats } from './lib/api'
import { AuthProvider, useAuth } from './lib/auth'
import TopBar from './components/TopBar'
import { BottomNav, Sidebar } from './components/Nav'
import Home from './pages/Home'
import Saved from './pages/Saved'
import Feeds from './pages/Feeds'
import Settings from './pages/Settings'
import Login from './pages/Login'

function Shell() {
  const queryClient = useQueryClient()
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
    refetchInterval: 60_000,
  })

  const handleRefreshed = () => {
    queryClient.invalidateQueries({ queryKey: ['articles'] })
    queryClient.invalidateQueries({ queryKey: ['stats'] })
  }

  return (
    <div className="flex h-full bg-bg-base">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <TopBar stats={stats} onRefreshed={handleRefreshed} />
        <main className="flex-1 overflow-y-auto pb-20 sm:pb-0">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/saved" element={<Saved />} />
            <Route path="/feeds" element={<Feeds />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <BottomNav />
      </div>
    </div>
  )
}

function Gate() {
  const { user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-gray-500">
        Loading…
      </div>
    )
  }

  if (!user) {
    // /login renders itself; everything else bounces there.
    return location.pathname === '/login'
      ? <Login />
      : <Navigate to="/login" replace />
  }

  return location.pathname === '/login' ? <Navigate to="/" replace /> : <Shell />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </BrowserRouter>
  )
}
