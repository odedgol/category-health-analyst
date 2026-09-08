"""DB layer: the DuckDB adapter implementing `MetricsRepository`.

DuckDB stands in here for a real ClickHouse cluster — `connection.py`
manages the local database file and schema, `repository.py` is the only
place SQL is written. Swapping in `clickhouse-connect` later means
replacing this package's contents; nothing outside `db/` would change,
since every caller depends on `domain.ports.MetricsRepository`, not on
DuckDB directly.
"""
