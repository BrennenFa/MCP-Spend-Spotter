"""Tests for graph selection heuristics."""

from chat.agent_functions.graph_generator.graph_generator import (
    _select_plot_columns,
    detect_graph_type,
    generate_graph,
    validate_chart_spec,
)


class TestGraphSelection:
    """Test chart-type and axis-selection logic."""

    def test_prefers_category_over_year_for_rankings(self):
        results = [
            {"fiscal_year": 2025, "agency": "Transportation", "total_amount": 9000000},
            {"fiscal_year": 2025, "agency": "Education", "total_amount": 8000000},
            {"fiscal_year": 2025, "agency": "Health", "total_amount": 7000000},
            {"fiscal_year": 2025, "agency": "Justice", "total_amount": 6000000},
        ]

        independent_var, dependent_var, is_time_series = _select_plot_columns(
            results,
            "show top agencies by total spending in 2025",
        )

        assert independent_var == "agency"
        assert dependent_var == "total_amount"
        assert is_time_series is False
        assert detect_graph_type(results, "show top agencies by total spending in 2025") == "bar"

    def test_uses_year_for_actual_time_series(self):
        results = [
            {"fiscal_year": 2022, "total_amount": 5000000},
            {"fiscal_year": 2023, "total_amount": 5500000},
            {"fiscal_year": 2024, "total_amount": 6100000},
            {"fiscal_year": 2025, "total_amount": 6800000},
        ]

        independent_var, dependent_var, is_time_series = _select_plot_columns(
            results,
            "show spending trend by year",
        )

        assert independent_var == "fiscal_year"
        assert dependent_var == "total_amount"
        assert is_time_series is True
        assert detect_graph_type(results, "show spending trend by year") == "line"

    def test_does_not_treat_unsorted_year_values_as_time_series(self):
        results = [
            {"fiscal_year": 2024, "vendor": "A", "payment_amount": 1000},
            {"fiscal_year": 2022, "vendor": "B", "payment_amount": 2000},
            {"fiscal_year": 2025, "vendor": "C", "payment_amount": 3000},
            {"fiscal_year": 2023, "vendor": "D", "payment_amount": 4000},
        ]

        independent_var, dependent_var, is_time_series = _select_plot_columns(
            results,
            "show top vendors by payment amount",
        )

        assert independent_var == "vendor"
        assert dependent_var == "payment_amount"
        assert is_time_series is False

    def test_validates_explicit_chart_spec(self):
        results = [
            {"agency": "Transportation", "total_amount": 9000000},
            {"agency": "Education", "total_amount": 8000000},
            {"agency": "Health", "total_amount": 7000000},
        ]

        chart_spec = {
            "chart_type": "bar",
            "x_field": "agency",
            "y_field": "total_amount",
            "analysis_goal": "compare agencies",
            "title": "Top Agencies",
        }

        assert validate_chart_spec(results, chart_spec) == chart_spec

    def test_rejects_invalid_chart_spec_without_fallback_graph(self):
        results = [
            {"agency": "Transportation", "total_amount": 9000000},
            {"agency": "Education", "total_amount": 8000000},
            {"agency": "Health", "total_amount": 7000000},
        ]

        chart_spec = {
            "chart_type": "line",
            "x_field": "agency",
            "y_field": "total_amount",
            "analysis_goal": "show trend",
        }

        assert validate_chart_spec(results, chart_spec) is None
        assert generate_graph(results, query="", chart_spec=chart_spec) is None
