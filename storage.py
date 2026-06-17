"""
SQLite 存储层
- usage_history：历史用量快照（用于将来画趋势图）
- alert_history：已发送的提醒记录（用于防重复）
"""

import os
import sqlite3
import time
from typing import Optional


DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage.db")


class Storage:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS usage_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ts            INTEGER NOT NULL,
            level         TEXT NOT NULL,
            percent       REAL NOT NULL,
            reset_ts      INTEGER NOT NULL,
            update_ts     INTEGER NOT NULL,
            status        TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_uh_ts ON usage_history(ts);
        CREATE INDEX IF NOT EXISTS idx_uh_level_ts ON usage_history(level, ts);

        CREATE TABLE IF NOT EXISTS alert_history (
            level         TEXT NOT NULL,
            threshold     INTEGER NOT NULL,
            cycle_reset   INTEGER NOT NULL,
            alerted_at    INTEGER NOT NULL,
            PRIMARY KEY (level, threshold, cycle_reset)
        );
        """)
        self.conn.commit()

    # ---------- 用量快照 ----------
    def save_snapshot(self, data: dict):
        """保存一次拉取结果（三个 level 各一行）"""
        now = int(time.time())
        status = data.get("status", "")
        update_ts = data.get("update_ts", now)
        rows = []
        for level, q in data.get("quotas", {}).items():
            rows.append((
                now, level, float(q.get("percent", 0)),
                int(q.get("reset_ts", 0)), update_ts, status,
            ))
        if rows:
            self.conn.executemany(
                "INSERT INTO usage_history(ts,level,percent,reset_ts,update_ts,status) "
                "VALUES (?,?,?,?,?,?)",
                rows,
            )
            self.conn.commit()

    def cleanup_old(self, keep_days: int = 90):
        """清理过期历史记录"""
        cutoff = int(time.time()) - keep_days * 86400
        self.conn.execute("DELETE FROM usage_history WHERE ts < ?", (cutoff,))
        self.conn.commit()

    # ---------- 提醒去重 ----------
    def has_alerted(self, level: str, threshold: int, cycle_reset: int) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM alert_history WHERE level=? AND threshold=? AND cycle_reset=?",
            (level, threshold, cycle_reset),
        )
        return cur.fetchone() is not None

    def mark_alerted(self, level: str, threshold: int, cycle_reset: int):
        self.conn.execute(
            "INSERT OR IGNORE INTO alert_history(level,threshold,cycle_reset,alerted_at) "
            "VALUES (?,?,?,?)",
            (level, threshold, cycle_reset, int(time.time())),
        )
        self.conn.commit()

    def cleanup_alerts_before(self, ts: int):
        """清理早于 ts 的旧提醒记录（cycle_reset 已过期的）"""
        self.conn.execute("DELETE FROM alert_history WHERE cycle_reset < ?", (ts,))
        self.conn.commit()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
