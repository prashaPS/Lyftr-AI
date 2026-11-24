import { useState, useRef, useEffect, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Generate a stable session ID for this page load
const SESSION_ID = `s-${uuidv4().slice(0, 8)}`

function MetaBar({ metadata }) {
  if (!metadata) return null
  const isCache = metadata.resolution_source === 'LLM_CACHE'
  return (
    <div className="meta-bar">
      <span className={`meta-chip ${isCache ? 'source-cache' : 'source-live'}`}>
        <span className="meta-dot" />
        <span data-testid="meta-source">{metadata.resolution_source}</span>
      </span>
      <span className="meta-chip">
        🤖 <span data-testid="meta-model">{metadata.model}</span>
      </span>
      <span className="meta-chip">
        ⚡ <span data-testid="meta-latency">{metadata.latency_ms} ms</span>
      </span>
      <span className="meta-chip">
        ↑ <span data-testid="meta-input-tokens">{metadata.input_tokens}</span> in
      </span>
      <span className="meta-chip">
        ↓ <span data-testid="meta-output-tokens">{metadata.output_tokens}</span> out
      </span>
      {metadata.key_id && (
        <span className="meta-chip">🔑 {metadata.key_id}</span>
      )}
      {metadata.fallback_attempts > 0 && (
        <span className="meta-chip" style={{ color: '#f59e0b', borderColor: '#f59e0b' }}>
          ⚠ {metadata.fallback_attempts} fallback{metadata.fallback_attempts > 1 ? 's' : ''}
        </span>
      )}
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="message-row assistant">
      <div className="avatar assistant">AI</div>
      <div className="typing-indicator">
        <div className="typing-dot" />
        <div className="typing-dot" />
        <div className="typing-dot" />
      </div>
    </div>
  )
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [apiStatus, setApiStatus] = useState('checking')
  const chatEndRef = useRef(null)
  const textareaRef = useRef(null)

  // Health check on mount
  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(() => setApiStatus('ok'))
      .catch(() => setApiStatus('error'))
  }, [])

  // Auto-scroll
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`
  }, [input])

  const sendMessage = useCallback(async () => {
    const text = input.trim()
    if (!text || isLoading) return

    const userMsg = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setIsLoading(true)

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: SESSION_ID,
          message: text,
          ...(systemPrompt.trim() ? { system_prompt: systemPrompt.trim() } : {}),
        }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
        setMessages(prev => [
          ...prev,
          { role: 'error', content: `Error: ${err.detail || 'Something went wrong'}` },
        ])
        return
      }

      const data = await res.json()
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: data.reply, metadata: data.metadata },
      ])
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { role: 'error', content: `Network error: ${err.message}` },
      ])
    } finally {
      setIsLoading(false)
      textareaRef.current?.focus()
    }
  }, [input, isLoading, systemPrompt])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const canSend = input.trim().length > 0 && !isLoading

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-logo">L</div>
        <div>
          <div className="header-title">Lyftr AI Chat</div>
          <div className="header-subtitle">Session: {SESSION_ID}</div>
        </div>
        <div className="header-status">
          <span className={`status-dot ${apiStatus === 'ok' ? 'ok' : ''}`} />
          {apiStatus === 'ok' ? 'Backend connected' : apiStatus === 'checking' ? 'Connecting…' : 'Backend unreachable'}
        </div>
      </header>

      {/* System prompt */}
      <div className="system-prompt-bar">
        <label>System Prompt (optional)</label>
        <input
          data-testid="system-prompt-input"
          type="text"
          placeholder="e.g. You are a helpful assistant that answers concisely."
          value={systemPrompt}
          onChange={e => setSystemPrompt(e.target.value)}
          disabled={isLoading}
        />
      </div>

      {/* Chat messages */}
      <div className="chat-area">
        {messages.length === 0 && !isLoading && (
          <div className="empty-state">
            <div className="empty-state-icon">💬</div>
            <h2>Start a conversation</h2>
            <p>Ask anything — your session is remembered across turns.</p>
          </div>
        )}

        {messages.map((msg, i) => {
          if (msg.role === 'user') {
            return (
              <div key={i} className="message-row user">
                <div className="avatar user">U</div>
                <div className="message-col">
                  <div className="bubble user">{msg.content}</div>
                </div>
              </div>
            )
          }

          if (msg.role === 'error') {
            return (
              <div key={i} className="message-row assistant">
                <div className="avatar assistant">!</div>
                <div className="message-col">
                  <div className="bubble error">{msg.content}</div>
                </div>
              </div>
            )
          }

          // assistant
          return (
            <div key={i} className="message-row assistant" data-testid="assistant-message">
              <div className="avatar assistant">AI</div>
              <div className="message-col">
                <div className="bubble assistant">{msg.content}</div>
                <MetaBar metadata={msg.metadata} />
              </div>
            </div>
          )
        })}

        {isLoading && <TypingIndicator />}
        <div ref={chatEndRef} />
      </div>

      {/* Input */}
      <div className="input-bar">
        <div className="input-row">
          <textarea
            ref={textareaRef}
            data-testid="chat-input"
            className="chat-textarea"
            placeholder="Type a message… (Enter to send, Shift+Enter for new line)"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            rows={1}
          />
          <button
            data-testid="send-button"
            className="send-btn"
            onClick={sendMessage}
            disabled={!canSend}
            aria-label="Send message"
          >
            ➤
          </button>
        </div>
        <div className="input-hint">Enter to send · Shift+Enter for newline</div>
      </div>
    </div>
  )
}
