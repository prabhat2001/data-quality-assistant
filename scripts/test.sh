#!/usr/bin/env bash
# Fast check of the running Django API. Start the app first: scripts/dev.sh
set -euo pipefail
API="${API:-http://127.0.0.1:8000}"

python3 - "$API" << 'PY'
import json
import sys
import urllib.error
import urllib.request

API = sys.argv[1]
failed = 0


def check(name, ok, detail=""):
    global failed
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failed += 1


def call(method, path, body=None, timeout=60):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(API + path, data=data, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload
    except urllib.error.URLError as exc:
        return 0, {"detail": str(exc.reason)}


def samples(run):
    found = []
    for result in run.get("results") or []:
        for value in result.get("sample_failures") or []:
            found.append(value)
    return found


def ensure_report(table):
    status, rules = call("GET", f"/api/rules?schema_name=public&table_name={table}")
    if status == 200 and not rules:
        call("POST", f"/api/tables/public/{table}/suggestions")
    status, run = call("GET", f"/api/runs/latest?schema_name=public&table_name={table}")
    if status != 200:
        status, run = call("POST", "/api/runs", {"schema_name": "public", "table_name": table})
    return status, run


status, health = call("GET", "/api/health")
check("API is up", status == 200 and health.get("database") == "ok", health.get("message", "") if isinstance(health, dict) else "")

status, tables = call("GET", "/api/tables")
names = {row["table_name"] for row in tables} if isinstance(tables, list) else set()
check("demo tables exist", names >= {"customers", "orders", "products"}, ", ".join(sorted(names)))

status, detail = call("GET", "/api/tables/public/customers")
columns = {column["name"] for column in detail.get("columns", [])} if isinstance(detail, dict) else set()
check("customer schema and sample rows", "email" in columns and bool(detail.get("sample_rows")))

status, customers = ensure_report("customers")
customer_samples = samples(customers) if isinstance(customers, dict) else []
check("customers report is saved", status == 200 and customers.get("status") == "completed")
check("customers report shows the bad email", "nope" in customer_samples)
check("customers report shows the duplicate email", "ada@example.com" in customer_samples)
check("customers report shows impossible ages", -3 in customer_samples and 240 in customer_samples)

status, orders = ensure_report("orders")
order_samples = samples(orders) if isinstance(orders, dict) else []
check("orders report shows the unknown customer", 9999 in order_samples)
check("orders report shows the negative amount", -20.0 in order_samples or -20 in order_samples)

status, products = ensure_report("products")
product_samples = samples(products) if isinstance(products, dict) else []
check("products report shows the duplicate SKU", "SKU-1" in product_samples)
check("products report shows the negative price", -9.99 in product_samples)

status, created = call(
    "POST",
    "/api/rules/natural-language",
    {"schema_name": "public", "table_name": "customers", "text": "country is required"},
)
rule_id = None
if status == 200 and created.get("rules"):
    rule = created["rules"][0]
    rule_id = rule["id"]
    check(
        "plain language becomes a check",
        rule["expectation_type"] == "expect_column_values_to_not_be_null" and rule["kwargs"].get("column") == "country",
    )
elif status == 400 and "already" in str(created.get("detail", "")).lower():
    check("plain language becomes a check", True, "already saved")
else:
    check("plain language becomes a check", False, str(created))

status, rejected = call(
    "POST",
    "/api/rules/natural-language",
    {"schema_name": "public", "table_name": "customers", "text": "make the data better"},
)
check("vague sentence is rejected", status == 400)

status, rules = call("GET", "/api/rules?schema_name=public&table_name=customers")
target = next((rule for rule in rules if rule["kwargs"].get("column") == "email"), None) if isinstance(rules, list) else None
if target:
    status, bad = call("PATCH", f"/api/rules/{target['id']}", {"kwargs": {"column": "not_a_column"}})
    check("unknown column is rejected", status == 400)
else:
    check("unknown column is rejected", False, "no email check to edit")

status, live = call("POST", "/api/runs", {"schema_name": "public", "table_name": "customers"})
live_samples = samples(live) if isinstance(live, dict) else []
check(
    "live re-run still catches the bad email",
    status == 200 and live.get("status") == "completed" and "nope" in live_samples,
)

if rule_id:
    status, _ = call("DELETE", f"/api/rules/{rule_id}")
    check("test check removed", status == 204)

print()
print("FAIL" if failed else "PASS", f"{failed} problem(s)." if failed else "All checks passed.")
sys.exit(1 if failed else 0)
PY
