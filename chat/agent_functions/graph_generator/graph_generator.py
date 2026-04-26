#!/usr/bin/env python3
"""Graph generation for SQL query results using matplotlib."""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64
from io import BytesIO
from typing import List, Dict, Optional, Tuple
import re
import math

MAX_BAR_POINTS = 25
MAX_LINE_POINTS = 30


def format_numbers(value: float) -> str:
    """Format a number as currency + handle scale"""
    # billion
    if value >= 1_000_000_000:
        return f"${value/1_000_000_000:.1f}B"
    # million
    elif value >= 1_000_000:
        return f"${value/1_000_000:.1f}M"
    # thousand
    elif value >= 1_000:
        return f"${value/1_000:.0f}K"
    else:
        return f"${value:.0f}"


def detect_graph_type(results: List[Dict], query: str) -> str:
    """
    Auto-detect the best graph type based on data shape and query.
    TODO - make llm-assisted

    Args:
        results: Query results as list of dicts
        query: Original SQL query

    Returns:
        "bar", "line", or "none"
    """
    # issues with results
    if not results or len(results) < 4:
        return "none"


    # ==============
    # LINE
    # ==============

    # SELECT * outputs are usually too wide/noisy for line charts
    query_upper = query.upper()
    if 'SELECT *' in query_upper:
        return "bar"

    # Check for time series data - look for 'fiscal_year' or 'year' in any key
    has_time_col = any('fiscal_year' in str(key).lower() or 'year' in str(key).lower()
                       for key in results[0].keys())

    if has_time_col and len(results) >= 4:
        return "line"


    # ==============
    # BAR
    # ==============

    # Check for top N lists in query (LIMIT + ORDER BY)
    if 'LIMIT' in query_upper and 'ORDER BY' in query_upper:
        return "bar"

    # Default to bar chart for aggregations
    if 'GROUP BY' in query_upper:
        return "bar"

    return "bar"


def truncate_label(label: str, max_length: int = 30) -> str:
    """Truncate label if too long and add ellipsis."""
    if len(label) > max_length:
        return label[:max_length-3] + "..."
    return label


def _parse_numeric(value) -> Optional[float]:
    """Parse numeric values from ints/floats/currency-like strings."""
    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        cleaned = re.sub(r'[\$,]', '', value).strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    return None


def _select_plot_columns(results: List[Dict]) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Choose independent/dependent columns more intelligently than first-two-columns.
    Returns (independent_var, dependent_var, is_time_series).
    """
    if not results:
        return None, None, False

    keys = list(results[0].keys())
    if not keys:
        return None, None, False

    # Find numeric-capable columns by sampling rows
    numeric_candidates = []
    sample_size = min(len(results), 50)
    for key in keys:
        parsed = 0
        for row in results[:sample_size]:
            if _parse_numeric(row.get(key)) is not None:
                parsed += 1
        if parsed >= max(2, int(sample_size * 0.6)):
            numeric_candidates.append(key)

    if not numeric_candidates:
        return None, None, False

    # Prefer common metric/value columns
    metric_priority = [
        "total", "amount", "payment", "expenditures",
        "receipts", "net_appropriations", "count", "sum", "avg"
    ]
    dependent_var = None
    for candidate in numeric_candidates:
        candidate_lower = candidate.lower()
        if any(token in candidate_lower for token in metric_priority):
            dependent_var = candidate
            break
    if dependent_var is None:
        dependent_var = numeric_candidates[0]

    # Prefer time series x-axis when available
    time_columns = [
        key for key in keys
        if key != dependent_var and any(t in key.lower() for t in ["year", "date", "month", "quarter"])
    ]
    if time_columns:
        return time_columns[0], dependent_var, True

    # Otherwise pick first non-ID-ish column
    independent_var = None
    for key in keys:
        key_lower = key.lower()
        if key == dependent_var:
            continue
        if key_lower == "id" or key_lower.endswith("_id"):
            continue
        independent_var = key
        break

    if independent_var is None:
        for key in keys:
            if key != dependent_var:
                independent_var = key
                break

    return independent_var, dependent_var, False


def _aggregate_points_for_display(
    labels: List[str],
    values: List[float],
    graph_type: str
) -> Tuple[List[str], List[float]]:
    """Cap plotted points and aggregate overflow for readability."""
    if graph_type == "bar":
        if len(labels) <= MAX_BAR_POINTS:
            return labels, values

        pairs = list(zip(labels, values))
        pairs.sort(key=lambda p: p[1], reverse=True)
        keep_count = MAX_BAR_POINTS - 1
        kept = pairs[:keep_count]
        remainder = pairs[keep_count:]
        other_total = sum(v for _, v in remainder)

        capped_labels = [label for label, _ in kept] + ["Other"]
        capped_values = [value for _, value in kept] + [other_total]
        return capped_labels, capped_values

    if graph_type == "line":
        if len(labels) <= MAX_LINE_POINTS:
            return labels, values

        bucket_size = int(math.ceil(len(labels) / MAX_LINE_POINTS))
        agg_labels = []
        agg_values = []

        for i in range(0, len(labels), bucket_size):
            chunk_labels = labels[i:i + bucket_size]
            chunk_values = values[i:i + bucket_size]
            if not chunk_labels:
                continue
            if len(chunk_labels) == 1:
                agg_label = chunk_labels[0]
            else:
                agg_label = f"{chunk_labels[0]}..{chunk_labels[-1]}"
            agg_labels.append(agg_label)
            agg_values.append(sum(chunk_values))

        return agg_labels, agg_values

    return labels, values


def _plot_bar_chart(
    ax,
    independent_values: List[str],
    dependent_values: List[float],
    independent_var: str,
    dependent_var: str,
    is_currency: bool
) -> None:
    """
    Internal function to plot a horizontal bar chart.

    Args:
        ax: Matplotlib axes object
        independent_values: List of independent variable values for Y-axis (e.g., agency names, years)
        dependent_values: List of dependent variable values (numeric amounts)
        independent_var: Name of the independent variable column (e.g., "agency", "fiscal_year")
        dependent_var: Name of the dependent variable column (e.g., "total", "amount")
        is_currency: Whether values represent currency
    """
    num_items = len(independent_values)

    # Horizontal bar chart
    y_pos = range(num_items)
    bars = ax.barh(y_pos, dependent_values, color='#3b82f6', edgecolor='#60a5fa', linewidth=1.5)

    # Dynamic label formatting based on number of items
    if num_items > 50:
        max_label_length = 20
        label_fontsize = 6
    elif num_items > 30:
        max_label_length = 25
        label_fontsize = 7
    elif num_items > 20:
        max_label_length = 30
        label_fontsize = 8
    else:
        max_label_length = 40
        label_fontsize = 10

    # Truncate/assign labels
    truncated_labels = [truncate_label(label, max_label_length) for label in independent_values]
    ax.set_yticks(y_pos)
    ax.set_yticklabels(truncated_labels, fontsize=label_fontsize, color='#e5e7eb')

    # Format X-axis
    if is_currency:
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: format_numbers(x)))

    ax.set_xlabel(dependent_var.replace('_', ' ').title(), fontsize=12, color='#e5e7eb', fontweight='bold')
    ax.tick_params(axis='x', colors='#e5e7eb', labelsize=10)

    # Add value labels on bars (skip if too many items to avoid clutter)
    if num_items <= 40:
        value_fontsize = 9 if num_items <= 20 else 7
        for bar, value in zip(bars, dependent_values):
            width = bar.get_width()
            label_text = format_numbers(value) if is_currency else f'{value:,.0f}'
            ax.text(width, bar.get_y() + bar.get_height()/2,
                   f' {label_text}',
                   va='center', ha='left', fontsize=value_fontsize, color='#e5e7eb', fontweight='bold')


def _plot_line_chart(
    ax,
    independent_values: List[str],
    dependent_values: List[float],
    independent_var: str,
    dependent_var: str,
    is_currency: bool
) -> None:
    """
    Internal function to plot a line chart.

    Args:
        ax: Matplotlib axes object
        independent_values: List of independent variable values for X-axis (typically time series like years)
        dependent_values: List of dependent variable values (numeric amounts)
        independent_var: Name of the independent variable column (e.g., "fiscal_year")
        dependent_var: Name of the dependent variable column (e.g., "total", "amount")
        is_currency: Whether values represent currency
    """
    ax.plot(independent_values, dependent_values, marker='o', linewidth=2, markersize=8,
           color='#3b82f6', markerfacecolor='#60a5fa', markeredgecolor='#1e40af')

    # Format Y-axis
    if is_currency:
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: format_numbers(y)))

    ax.set_xlabel(independent_var.replace('_', ' ').title(), fontsize=12, color='#e5e7eb', fontweight='bold')
    ax.set_ylabel(dependent_var.replace('_', ' ').title(), fontsize=12, color='#e5e7eb', fontweight='bold')
    ax.tick_params(axis='both', colors='#e5e7eb', labelsize=10)

    # Rotate x-axis labels if needed
    if len(independent_values) > 10:
        plt.xticks(rotation=45, ha='right')

    # Add grid for better readability
    ax.grid(True, alpha=0.2, color='#9ca3af', linestyle='--')


def generate_graph(
    results: List[Dict],
    query: str = "",
    graph_type: str = "auto",
    title: Optional[str] = None
) -> Optional[str]:
    """
    Generate a graph from SQL query results.

    Args:
        results: Query results as list of dicts
        query: Original SQL query (for context)
        graph_type: "bar", "line", or "auto" (default)
        title: Optional custom title

    Returns:
        Base64-encoded PNG image string, or None if graph shouldn't be generated
    """
    if not results:
        return None

    # Auto-detect graph type if requested
    if graph_type == "auto":
        graph_type = detect_graph_type(results, query)

    if graph_type == "none":
        return None

    independent_var, dependent_var, is_time_series = _select_plot_columns(results)
    if not independent_var or not dependent_var:
        return None

    # Extract as 2D array: each point is [independent_var_value, dependent_var_value]
    points = []
    is_currency = False

    for row in results:
        label = str(row.get(independent_var, ""))
        raw_val = row.get(dependent_var, 0)
        if isinstance(raw_val, str):
            is_currency = is_currency or ('$' in raw_val)
        parsed_val = _parse_numeric(raw_val)
        points.append([label, float(parsed_val if parsed_val is not None else 0.0)])

    # Separate into independent and dependent value arrays for plotting
    independent_values = [point[0] for point in points]
    dependent_values = [point[1] for point in points]

    # If auto-detected as line but x-axis is not time-like, force bar.
    if graph_type == "line" and not is_time_series:
        graph_type = "bar"

    # Cap plotted points and aggregate overflow for readability.
    independent_values, dependent_values = _aggregate_points_for_display(
        independent_values,
        dependent_values,
        graph_type
    )

    # Calculate dynamic figure size based on data points and chart type
    num_items = len(independent_values)

    if graph_type == "bar":
        # Dynamic height for bar charts based on number of items
        # Minimum 6 inches, then 0.25 inches per item (capped at 30 inches)
        bar_height = min(max(6, num_items * 0.25), 30)
        figsize = (12, bar_height)
    else:
        # Line charts use fixed size
        figsize = (12, 6)

    # Create figure
    fig, ax = plt.subplots(figsize=figsize, facecolor='#1f2937')
    ax.set_facecolor('#374151')

    # Generate the appropriate chart type using helper functions
    if graph_type == "bar":
        _plot_bar_chart(ax, independent_values, dependent_values, independent_var, dependent_var, is_currency)
    elif graph_type == "line":
        _plot_line_chart(ax, independent_values, dependent_values, independent_var, dependent_var, is_currency)

    # Set title
    if title:
        plt.title(title, fontsize=14, color='#e5e7eb', fontweight='bold', pad=20)
    else:
        # Generate title from query context
        auto_title = f"{dependent_var.replace('_', ' ').title()} by {independent_var.replace('_', ' ').title()}"
        plt.title(auto_title, fontsize=14, color='#e5e7eb', fontweight='bold', pad=20)

    # Style the spines
    for spine in ax.spines.values():
        spine.set_edgecolor('#9ca3af')
        spine.set_linewidth(1)

    plt.tight_layout()

    # Convert to base64 (binary)
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100, facecolor='#1f2937', edgecolor='none')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
    buffer.close()
    plt.close(fig)

    return image_base64

