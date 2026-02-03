#!/usr/bin/env python3
"""Tool definitions and schemas."""

# Main tool definitions in MCP format
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_vendor_payments",
            "description": "Execute SQL query on vendor payment database. Use this for questions about actual spending, payments to vendors, what money was paid for, TOP LISTS, RANKINGS, or AGGREGATES. Table: vendor_payments with columns: fiscal_year (TEXT), payment (TEXT - currency format), vendor_recipient (TEXT), account_description (TEXT), major_category (TEXT), agency_description (TEXT), etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query to execute on vendor_payments table. CRITICAL: payment column is TEXT like '$1,234.56'. To do ANY math (SUM, AVG, etc.), you MUST convert it: CAST(REPLACE(REPLACE(payment, '$', ''), ',', '') AS REAL). Example: SELECT vendor_recipient, SUM(CAST(REPLACE(REPLACE(payment, '$', ''), ',', '') AS REAL)) as total FROM vendor_payments WHERE fiscal_year = '2026' GROUP BY vendor_recipient ORDER BY total DESC LIMIT 10"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_budget",
            "description": "Execute SQL query on budget database. Use this for questions about budget allocations, planned budgets, committees, appropriations. Table: budget with columns: committee (TEXT), agency (TEXT), account_group (TEXT), expenditures (TEXT - currency format), receipts (TEXT - currency format), net_appropriations (TEXT - currency format), budget_type (TEXT), fund_type (TEXT), fiscal_year (TEXT).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query to execute on budget table. CRITICAL: expenditures, receipts, net_appropriations are TEXT like '$1,234.56'. To do ANY math (SUM, AVG, etc.), you MUST convert: CAST(REPLACE(REPLACE(expenditures, '$', ''), ',', '') AS REAL). Example: SELECT committee, SUM(CAST(REPLACE(REPLACE(expenditures, '$', ''), ',', '') AS REAL)) as total FROM budget WHERE fiscal_year = '2025' GROUP BY committee ORDER BY total DESC LIMIT 10"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_graph",
            "description": "Generate a visualization (bar chart or line chart) from query results. Use this AFTER executing a query when results would benefit from visualization - especially for aggregates, rankings, time series, or top-N lists with 4+ rows. Returns a base64-encoded PNG image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "description": "Query results as array of objects (the data returned from query_vendor_payments or query_budget)"
                    },
                    "query": {
                        "type": "string",
                        "description": "The SQL query that generated these results (for context in choosing graph type)"
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional custom title for the graph. If not provided, will auto-generate from data."
                    }
                },
                "required": ["results", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_sql",
            "description": "Query budget and vendor databases using natural language. Automatically converts questions to SQL and executes them. Use this for spending amounts, payments, budgets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language question (e.g., 'How much did NC spend on transportation in 2025?')"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_budget_context",
            "description": "Search NC Governor's Budget documents for explanations of concepts, terminology, and policies. Use this for 'what is', 'explain', or 'tell me about' questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Question about budget concepts, policies, or terminology (e.g., 'What is a net appropriation?' or 'Explain the budget process')"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional session ID for tracking conversation context"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# Agent-specific tool subsets
SQL_TOOLS = [tool for tool in TOOLS if tool["function"]["name"] in [
    "query_sql",
    "query_vendor_payments",
    "query_budget"
]]

GRAPH_TOOLS = [tool for tool in TOOLS if tool["function"]["name"] in [
    "create_graph"
]]

RAG_TOOLS = [
    {
        "name": "query_budget_context",
        "description": "Search NC Governor's Budget documents for explanations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "session_id": {"type": "string"}
            },
            "required": ["query"]
        }
    }
]
