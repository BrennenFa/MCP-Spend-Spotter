'use client'

import { useState, useEffect, useRef } from 'react'
import { Message, ChatResponse } from '@/types/chat'
import MessageBubble from './MessageBubble'
import InputArea from './InputArea'
import LoadingIndicator from './LoadingIndicator'

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const sessionId = useRef(`session-${Date.now()}`)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSendMessage = async (content: string) => {
    // Add user message immediately
    const userMessage: Message = {
      role: 'user',
      content,
      timestamp: new Date()
    }
    setMessages(prev => [...prev, userMessage])
    setIsLoading(true)

    try {
      // Call Next.js API route (which proxies to FastAPI backend)
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: content,
          session_id: sessionId.current
        })
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.statusText}`)
      }

      const data: ChatResponse = await response.json()

      // Add assistant message instantly
      const assistantMessage: Message = {
        role: 'assistant',
        content: data.answer,
        data: data.data,  // Add query results data
        graph: data.graph,
        sqlQuery: data.sql_query,
        timestamp: new Date()
      }
      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      console.error('Error sending message:', error)

      const errorMessage: Message = {
        role: 'assistant',
        content: `Error: ${error instanceof Error ? error.message : 'Unknown error occurred'}. Please try again.`,
        timestamp: new Date()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const examplePrompts = [
    "How much did NC spend on transportation in 2025?",
    "Show me the top 10 vendors by payment amount",
    "What are the recent payments to Duke University?",
    "Compare spending across different departments"
  ]

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-6 pt-[76px] pb-0">
        <div className="max-w-[800px] mx-auto">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center text-center px-4 mt-12 mb-24">

              <h1 className="text-3xl font-semibold text-gray-900 dark:text-gray-100 mb-3">
                NC Spend Tracker
              </h1>
              <p className="text-base text-gray-600 dark:text-gray-400 mb-8 max-w-md">
                Ask questions about North Carolina state budget and vendor payments. I'll analyze the data and provide visualizations.
              </p>

              <div className="w-full max-w-2xl grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
                {examplePrompts.map((prompt, index) => (
                  <button
                    key={index}
                    onClick={() => handleSendMessage(prompt)}
                    className="group text-left p-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600 hover:shadow-md transition-all duration-200"
                  >
                    <p className="text-sm text-gray-700 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-gray-100">
                      {prompt}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message, index) => (
              <MessageBubble key={index} message={message} />
            ))
          )}

          {isLoading && <LoadingIndicator />}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input area */}
      <InputArea onSendMessage={handleSendMessage} isLoading={isLoading} />
    </div>
  )
}
