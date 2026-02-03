"""Convert vendor payment data and budget data CSV files to SQLite database."""

import csv
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# get root dir
script_dir = Path(__file__).parent
project_root = script_dir.parent

vendor_csv = project_root / "data" / "vendor_data.csv"
vendor_csv_2024 = project_root / "data" / "Key value - Payment 1y.csv"
vendor_csv_2025 = project_root / "data" / "Key value - Payment 1ya.csv"
budget_csv = project_root / "data" / "budget_data.csv"
budget_2024_csv = project_root / "data" / "budget2024.csv"


# handle db directory
db_dir = project_root / "db"
db_dir.mkdir(parents=True, exist_ok=True)

vendor_db_file = db_dir / "vendor.db"
budget_db_file = db_dir / "budget.db"

# Create vendor database
print("Creating vendor database...")
vendor_conn = sqlite3.connect(vendor_db_file)
vendor_cursor = vendor_conn.cursor()


vendor_cursor.execute("""
CREATE TABLE IF NOT EXISTS vendor_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fiscal_year_numeric TEXT,
    budget_fund TEXT,
    fiscal_year TEXT,
    payment TEXT,
    vendor_recipient TEXT,
    account_description TEXT,
    major_category TEXT,
    budget_code TEXT,
    report_title TEXT,
    description TEXT,
    agency_description TEXT
)
""")

# Create budget database
print("Creating budget database...")
budget_conn = sqlite3.connect(budget_db_file)
budget_cursor = budget_conn.cursor()

budget_cursor.execute("""
CREATE TABLE IF NOT EXISTS budget (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    committee TEXT,
    agency TEXT,
    budget_code TEXT,
    account_group TEXT,
    budget_fund_code TEXT,
    expenditures TEXT,
    receipts TEXT,
    net_appropriations TEXT,
    budget_type TEXT,
    fund_type TEXT,
    fiscal_year TEXT
)
""")


# remove elements to prevent duplicates
vendor_cursor.execute("DELETE FROM vendor_payments")
vendor_cursor.execute("DELETE FROM sqlite_sequence WHERE name='vendor_payments'")

budget_cursor.execute("DELETE FROM budget")
budget_cursor.execute("DELETE FROM sqlite_sequence WHERE name='budget'")

# Import vendor payment data
print("\nImporting vendor payment data...")
with open(vendor_csv, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)

    # Skip header row
    next(reader)

    # Insert data
    row_count = 0
    for row in reader:
        # The CSV has 11 columns
        if len(row) >= 11:
            vendor_cursor.execute("""
                INSERT INTO vendor_payments (
                    fiscal_year_numeric, budget_fund, fiscal_year, payment,
                    vendor_recipient, account_description, major_category,
                    budget_code, report_title, description, agency_description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row[:11])
            row_count += 1

            if row_count % 1000 == 0:
                print(f"Imported {row_count} vendor payment rows...")

# Import additional vendor payment data (FY 2024)
print("\nImporting FY 2024 vendor payment data...")
with open(vendor_csv_2024, 'r', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    next(reader)  # Skip header
    for row in reader:
        if len(row) >= 11:
            vendor_cursor.execute("""
                INSERT INTO vendor_payments (
                    fiscal_year_numeric, budget_fund, fiscal_year, payment,
                    vendor_recipient, account_description, major_category,
                    budget_code, report_title, description, agency_description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row[:11])
            row_count += 1
            if row_count % 1000 == 0:
                print(f"Imported {row_count} vendor payment rows...")

# Import additional vendor payment data (FY 2025)
print("\nImporting FY 2025 vendor payment data...")
with open(vendor_csv_2025, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader)  # Skip header
    for row in reader:
        if len(row) >= 11:
            vendor_cursor.execute("""
                INSERT INTO vendor_payments (
                    fiscal_year_numeric, budget_fund, fiscal_year, payment,
                    vendor_recipient, account_description, major_category,
                    budget_code, report_title, description, agency_description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row[:11])
            row_count += 1
            if row_count % 1000 == 0:
                print(f"Imported {row_count} vendor payment rows...")

vendor_conn.commit()

# Import budget data
print("\nImporting budget data...")
with open(budget_csv, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)

    # Skip header row
    next(reader)

    # Insert data
    budget_count = 0
    for row in reader:
        # The CSV has 11 columns
        if len(row) >= 11:
            budget_cursor.execute("""
                INSERT INTO budget (
                    committee, agency, budget_code, account_group,
                    budget_fund_code, expenditures, receipts, net_appropriations,
                    budget_type, fund_type, fiscal_year
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row[:11])
            budget_count += 1

            if budget_count % 1000 == 0:
                print(f"Imported {budget_count} budget rows...")

with open(budget_2024_csv, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)

    # Skip header row
    next(reader)

    # Insert data
    budget_count = 0
    for row in reader:
        # The CSV has 11 columns
        if len(row) >= 11:
            budget_cursor.execute("""
                INSERT INTO budget (
                    committee, agency, budget_code, account_group,
                    budget_fund_code, expenditures, receipts, net_appropriations,
                    budget_type, fund_type, fiscal_year
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row[:11])
            budget_count += 1

            if budget_count % 1000 == 0:
                print(f"Imported {budget_count} budget rows...")

budget_conn.commit()

# Print summary
vendor_cursor.execute("SELECT COUNT(*) FROM vendor_payments")
vendor_payment_rows = vendor_cursor.fetchone()[0]

budget_cursor.execute("SELECT COUNT(*) FROM budget")
budget_rows = budget_cursor.fetchone()[0]

print(f"\n✓ Successfully created databases:")
print(f"  - {vendor_db_file} ({vendor_payment_rows} rows)")
print(f"  - {budget_db_file} ({budget_rows} rows)")

# Show sample data
print("\nSample vendor payment records:")
vendor_cursor.execute("SELECT vendor_recipient, payment, fiscal_year, agency_description FROM vendor_payments LIMIT 3")
for row in vendor_cursor.fetchall():
    print(f"  - {row[0]} | {row[1]} | FY{row[2]} | {row[3]}")

print("\nSample budget records:")
budget_cursor.execute("SELECT agency, account_group, expenditures, fiscal_year FROM budget LIMIT 3")
for row in budget_cursor.fetchall():
    print(f"  - {row[0]} | {row[1]} | {row[2]} | FY{row[3]}")

vendor_conn.close()
budget_conn.close()
