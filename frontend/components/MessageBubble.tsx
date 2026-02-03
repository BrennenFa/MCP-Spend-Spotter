import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Message } from '@/types/chat'
import GraphDisplay from './GraphDisplay'
import DataTable from './DataTable'

interface MessageBubbleProps {
  message: Message
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`mb-8 ${isUser ? 'flex justify-end' : 'flex justify-start'}`}>
      <div className={`max-w-[85%] ${isUser ? '' : 'w-full'}`}>
        {/* Role label */}
        {/* <div className="flex items-center gap-2 mb-2 px-1">
          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold ${
            isUser
              ? 'bg-blue-500 text-white'
              : 'bg-gradient-to-br from-purple-500 to-blue-600 text-white'
          }`}>
            {isUser ? 'U' : 'AI'}
          </div>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {isUser ? 'You' : 'NC Spend Tracker'}
          </span>
          <span className="text-xs text-gray-400 dark:text-gray-600">
            {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div> */}

        {/* Message content */}
        <div
          className={`rounded-2xl ${
            isUser
              ? 'bg-blue-500 text-white px-5 py-3'
              : 'bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-700/50'
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap leading-relaxed">
              {message.content}
            </p>
          ) : (
            <div>
              {/* Main answer */}
              <div className="px-5 py-4 prose prose-base dark:prose-invert max-w-none prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-p:leading-relaxed prose-p:text-gray-800 dark:prose-p:text-gray-200">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    p: ({children}) => <p className="mb-3 leading-relaxed">{children}</p>,
                    ul: ({children}) => <ul className="mb-3 ml-5 list-disc">{children}</ul>,
                    ol: ({children}) => <ol className="mb-3 ml-5 list-decimal">{children}</ol>,
                    li: ({children}) => <li className="mb-1">{children}</li>,
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              </div>

              {/* Data/Graph section - with visual separation */}
              {(message.data || message.graph || message.sqlQuery) && (
                <div className="border-t border-gray-200 dark:border-gray-700 pt-4 pb-2">
                  {/* Graph visualization */}
                  {message.graph && (
                    <div className="px-5 mb-4">
                      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                        </svg>
                        Visualization
                      </h4>
                      <GraphDisplay
                        base64Image={message.graph}
                        alt="SQL query results visualization"
                      />
                    </div>
                  )}

                  {/* Data table */}
                  {message.data && (
                    <div className="px-5 mb-4">
                      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                        Query Results
                      </h4>
                      <DataTable data={message.data} maxRows={20} />
                    </div>
                  )}

                  {/* SQL Query */}
                  {message.sqlQuery && (
                    <div className="px-5 mb-3">
                      <details className="group">
                        <summary className="cursor-pointer text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 flex items-center gap-2 select-none">
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 group-open:rotate-90 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                          </svg>
                          View SQL Query
                        </summary>
                        <pre className="mt-3 p-4 bg-gray-900 dark:bg-black text-green-400 rounded-lg overflow-x-auto text-xs font-mono border border-gray-700">
                          <code>{message.sqlQuery}</code>
                        </pre>
                      </details>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
