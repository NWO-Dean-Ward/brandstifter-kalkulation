import { useState, useRef, useEffect } from 'react'
import { chat as chatApi } from '../api'

const QUICK_SUGGESTIONS = [
  'Was kosten die importierten Platten?',
  'Schlage Preise fuer alle Materialien vor',
  'Ist die Kalkulation plausibel?',
  'Welche Zuschlaege sind ueblich?',
]

function euro(val) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(val || 0)
}

export default function PersistentChat({ open, onToggle, context, onApplyAction, initialMessages }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input when opened
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 200)
  }, [open])

  // Merge initial messages (from auto-vorschlag)
  useEffect(() => {
    if (initialMessages?.length > 0) {
      setMessages(prev => [...prev, ...initialMessages])
    }
  }, [initialMessages])

  const sendMessage = async (text) => {
    if (!text.trim() || loading) return

    const userMsg = { role: 'user', content: text, ts: Date.now() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      // Rolling window: max 5 messages for context
      const historyForApi = [...messages, userMsg]
        .slice(-5)
        .map(m => ({ role: m.role, content: m.content }))

      const result = await chatApi.message({
        message: text,
        context: context || {},
        history: historyForApi,
        force_claude: false,
      })

      const assistantMsg = {
        role: 'assistant',
        content: result.text || 'Keine Antwort erhalten.',
        actions: result.actions || [],
        model_used: result.model_used || 'unknown',
        tokens: result.tokens || 0,
        ts: Date.now(),
        appliedActions: {},
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Fehler: ${err.message}`,
        actions: [],
        model_used: 'error',
        tokens: 0,
        ts: Date.now(),
        appliedActions: {},
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  const handleApplyAction = (msgIdx, actionIdx, action) => {
    if (onApplyAction) {
      onApplyAction(action)
      // Mark action as applied
      setMessages(prev => prev.map((m, i) => {
        if (i !== msgIdx) return m
        return {
          ...m,
          appliedActions: { ...m.appliedActions, [actionIdx]: true },
        }
      }))
    }
  }

  const clearChat = () => {
    setMessages([])
    setInput('')
  }

  if (!open) return null

  return (
    <div className="fixed right-0 top-16 bottom-0 w-[380px] z-40 flex flex-col animate-slide-in-right"
         style={{ background: 'rgba(15, 23, 42, 0.95)', backdropFilter: 'blur(16px)', borderLeft: '1px solid rgba(147, 51, 234, 0.3)' }}>

      {/* Header */}
      <div className="px-4 py-3 border-b border-purple-500/30 flex items-center justify-between"
           style={{ background: 'linear-gradient(135deg, rgba(147,51,234,0.15), rgba(168,85,247,0.08))' }}>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse" />
          <h2 className="font-bold text-purple-400 text-sm">KI-Chat</h2>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={clearChat} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
            Leeren
          </button>
          <button onClick={onToggle} className="text-slate-400 hover:text-white transition-colors text-lg leading-none">
            &times;
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="space-y-3 mt-4">
            <p className="text-xs text-slate-500 text-center">Wie kann ich bei der Kalkulation helfen?</p>
            <div className="space-y-2">
              {QUICK_SUGGESTIONS.map((suggestion, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(suggestion)}
                  className="w-full text-left px-3 py-2 text-xs rounded-lg border border-purple-500/20 bg-purple-500/5 hover:bg-purple-500/15 text-purple-300 transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
              msg.role === 'user'
                ? 'bg-purple-600/30 text-purple-100 border border-purple-500/30'
                : 'bg-slate-800/80 text-slate-200 border border-slate-700/50'
            }`}>
              {/* Message content */}
              <div className="whitespace-pre-wrap break-words">{msg.content}</div>

              {/* Actions */}
              {msg.actions?.length > 0 && (
                <div className="mt-2 pt-2 border-t border-slate-600/30 space-y-1.5">
                  {msg.actions.map((action, aIdx) => {
                    const isApplied = msg.appliedActions?.[aIdx]
                    return (
                      <div key={aIdx} className="flex items-center gap-2">
                        <button
                          onClick={() => handleApplyAction(idx, aIdx, action)}
                          disabled={isApplied}
                          className={`text-xs px-2 py-1 rounded transition-colors ${
                            isApplied
                              ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                              : 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30'
                          }`}
                        >
                          {isApplied ? 'Uebernommen' : 'Uebernehmen'}
                        </button>
                        <span className="text-xs text-slate-400 truncate">
                          {action.type === 'set_price' && `${action.bezeichnung}: ${euro(action.value)}`}
                          {action.type === 'set_hours' && `${action.bezeichnung}: ${action.value}h`}
                          {action.type === 'set_zuschlag' && `${action.field}: ${action.value}%`}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Model badge */}
              {msg.role === 'assistant' && msg.model_used && msg.model_used !== 'error' && (
                <div className="mt-1.5 flex items-center gap-2 text-[10px] text-slate-500">
                  <span className={`px-1.5 py-0.5 rounded ${
                    msg.model_used.includes('claude') ? 'bg-orange-500/10 text-orange-400' : 'bg-blue-500/10 text-blue-400'
                  }`}>
                    {msg.model_used.includes('claude') ? 'Claude' : 'Ollama'}
                  </span>
                  {msg.tokens > 0 && <span>{msg.tokens} tokens</span>}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-slate-800/80 border border-slate-700/50 rounded-xl px-3 py-2 text-sm text-slate-400">
              <span className="animate-pulse">Denke nach...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="px-3 py-3 border-t border-purple-500/20">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Frage zur Kalkulation..."
            className="flex-1 bg-slate-800/80 border border-slate-600/50 rounded-lg px-3 py-2 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-purple-500/50 focus:border-purple-500/50 placeholder-slate-500"
            disabled={loading}
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={loading || !input.trim()}
            className="px-3 py-2 rounded-lg text-sm font-medium transition-colors bg-purple-600/80 hover:bg-purple-600 disabled:opacity-30 text-white"
          >
            &rarr;
          </button>
        </div>
      </div>
    </div>
  )
}
