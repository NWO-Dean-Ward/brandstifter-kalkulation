import { Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Ausschreibung from './pages/Ausschreibung'
import Projekt from './pages/Projekt'
import Einstellungen from './pages/Einstellungen'

function Nav() {
  const link = ({ isActive }) =>
    `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
      isActive
        ? 'bg-orange-600 text-white'
        : 'text-slate-600 hover:bg-slate-100'
    }`

  return (
    <nav className="bg-white border-b border-slate-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 flex items-center h-14 gap-2">
        <div className="flex items-center gap-2 mr-8">
          <div className="w-8 h-8 bg-orange-600 rounded-lg flex items-center justify-center text-white font-bold text-sm">B</div>
          <span className="font-bold text-slate-800">Brandstifter</span>
        </div>
        <NavLink to="/" end className={link}>Dashboard</NavLink>
        <NavLink to="/ausschreibung" className={link}>Neue Ausschreibung</NavLink>
        <NavLink to="/einstellungen" className={link}>Einstellungen</NavLink>
      </div>
    </nav>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50">
      <Nav />
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/ausschreibung" element={<Ausschreibung />} />
          <Route path="/projekt/:id" element={<Projekt />} />
          <Route path="/einstellungen" element={<Einstellungen />} />
        </Routes>
      </main>
    </div>
  )
}
