#!/bin/bash
set -e

echo "Starting application..."
echo "PORT: ${PORT:-8000}"
echo "Python version: $(python --version)"
echo "Working directory: $(pwd)"

# Check if database files exist
if [ -f "db/vendor.db" ] && [ -f "db/budget.db" ]; then
    echo "✅ Database files found"
else
    echo "⚠️  Warning: Database files not found in db/"
    ls -la db/ || echo "db/ directory not found"
fi

# Check environment variables
if [ -z "$GROQ_KEY" ]; then
    echo "⚠️  WARNING: GROQ_KEY not set"
fi

if [ -z "$BACKEND_API_KEY" ]; then
    echo "⚠️  WARNING: BACKEND_API_KEY not set"
fi

# Start uvicorn
exec python -m uvicorn chat.api:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --timeout-keep-alive 120
