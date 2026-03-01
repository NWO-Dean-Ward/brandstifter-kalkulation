import { useState, useCallback, useRef } from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import Dashboard from './pages/Dashboard'
import Ausschreibung from './pages/Ausschreibung'
import Projekt from './pages/Projekt'
import Einstellungen from './pages/Einstellungen'
import Werkzeuge from './pages/Werkzeuge'
import Kalkulator from './pages/Kalkulator'
import PersistentChat from './components/PersistentChat'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/ausschreibung', label: 'Ausschreibung' },
  { to: '/kalkulator', label: 'Kalkulator' },
  { to: '/werkzeuge', label: 'Werkzeuge' },
  { to: '/einstellungen', label: 'Einstellungen' },
]

function Nav({ chatOpen, onChatToggle }) {
  return (
    <nav className="bg-slate-900/80 backdrop-blur-xl border-b border-slate-700/50 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 flex items-center h-16 gap-1">
        {/* Logo */}
        <div className="flex items-center gap-3 mr-10">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center font-black text-sm text-white"
               style={{ background: 'linear-gradient(135deg, #b45309, #d97706)' }}>
            ME
          </div>
          <div className="flex flex-col">
            <span className="font-bold text-white text-sm leading-tight tracking-wide">Meister Eder</span>
            <span className="text-[10px] text-amber-500/80 font-medium tracking-widest uppercase">Kalkulation</span>
          </div>
        </div>

        {/* Nav Links */}
        <div className="flex items-center gap-1">
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn('px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                  isActive
                    ? 'nav-active'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </div>

        {/* Right side – KI-Chat toggle + status dot */}
        <div className="ml-auto flex items-center gap-3">
          <Button
            variant="outline"
            onClick={onChatToggle}
            className={cn(
              'text-sm font-medium transition-all duration-200',
              chatOpen
                ? 'bg-purple-600 text-white border-purple-600 shadow-lg shadow-purple-900/30 hover:bg-purple-700'
                : 'border-purple-500/30 bg-purple-500/10 hover:bg-purple-500/20 text-purple-400'
            )}
          >
            KI-Chat
          </Button>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" title="Server online" />
            <span className="text-xs text-slate-500">v0.1</span>
          </div>
        </div>
      </div>
    </nav>
  )
}

export default function App() {
  const [chatOpen, setChatOpen] = useState(false)
  const [chatContext, setChatContext] = useState({})
  const [chatInitialMessages, setChatInitialMessages] = useState(null)
  const actionHandlerRef = useRef(null)

  const handleChatToggle = useCallback(() => {
    setChatOpen(prev => !prev)
  }, [])

  const updateChatContext = useCallback((ctx) => {
    setChatContext(ctx)
  }, [])

  const addChatMessages = useCallback((msgs) => {
    setChatInitialMessages(msgs)
    setChatOpen(true)
  }, [])

  const registerActionHandler = useCallback((handler) => {
    actionHandlerRef.current = handler
  }, [])

  const handleApplyAction = useCallback((action) => {
    if (actionHandlerRef.current) {
      actionHandlerRef.current(action)
    }
  }, [])

  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(180deg, #0f172a 0%, #1a1f35 100%)' }}>
      <Nav chatOpen={chatOpen} onChatToggle={handleChatToggle} />
      <main className={`max-w-7xl mx-auto px-6 py-8 transition-all duration-300 ${chatOpen ? 'mr-[380px]' : ''}`}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/ausschreibung" element={<Ausschreibung />} />
          <Route path="/projekt/:id" element={<Projekt />} />
          <Route path="/kalkulator" element={
            <Kalkulator
              updateChatContext={updateChatContext}
              addChatMessages={addChatMessages}
              registerActionHandler={registerActionHandler}
            />
          } />
          <Route path="/werkzeuge" element={<Werkzeuge />} />
          <Route path="/einstellungen" element={<Einstellungen />} />
        </Routes>
      </main>
      <PersistentChat
        open={chatOpen}
        onToggle={handleChatToggle}
        context={chatContext}
        onApplyAction={handleApplyAction}
        initialMessages={chatInitialMessages}
      />
    </div>
  )
}
