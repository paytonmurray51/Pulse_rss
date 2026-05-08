import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getStats } from './lib/api'
import TopBar from './components/TopBar'
import { BottomNav, Sidebar } from './components/Nav'
import Home from './pages/Home'
import Saved from './pages/Saved'
import Feeds from './pages/Feeds'
import Settings from './pages/Settings'

function Layout() {
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
          </Routes>
        </main>
        <BottomNav />
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  )
}
