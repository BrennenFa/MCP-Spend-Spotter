# NC Budget & Vendor Database Explorer

An AI-powered interface to explore North Carolina state budget and vendor payment data with automatic graph visualization.

## Features

- **AI Chat Interface**: Ask natural language questions about NC budget and vendor data
- **Automatic Graph Generation**: SQL query results automatically visualized as charts
- **Multi-Interface**: Use via web frontend, CLI, or API
- **Session Management**: Conversation history maintained per session
- **Dark Mode Support**: Full dark mode theme

## Quick Start

### 1. Install Backend Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Backend (.env file in root)
```
GROQ_KEY=your_groq_api_key
MODEL_NAME=llama-3.1-8b-instant
FRONTEND_URL=http://localhost:3000
BACKEND_API_KEY=your_secret_key
```

### 3. Start Backend
```bash
cd chat
python api.py
```

### 4. Install Frontend Dependencies
```bash
cd frontend
npm install
```

### 5. Configure Frontend (.env.local in frontend/)
```
BACKEND_URL=http://localhost:8000
BACKEND_API_KEY=your_secret_key
```

### 6. Start Frontend
```bash
cd frontend
npm run dev
```

### 7. Open Browser
Navigate to http://localhost:3000

## Example Queries

- "Which vendors got paid the most in 2026?"
- "Show me the top 10 agencies by spending"
- "What's the total net budget for FY 2025?"
- "Show me spending by fiscal year" (generates line chart)

## CLI Usage

```bash
cd chat
python chat_cli.py
```

## API Documentation

Visit http://localhost:8000/docs when backend is running.

## Technologies

- **Backend**: FastAPI, Groq (Llama 3.1), SQLite, Matplotlib
- **Frontend**: Next.js 15, TypeScript, Tailwind CSS, React Markdown
