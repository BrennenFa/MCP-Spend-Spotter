"""SQL and result validators with warning-based approach."""

import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


def sql_validator(sql: str) -> Tuple[bool, List[str]]:
    """
    Check SQL for dangerous operations and BLOCK if found.
    
    This is a BLOCKING check - if dangerous operations are detected,
    the query should NOT be executed.
    
    Args:
        sql: SQL query to check
        
    Returns:
        (is_safe, warnings) - is_safe=False means query should be BLOCKED
    """
    warnings = []
    sql_upper = sql.upper().strip()
    
    # Check for destructive keywords
    destructive_keywords = [
        'DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER',
        'CREATE', 'TRUNCATE', 'REPLACE', 'MERGE'
    ]
    
    for keyword in destructive_keywords:
        if f' {keyword} ' in f' {sql_upper} ' or sql_upper.startswith(keyword + ' '):
            warnings.append(f"[SQL_SAFETY] BLOCKED: Destructive operation '{keyword}' detected in query")
            return (False, warnings)
    
    # Check for multiple statements - sql injection risk
    if ';' in sql.rstrip(';'):
        warnings.append("[SQL_SAFETY] BLOCKED: Multiple SQL statements detected (SQL injection risk)")
        return (False, warnings)
    
    return (True, warnings)


def validate_query_results(results: List[Dict], sql: str, query_error: str = "") -> List[str]:
    """
    Validate query results after data has been collected - deterministically.

    Checks for:
    - Query execution errors
    - Empty result sets (when SQL was executed)
    - Negative monetary values (payments, expenditures, etc.)
    - Invalid fiscal years
    - Suspiciously large result sets

    Args:
        results: Query results as list of dicts
        sql: SQL query that generated results
        query_error: Error message from query execution, if any

    Returns:
        List of warning messages (empty if no issues)
    """
    if query_error:
        return [f"[QUERY_FAILED] {query_error}"]

    if sql and len(results) == 0:
        return ["[EMPTY_RESULTS] Query returned 0 rows — SQL may need correction"]

    warnings = []

    # Check first few rows for common issues
    sample_size = min(10, len(results))
    sample = results[:sample_size]

    for i, row in enumerate(sample):
        # Check for negative monetary values
        money_fields = ['payment', 'expenditures', 'receipts', 'net_appropriations', 'total', 'amount']
        for field in money_fields:
            if field in row:
                value = row[field]
                # Parse numeric value
                if isinstance(value, str):
                    try:
                        value = float(value.replace('$', '').replace(',', ''))
                    except:
                        continue

                if isinstance(value, (int, float)) and value < 0:
                    warnings.append(f"[RESULT_VALIDATOR] WARNING: Negative monetary value in row {i+1}: {field}={value}")

        # Check for fiscal years outside what's actually in the database (2024-2026)
        if 'fiscal_year' in row:
            year = row['fiscal_year']
            try:
                year_int = int(year) if isinstance(year, str) else year
                if year_int not in (2024, 2025, 2026):
                    warnings.append(f"[RESULT_VALIDATOR] WARNING: Unexpected fiscal year in row {i+1}: {year}")
            except:
                warnings.append(f"[RESULT_VALIDATOR] WARNING: Invalid fiscal year format in row {i+1}: {year}")

    # Check for suspiciously large result sets
    if len(results) > 10000:
        warnings.append(f"[RESULT_VALIDATOR] WARNING: Large result set returned ({len(results)} rows) - may impact performance")

    return warnings
