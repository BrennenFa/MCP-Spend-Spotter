'use client'

import { useState, KeyboardEvent, useRef, useEffect } from 'react'

interface InputAreaProps {
  onSendMessage: (message: string) => void
  isLoading: boolean
}

export default function InputArea({ onSendMessage, isLoading }: InputAreaProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = '24px'
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`
    }
  }, [input])

  const handleSend = () => {
    if (input.trim() && !isLoading) {
      onSendMessage(input.trim())
      setInput('')
    }
  }

  const handleKeyPress = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="sticky bottom-0 bg-gradient-to-t from-white via-white to-transparent dark:from-gray-950 dark:via-gray-950 pt-8 pb-6 px-4">
      <div className="max-w-[800px] mx-auto">
        <div className="relative bg-white dark:bg-gray-900 rounded-3xl shadow-[0_0_0_1px_rgba(0,0,0,0.05),0_4px_16px_rgba(0,0,0,0.08)] dark:shadow-[0_0_0_1px_rgba(255,255,255,0.1),0_4px_16px_rgba(0,0,0,0.4)] transition-shadow hover:shadow-[0_0_0_1px_rgba(0,0,0,0.05),0_4px_20px_rgba(0,0,0,0.12)] dark:hover:shadow-[0_0_0_1px_rgba(255,255,255,0.15),0_4px_20px_rgba(0,0,0,0.5)]">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyPress}
            placeholder="Ask about NC budget or vendor payments..."
            className="w-full min-h-[24px] max-h-[200px] resize-none rounded-3xl px-6 py-4 pr-14 bg-transparent text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none"
            disabled={isLoading}
            rows={1}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="absolute bottom-3 right-3 w-9 h-9 flex items-center justify-center rounded-full bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 hover:bg-gray-700 dark:hover:bg-gray-300 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-gray-900 dark:disabled:hover:bg-gray-100 transition-all duration-200 disabled:scale-90"
            aria-label="Send message"
          >
            {isLoading ? (
              <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-xs text-center text-gray-500 dark:text-gray-500 mt-3 px-4">
          NC Spend Tracker can make mistakes. Please verify important information.
        </p>
      </div>
    </div>
  )
}
