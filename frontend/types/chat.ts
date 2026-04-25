export interface Citation {
  id: number
  kind: 'sql' | 'rag'
  title: string
  detail: string
  confidence?: number
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  data?: any[]  // Query results data
  graph?: string  // Base64-encoded PNG image
  visualizationStatus?: 'created' | 'not_created'
  citations?: Citation[]
  sqlQuery?: string  // SQL query that was executed
  timestamp: Date
}

export interface ChatResponse {
  answer: string
  data?: any[]  // Query results data
  graph?: string
  visualization_status?: 'created' | 'not_created'
  citations?: Citation[]
  sql_query?: string
  tokens_used: number
  prompt_tokens: number
  completion_tokens: number
  session_id: string
}

export interface ChatRequest {
  message: string
  session_id?: string
}
