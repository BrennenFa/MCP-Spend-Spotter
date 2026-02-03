"""SQL and result validators with warning-based approach."""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def validate_sql_query(sql: str) -> List[str]:
    """
    Validate SQL query and return list of warnings (non-blocking).

    Checks for:
    - Destructive operations (DROP, DELETE, UPDATE, ALTER, etc.)
    - Multiple statements (SQL injection risk)
    - Missing WHERE clause on large tables

    Returns:
        List of warning messages (empty if no issues)
    """
    warnings = []
    sql_upper = sql.upper()

    # Check for destructive keywords
    destructive_keywords = [
        'DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER',
        'CREATE', 'TRUNCATE', 'REPLACE', 'MERGE'
    ]

    for keyword in destructive_keywords:
        if f' {keyword} ' in f' {sql_upper} ' or sql_upper.startswith(keyword + ' '):
            warnings.append(f"[SQL_VALIDATOR] WARNING: Destructive operation '{keyword}' detected in query")

    # Check for multiple statements
    if ';' in sql.rstrip(';'):
        warnings.append("[SQL_VALIDATOR] WARNING: Multiple SQL statements detected (SQL injection risk)")

    # Check if not a SELECT query
    if not sql_upper.strip().startswith('SELECT'):
        warnings.append("[SQL_VALIDATOR] WARNING: Non-SELECT query detected")

    # Warn about missing WHERE clause on full table scans
    if 'WHERE' not in sql_upper and 'LIMIT' not in sql_upper:
        warnings.append("[SQL_VALIDATOR] WARNING: Query has no WHERE or LIMIT clause (full table scan)")

    return warnings
