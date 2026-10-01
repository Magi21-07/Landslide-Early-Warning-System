"""
src/risk/risk_store.py
-----------------------
Phase 5.9: Risk State Storage — Repository Pattern.

Defines an abstract RiskStore interface that decouples the risk engine from
its storage backend. The concrete SQLiteRiskStore uses Python's built-in
sqlite3 module only (no SQLAlchemy, no external ORMs).

Designed to be swapped for PostgreSQL/PostGIS in Phase 6+ without changing
any risk-engine code that calls the interface methods.

NO external dependencies — standard library only: abc, sqlite3, json, datetime.
"""

import json
import logging
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column map — keeps the SQL schema and Python dicts in sync
# ---------------------------------------------------------------------------

# Ordered list of (column_name, sqlite_type) for the risk_history table.
# All columns are nullable (except id, location_id, timestamp).
_COLUMNS: List[tuple] = [
    ("id",                        "INTEGER PRIMARY KEY AUTOINCREMENT"),
    ("location_id",               "TEXT NOT NULL"),
    ("latitude",                  "REAL"),
    ("longitude",                 "REAL"),
    ("timestamp",                 "TEXT NOT NULL"),    # UTC ISO-8601
    ("observation_date",          "TEXT"),             # YYYY-MM-DD
    ("susceptibility_probability","REAL"),
    ("susceptibility_class",      "TEXT"),
    ("rainfall_1d",               "REAL"),
    ("rainfall_3d",               "REAL"),
    ("rainfall_7d",               "REAL"),
    ("rainfall_15d",              "REAL"),
    ("rainfall_trigger_score",    "INTEGER"),
    ("rainfall_trigger_state",    "TEXT"),
    ("dynamic_risk",              "TEXT"),
    ("risk_level",                "TEXT"),
    ("data_source",               "TEXT"),
    ("stale",                     "INTEGER DEFAULT 0"), # SQLite BOOLEAN as INT
    ("error_info",                "TEXT"),
]

# Names of non-PK columns (used for INSERT)
_DATA_COLUMNS: List[str] = [c[0] for c in _COLUMNS if c[0] != "id"]

# The column names that correspond directly to dict keys we read/write
_SELECT_COLS: str = ", ".join(c[0] for c in _COLUMNS)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class RiskStore(ABC):
    """
    Abstract storage interface for risk assessment results.

    Implementations must be swappable (SQLite today, PostGIS tomorrow)
    without modifying any upstream risk-engine code.
    """

    @abstractmethod
    def save_risk_result(self, result_dict: Dict[str, Any]) -> None:
        """
        Persist a single risk assessment record.

        Parameters
        ----------
        result_dict : dict
            Must contain 'location_id' and 'timestamp' (ISO-8601 UTC string).
            All other schema columns are optional.
        """

    @abstractmethod
    def get_latest_risk(self, location_id: str) -> Optional[Dict[str, Any]]:
        """Return the most-recent record for a location, or None."""

    @abstractmethod
    def get_risk_history(
        self, location_id: str, limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Return up to `limit` records for a location, newest first.

        Parameters
        ----------
        location_id : str
        limit       : int  Maximum number of records to return.
        """

    @abstractmethod
    def get_last_successful_update(
        self, location_id: str
    ) -> Optional[datetime]:
        """
        Return the UTC datetime of the most-recent non-stale record,
        or None if no such record exists.
        """

    @abstractmethod
    def mark_stale(self, location_id: str, error_reason: str) -> None:
        """
        Mark the latest record for a location as stale and record the
        error_reason. If no record exists, inserts a minimal stale record.
        """


# ---------------------------------------------------------------------------
# SQLite concrete implementation
# ---------------------------------------------------------------------------

class SQLiteRiskStore(RiskStore):
    """
    Append-only SQLite backend for risk assessment history.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file, or ':memory:' for an in-memory DB.
    """

    def __init__(self, db_path: str = ":memory:"):
        self._db_path = db_path
        self._conn    = self._connect()
        self._init_schema()
        logger.info(
            "SQLiteRiskStore initialised at '%s'.", db_path
        )

    # ------------------------------------------------------------------ #
    # RiskStore interface implementation                                   #
    # ------------------------------------------------------------------ #

    def save_risk_result(self, result_dict: Dict[str, Any]) -> None:
        """
        INSERT a new row into risk_history.
        Append-only: we never UPDATE existing rows; history is preserved.

        Raises
        ------
        ValueError : if 'location_id' or 'timestamp' are missing.
        """
        if 'location_id' not in result_dict:
            raise ValueError("result_dict must contain 'location_id'.")
        if 'timestamp' not in result_dict:
            raise ValueError("result_dict must contain 'timestamp'.")

        row = self._dict_to_row(result_dict)
        placeholders = ", ".join(["?"] * len(_DATA_COLUMNS))
        cols_sql     = ", ".join(_DATA_COLUMNS)
        sql = f"INSERT INTO risk_history ({cols_sql}) VALUES ({placeholders})"

        with self._conn:
            self._conn.execute(sql, row)

        logger.debug(
            "Saved risk result for location '%s' at %s.",
            result_dict['location_id'], result_dict['timestamp']
        )

    def get_latest_risk(self, location_id: str) -> Optional[Dict[str, Any]]:
        """Return the newest record (by timestamp) for a location."""
        sql = (
            f"SELECT {_SELECT_COLS} FROM risk_history "
            "WHERE location_id = ? "
            "ORDER BY timestamp DESC LIMIT 1"
        )
        cur = self._conn.execute(sql, (location_id,))
        row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    def get_risk_history(
        self, location_id: str, limit: int = 30
    ) -> List[Dict[str, Any]]:
        """Return up to `limit` records, newest first."""
        sql = (
            f"SELECT {_SELECT_COLS} FROM risk_history "
            "WHERE location_id = ? "
            "ORDER BY timestamp DESC LIMIT ?"
        )
        cur  = self._conn.execute(sql, (location_id, limit))
        rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_last_successful_update(
        self, location_id: str
    ) -> Optional[datetime]:
        """Return UTC datetime of the most-recent stale=0 record, or None."""
        sql = (
            "SELECT timestamp FROM risk_history "
            "WHERE location_id = ? AND stale = 0 "
            "ORDER BY timestamp DESC LIMIT 1"
        )
        cur = self._conn.execute(sql, (location_id,))
        row = cur.fetchone()
        if not row:
            return None
        return self._parse_ts(row[0])

    def mark_stale(self, location_id: str, error_reason: str) -> None:
        """
        Mark the latest record for a location as stale.

        Strategy (append-only log):
          1. Fetch the latest record.
          2. Clone it with stale=1 and the new error_reason + a fresh timestamp.
          3. INSERT the cloned row so history is preserved.
        If no previous record exists, insert a minimal stale sentinel row.
        """
        latest = self.get_latest_risk(location_id)
        now    = datetime.now(timezone.utc).isoformat()

        if latest:
            new_row = dict(latest)
            new_row.pop('id', None)
            new_row['stale']      = 1
            new_row['error_info'] = error_reason
            new_row['timestamp']  = now
        else:
            new_row = {
                'location_id': location_id,
                'timestamp':   now,
                'stale':       1,
                'error_info':  error_reason,
            }

        self.save_risk_result(new_row)
        logger.info(
            "Marked location '%s' as stale: %s", location_id, error_reason
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,   # safe for single-threaded test/usage
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        col_defs = ", ".join(f"{name} {dtype}" for name, dtype in _COLUMNS)
        ddl = (
            f"CREATE TABLE IF NOT EXISTS risk_history ({col_defs}); "
            "CREATE INDEX IF NOT EXISTS idx_location_ts "
            "ON risk_history (location_id, timestamp DESC);"
        )
        with self._conn:
            self._conn.executescript(ddl)
        logger.debug("risk_history table verified / created.")

    def _dict_to_row(self, d: Dict[str, Any]) -> tuple:
        """
        Map a result dict to an ordered tuple matching _DATA_COLUMNS.
        Missing keys default to None. Booleans converted to 0/1 for SQLite.
        """
        def _coerce(col: str, val: Any) -> Any:
            if val is None:
                return None
            if col == 'stale':
                return int(bool(val))
            if isinstance(val, (dict, list)):
                return json.dumps(val)
            return val

        return tuple(
            _coerce(col, d.get(col)) for col in _DATA_COLUMNS
        )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a sqlite3.Row to a plain Python dict."""
        return dict(row)

    @staticmethod
    def _parse_ts(ts_str: str) -> datetime:
        """Parse an ISO-8601 UTC timestamp string to a timezone-aware datetime."""
        # Python 3.7+ fromisoformat doesn't handle 'Z' suffix directly
        ts_str = ts_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def close(self) -> None:
        """Explicitly close the database connection."""
        self._conn.close()
        logger.debug("SQLiteRiskStore connection closed.")
