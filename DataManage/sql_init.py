"""Convert vendor payment and budget CSV files into normalized SQLite databases."""

from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Iterable, List

from dotenv import load_dotenv

load_dotenv()

script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from preprocessing import EntityTypeClassifier, normalize_agency

vendor_csv_files = [
    project_root / "data" / "vendor_data.csv",
    project_root / "data" / "Key value - Payment 1y.csv",
    project_root / "data" / "Key value - Payment 1ya.csv",
]
budget_csv_files = [
    project_root / "data" / "budget_data.csv",
    project_root / "data" / "budget2024.csv",
]

db_dir = project_root / "db"
db_dir.mkdir(parents=True, exist_ok=True)

vendor_db_file = db_dir / "vendor.db"
budget_db_file = db_dir / "budget.db"


def _parse_currency(value: str) -> float:
    """Convert currency text into a numeric value."""
    cleaned = (value or "").replace("$", "").replace(",", "").strip()
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _derive_spending_type(major_category: str, account_description: str, entity_type: str) -> str:
    """Create coarse spending-type buckets for analysis views."""
    major = (major_category or "").upper()
    account = (account_description or "").upper()

    if entity_type in {"benefit_recipient", "claimant"}:
        return "benefits"
    if entity_type == "grant_recipient":
        return "grants"
    if "AID" in major or "PUBLIC ASSISTANCE" in major:
        return "grants"
    if "SALARY" in account or "WAGE" in account or "PAYROLL" in account:
        return "payroll_or_personal_services"
    if "TRANSFER" in account or "REIMBURSEMENT" in account:
        return "internal_transfers"
    if "PURCHASED SERVICES" in major or "SUPPLIES" in major or "EQUIPMENT" in account:
        return "contracts"
    return "other"


def _read_csv_rows(path: Path, encoding: str = "utf-8") -> Iterable[List[str]]:
    """Yield CSV rows, skipping the header."""
    with open(path, "r", encoding=encoding) as handle:
        reader = csv.reader(handle)
        next(reader)
        for row in reader:
            yield row


def _collect_entity_contexts() -> Dict[str, Dict[str, List[str]]]:
    """Collect distinct payee contexts for LLM classification."""
    contexts: Dict[str, Dict[str, List[str]]] = {}
    file_encodings = {
        vendor_csv_files[0]: "utf-8",
        vendor_csv_files[1]: "utf-8-sig",
        vendor_csv_files[2]: "utf-8",
    }

    for file_path in vendor_csv_files:
        for row in _read_csv_rows(file_path, encoding=file_encodings[file_path]):
            if len(row) < 11:
                continue
            payee = row[4].strip()
            if not payee:
                continue
            context = contexts.setdefault(payee, {
                "major_categories": [],
                "account_descriptions": [],
                "agencies": [],
            })
            for key, value in (
                ("major_categories", row[6].strip()),
                ("account_descriptions", row[5].strip()),
                ("agencies", row[10].strip()),
            ):
                if value and value not in context[key]:
                    context[key].append(value)
    return contexts


def _create_vendor_schema(cursor: sqlite3.Cursor) -> None:
    """Create normalized vendor tables and views."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS vendor_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_numeric TEXT,
            budget_fund TEXT,
            fiscal_year TEXT,
            payment TEXT,
            payment_amount REAL,
            raw_vendor_recipient TEXT,
            vendor_recipient TEXT,
            canonical_entity_name TEXT,
            entity_type TEXT,
            entity_type_confidence REAL,
            entity_type_source TEXT,
            account_description TEXT,
            major_category TEXT,
            budget_code TEXT,
            report_title TEXT,
            description TEXT,
            raw_agency_description TEXT,
            agency_description TEXT,
            canonical_agency TEXT,
            parent_agency TEXT,
            sub_agency TEXT,
            spending_type TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_classification_map (
            raw_vendor_recipient TEXT PRIMARY KEY,
            canonical_entity_name TEXT,
            entity_type TEXT,
            entity_type_confidence REAL,
            entity_type_source TEXT
        )
        """
    )
    cursor.execute("DELETE FROM vendor_payments")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='vendor_payments'")
    cursor.execute("DELETE FROM entity_classification_map")
    cursor.execute("DROP VIEW IF EXISTS vendor_payments_normalized")
    cursor.execute("DROP VIEW IF EXISTS vendor_only_payments")
    cursor.execute("DROP VIEW IF EXISTS agency_rollup_payments")


def _create_budget_schema(cursor: sqlite3.Cursor) -> None:
    """Create normalized budget schema."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS budget (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            committee TEXT,
            agency TEXT,
            budget_code TEXT,
            account_group TEXT,
            budget_fund_code TEXT,
            expenditures TEXT,
            expenditures_amount REAL,
            receipts TEXT,
            receipts_amount REAL,
            net_appropriations TEXT,
            net_appropriations_amount REAL,
            budget_type TEXT,
            fund_type TEXT,
            fiscal_year TEXT
        )
        """
    )
    cursor.execute("DELETE FROM budget")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='budget'")


def _insert_vendor_rows(cursor: sqlite3.Cursor, classifications: Dict[str, Dict[str, object]]) -> int:
    """Insert normalized vendor rows."""
    row_count = 0
    file_encodings = {
        vendor_csv_files[0]: "utf-8",
        vendor_csv_files[1]: "utf-8-sig",
        vendor_csv_files[2]: "utf-8",
    }

    for raw_name, classification in classifications.items():
        cursor.execute(
            """
            INSERT INTO entity_classification_map (
                raw_vendor_recipient, canonical_entity_name, entity_type,
                entity_type_confidence, entity_type_source
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                raw_name,
                classification.get("canonical_entity_name", raw_name),
                classification.get("entity_type", "unknown"),
                classification.get("entity_type_confidence", 0.0),
                classification.get("entity_type_source", "llm"),
            ),
        )

    for file_path in vendor_csv_files:
        for row in _read_csv_rows(file_path, encoding=file_encodings[file_path]):
            if len(row) < 11:
                continue

            raw_vendor_recipient = row[4].strip()
            classification = classifications.get(raw_vendor_recipient, {
                "canonical_entity_name": raw_vendor_recipient,
                "entity_type": "unknown",
                "entity_type_confidence": 0.0,
                "entity_type_source": "llm_missing",
            })
            agency_fields = normalize_agency(row[10].strip())
            spending_type = _derive_spending_type(
                major_category=row[6].strip(),
                account_description=row[5].strip(),
                entity_type=str(classification.get("entity_type", "unknown")),
            )

            cursor.execute(
                """
                INSERT INTO vendor_payments (
                    fiscal_year_numeric, budget_fund, fiscal_year, payment, payment_amount,
                    raw_vendor_recipient, vendor_recipient, canonical_entity_name,
                    entity_type, entity_type_confidence, entity_type_source,
                    account_description, major_category, budget_code, report_title,
                    description, raw_agency_description, agency_description,
                    canonical_agency, parent_agency, sub_agency, spending_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row[0].strip(),
                    row[1].strip(),
                    row[2].strip(),
                    row[3].strip(),
                    _parse_currency(row[3]),
                    raw_vendor_recipient,
                    raw_vendor_recipient,
                    classification.get("canonical_entity_name", raw_vendor_recipient),
                    classification.get("entity_type", "unknown"),
                    classification.get("entity_type_confidence", 0.0),
                    classification.get("entity_type_source", "llm"),
                    row[5].strip(),
                    row[6].strip(),
                    row[7].strip(),
                    row[8].strip(),
                    row[9].strip(),
                    row[10].strip(),
                    row[10].strip(),
                    agency_fields["canonical_agency"],
                    agency_fields["parent_agency"],
                    agency_fields["sub_agency"],
                    spending_type,
                ),
            )
            row_count += 1
            if row_count % 10000 == 0:
                print(f"Imported {row_count} vendor payment rows...")
    return row_count


def _insert_budget_rows(cursor: sqlite3.Cursor) -> int:
    """Insert budget rows with numeric convenience columns."""
    budget_count = 0
    for file_path in budget_csv_files:
        for row in _read_csv_rows(file_path):
            if len(row) < 11:
                continue
            cursor.execute(
                """
                INSERT INTO budget (
                    committee, agency, budget_code, account_group, budget_fund_code,
                    expenditures, expenditures_amount, receipts, receipts_amount,
                    net_appropriations, net_appropriations_amount, budget_type,
                    fund_type, fiscal_year
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row[0].strip(),
                    row[1].strip(),
                    row[2].strip(),
                    row[3].strip(),
                    row[4].strip(),
                    row[5].strip(),
                    _parse_currency(row[5]),
                    row[6].strip(),
                    _parse_currency(row[6]),
                    row[7].strip(),
                    _parse_currency(row[7]),
                    row[8].strip(),
                    row[9].strip(),
                    row[10].strip(),
                ),
            )
            budget_count += 1
            if budget_count % 10000 == 0:
                print(f"Imported {budget_count} budget rows...")
    return budget_count


def _create_vendor_views(cursor: sqlite3.Cursor) -> None:
    """Create curated analysis views."""
    cursor.execute(
        """
        CREATE VIEW vendor_payments_normalized AS
        SELECT
            fiscal_year,
            payment_amount,
            raw_vendor_recipient,
            canonical_entity_name,
            entity_type,
            entity_type_confidence,
            entity_type_source,
            account_description,
            major_category,
            budget_fund,
            budget_code,
            report_title,
            description,
            raw_agency_description,
            canonical_agency,
            parent_agency,
            sub_agency,
            spending_type
        FROM vendor_payments
        """
    )
    cursor.execute(
        """
        CREATE VIEW vendor_only_payments AS
        SELECT *
        FROM vendor_payments_normalized
        WHERE entity_type = 'vendor'
        """
    )
    cursor.execute(
        """
        CREATE VIEW agency_rollup_payments AS
        SELECT
            fiscal_year,
            parent_agency,
            canonical_agency,
            sub_agency,
            entity_type,
            spending_type,
            major_category,
            payment_amount,
            canonical_entity_name,
            raw_vendor_recipient,
            account_description
        FROM vendor_payments
        """
    )


def _create_vendor_indexes(cursor: sqlite3.Cursor) -> None:
    """Create useful vendor indexes for normalized analysis."""
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vendor_fiscal_year ON vendor_payments(fiscal_year)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vendor_entity_type ON vendor_payments(entity_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vendor_canonical_entity ON vendor_payments(canonical_entity_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vendor_parent_agency ON vendor_payments(parent_agency)")


def _create_budget_indexes(cursor: sqlite3.Cursor) -> None:
    """Create useful budget indexes."""
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_budget_fiscal_year ON budget(fiscal_year)")


def main() -> None:
    """Rebuild both SQLite databases with normalization."""
    print("Collecting LLM classification contexts...")
    entity_contexts = _collect_entity_contexts()

    print("Classifying payees with LLM...")
    entity_classifier = EntityTypeClassifier()
    classifications = entity_classifier.classify_entities(entity_contexts)

    print("Creating vendor database...")
    vendor_conn = sqlite3.connect(vendor_db_file)
    vendor_cursor = vendor_conn.cursor()
    _create_vendor_schema(vendor_cursor)
    vendor_rows = _insert_vendor_rows(vendor_cursor, classifications)
    _create_vendor_views(vendor_cursor)
    _create_vendor_indexes(vendor_cursor)
    vendor_conn.commit()

    print("Creating budget database...")
    budget_conn = sqlite3.connect(budget_db_file)
    budget_cursor = budget_conn.cursor()
    _create_budget_schema(budget_cursor)
    budget_rows = _insert_budget_rows(budget_cursor)
    _create_budget_indexes(budget_cursor)
    budget_conn.commit()

    print(f"\n✓ Successfully created databases:")
    print(f"  - {vendor_db_file} ({vendor_rows} rows)")
    print(f"  - {budget_db_file} ({budget_rows} rows)")

    print("\nSample vendor payment records:")
    vendor_cursor.execute(
        """
        SELECT canonical_entity_name, entity_type, payment_amount, fiscal_year, parent_agency
        FROM vendor_payments
        LIMIT 5
        """
    )
    for row in vendor_cursor.fetchall():
        print(f"  - {row[0]} | {row[1]} | {row[2]} | FY{row[3]} | {row[4]}")

    vendor_conn.close()
    budget_conn.close()


if __name__ == "__main__":
    main()
