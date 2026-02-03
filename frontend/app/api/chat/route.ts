import { NextRequest, NextResponse } from 'next/server'

export async function POST(req: NextRequest) {
  try {
    const { message, session_id } = await req.json()

    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
    const apiKey = process.env.BACKEND_API_KEY

    if (!apiKey) {
      return NextResponse.json(
        { error: 'Backend API key not configured' },
        { status: 500 }
      )
    }

    const response = await fetch(`${backendUrl}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey
      },
      body: JSON.stringify({
        message,
        session_id: session_id || 'default'
      })
    })

    if (!response.ok) {
      const errorText = await response.text()
      return NextResponse.json(
        { error: `Backend error: ${errorText}` },
        { status: response.status }
      )
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('API route error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    )
  }
}
