import sqlite3
import json
import os
import re

keywords = {
    "agencies": [],
    "committees": [],
    "account_groups": [],
    "expense_categories": []
}


def add_keywords_from_rows(target_list, rows):
    """seperate keywords based on characters - e.g. / , & -"""
    for row in rows:
        if row[0]:
            val = str(row[0]).strip().lower()
            parts = [p.strip() for p in re.split(r'[&,"/\-]', val)]
            for p in parts:
                if p:
                    norm = ' '.join(p.split())
                    target_list.append(norm)

# budget data
if os.path.exists("../db/budget.db"):
    conn = sqlite3.connect("../db/budget.db")
    curr = conn.cursor()
    
    # Agencies
    curr.execute("SELECT DISTINCT agency FROM budget")
    add_keywords_from_rows(keywords["agencies"], curr.fetchall())

    # commitees
    curr.execute("SELECT DISTINCT committee FROM budget")
    add_keywords_from_rows(keywords["committees"], curr.fetchall())

    # account group
    curr.execute("SELECT DISTINCT account_group FROM budget")
    add_keywords_from_rows(keywords["account_groups"], curr.fetchall())
    conn.close()

# vendor db
if os.path.exists("../db/vendor.db"):
    conn = sqlite3.connect("../db/vendor.db")
    curr = conn.cursor()
    
    # agencies
    curr.execute("SELECT DISTINCT agency_description FROM vendor_payments")
    add_keywords_from_rows(keywords["agencies"], curr.fetchall())
    
    # accounts
    curr.execute("SELECT DISTINCT account_description FROM vendor_payments")
    add_keywords_from_rows(keywords["expense_categories"], curr.fetchall())
    conn.close()

# Deduplicate and sort
for key in keywords:
    keywords[key] = sorted(list(set(keywords[key])))

with open("keywords.json", "w") as f:
    json.dump(keywords, f, indent=4)

