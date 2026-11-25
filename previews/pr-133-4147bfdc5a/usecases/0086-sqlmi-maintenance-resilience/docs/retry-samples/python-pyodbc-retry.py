"""Python (pyodbc + ODBC Driver 18) - exponential backoff retries for Azure SQL Managed Instance.

pip install pyodbc
"""
import random
import re
import time

import pyodbc

# Transient errors during a reconfiguration (maintenance or failover).
TRANSIENT = {233, 997, 1204, 1205, 1222, 4060, 4221, 10053, 10054, 10060, 10928, 10929,
             40143, 40197, 40501, 40540, 40613, 49918, 49919, 49920}
TRANSIENT_SQLSTATE = {"08S01", "08001", "08004", "HYT00", "HYT01", "40001"}

MAX_TRIES = 5
BASE_DELAY = 1.0
MAX_DELAY = 20.0

CONNECTION_STRING = (
    "Driver={ODBC Driver 18 for SQL Server};"
    "Server=tcp:<mi>.<dns-zone>.database.windows.net,1433;Database=orders;"
    "Encrypt=yes;Authentication=ActiveDirectoryMsi;"
    "ConnectRetryCount=3;ConnectRetryInterval=10;Connection Timeout=30;"
)


def is_transient(exc: pyodbc.Error) -> bool:
    sqlstate = exc.args[0] if exc.args else ""
    if sqlstate in TRANSIENT_SQLSTATE:
        return True
    message = " ".join(str(a) for a in exc.args)
    return any(int(n) in TRANSIENT for n in re.findall(r"\((-?\d+)\)", message))


def run_with_retry(work):
    """Runs the WHOLE unit of work (connection + query/transaction) with retries."""
    for attempt in range(1, MAX_TRIES + 1):
        try:
            with pyodbc.connect(CONNECTION_STRING, timeout=30) as connection:
                return work(connection)
        except pyodbc.Error as exc:
            if not is_transient(exc) or attempt == MAX_TRIES:
                raise
            delay = min(MAX_DELAY, BASE_DELAY * 2 ** (attempt - 1)) + random.uniform(0, 0.5)
            print(f"Transient SQL error (try {attempt}/{MAX_TRIES}): retrying in {delay:.1f} s")
            time.sleep(delay)


def count_orders(customer_id: str) -> int:
    def work(connection):
        return connection.cursor().execute(
            "SELECT COUNT(*) FROM dbo.Orders WHERE CustomerId = ?", customer_id).fetchval()
    return run_with_retry(work)


if __name__ == "__main__":
    print(count_orders("C-0001"))
