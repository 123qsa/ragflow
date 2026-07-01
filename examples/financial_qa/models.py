#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
"""
金融公告问答系统 - SQLite 数据模型

表结构：
- stocks: 已接入的股票
- announcements: 已下载的公告
- sync_logs: 每次同步的日志
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


DB_PATH = Path(__file__).parent / "financial_qa.db"


@dataclass
class Stock:
    code: str
    name: str
    exchange: str  # sse, szse, bse
    market: str  # sh, sz, kcb, cyb, bj
    kb_id: Optional[str] = None
    chat_id: Optional[str] = None
    llm_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Announcement:
    id: Optional[int]
    stock_code: str
    title: str
    announcement_time: str
    category: str
    url: str
    pdf_path: Optional[str]
    doc_id: Optional[str]
    status: str  # pending, downloaded, uploaded, parsed, failed
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class SyncLog:
    id: Optional[int]
    stock_code: str
    started_at: str
    ended_at: Optional[str]
    total_count: int
    new_count: int
    failed_count: int
    message: Optional[str]
    source: Optional[str] = "announcement"
    created_at: Optional[str] = None


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._init_tables()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stocks (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    market TEXT NOT NULL,
                    kb_id TEXT,
                    chat_id TEXT,
                    llm_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    announcement_time TEXT NOT NULL,
                    category TEXT,
                    url TEXT NOT NULL,
                    pdf_path TEXT,
                    doc_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(stock_code, title, announcement_time)
                );

                CREATE INDEX IF NOT EXISTS idx_announcements_stock
                    ON announcements(stock_code);
                CREATE INDEX IF NOT EXISTS idx_announcements_status
                    ON announcements(status);

                CREATE TABLE IF NOT EXISTS sync_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    total_count INTEGER NOT NULL DEFAULT 0,
                    new_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    message TEXT,
                    source TEXT DEFAULT 'announcement',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS source_sync_state (
                    stock_code TEXT NOT NULL,
                    source TEXT NOT NULL,
                    last_synced_at TEXT,
                    last_data_hash TEXT,
                    doc_id TEXT,
                    status TEXT DEFAULT 'idle',
                    message TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (stock_code, source)
                );
                """
            )
            # 兼容旧表：添加 llm_id 列
            try:
                with self._connect() as conn:
                    conn.execute("ALTER TABLE stocks ADD COLUMN llm_id TEXT")
            except sqlite3.OperationalError:
                pass

            # 兼容旧表：sync_logs 添加 source 列
            try:
                with self._connect() as conn:
                    conn.execute("ALTER TABLE sync_logs ADD COLUMN source TEXT DEFAULT 'announcement'")
            except sqlite3.OperationalError:
                pass

    # ------------------ stocks ------------------

    def add_stock(self, stock: Stock) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO stocks (code, name, exchange, market, kb_id, chat_id, llm_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name,
                    exchange=excluded.exchange,
                    market=excluded.market,
                    kb_id=excluded.kb_id,
                    chat_id=excluded.chat_id,
                    llm_id=excluded.llm_id,
                    updated_at=excluded.updated_at
                """,
                (
                    stock.code,
                    stock.name,
                    stock.exchange,
                    stock.market,
                    stock.kb_id,
                    stock.chat_id,
                    stock.llm_id,
                    now,
                    now,
                ),
            )

    def get_stock(self, code: str) -> Optional[Stock]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM stocks WHERE code = ?", (code,)
            ).fetchone()
            return Stock(**dict(row)) if row else None

    def list_stocks(self) -> List[Stock]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM stocks ORDER BY created_at DESC"
            ).fetchall()
            return [Stock(**dict(r)) for r in rows]

    def update_stock_kb_chat(
        self, code: str, kb_id: Optional[str] = None, chat_id: Optional[str] = None, llm_id: Optional[str] = None
    ) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            if kb_id is not None:
                conn.execute(
                    "UPDATE stocks SET kb_id = ?, updated_at = ? WHERE code = ?",
                    (kb_id, now, code),
                )
            if chat_id is not None:
                conn.execute(
                    "UPDATE stocks SET chat_id = ?, updated_at = ? WHERE code = ?",
                    (chat_id, now, code),
                )
            if llm_id is not None:
                conn.execute(
                    "UPDATE stocks SET llm_id = ?, updated_at = ? WHERE code = ?",
                    (llm_id, now, code),
                )

    def delete_stock(self, code: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM announcements WHERE stock_code = ?", (code,))
            conn.execute("DELETE FROM stocks WHERE code = ?", (code,))

    # ------------------ announcements ------------------

    def add_announcement(self, ann: Announcement) -> bool:
        """添加公告，如果已存在则返回 False。"""
        now = datetime.now().isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO announcements
                    (stock_code, title, announcement_time, category, url, pdf_path, doc_id, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ann.stock_code,
                        ann.title,
                        ann.announcement_time,
                        ann.category,
                        ann.url,
                        ann.pdf_path,
                        ann.doc_id,
                        ann.status,
                        now,
                        now,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def get_announcement(
        self, stock_code: str, title: str, announcement_time: str
    ) -> Optional[Announcement]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM announcements
                WHERE stock_code = ? AND title = ? AND announcement_time = ?
                """,
                (stock_code, title, announcement_time),
            ).fetchone()
            return Announcement(**dict(row)) if row else None

    def list_announcements(
        self, stock_code: Optional[str] = None, status: Optional[str] = None
    ) -> List[Announcement]:
        sql = "SELECT * FROM announcements WHERE 1=1"
        params = []
        if stock_code:
            sql += " AND stock_code = ?"
            params.append(stock_code)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY announcement_time DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [Announcement(**dict(r)) for r in rows]

    def update_announcement_status(
        self,
        stock_code: str,
        title: str,
        announcement_time: str,
        status: str,
        pdf_path: Optional[str] = None,
        doc_id: Optional[str] = None,
    ) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE announcements
                SET status = ?, pdf_path = ?, doc_id = ?, updated_at = ?
                WHERE stock_code = ? AND title = ? AND announcement_time = ?
                """,
                (
                    status,
                    pdf_path,
                    doc_id,
                    now,
                    stock_code,
                    title,
                    announcement_time,
                ),
            )

    def count_announcements(self, stock_code: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM announcements WHERE stock_code = ?",
                (stock_code,),
            ).fetchone()
            return row[0]

    # ------------------ sync_logs ------------------

    def add_sync_log(self, log: SyncLog) -> int:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sync_logs
                (stock_code, started_at, ended_at, total_count, new_count, failed_count, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.stock_code,
                    log.started_at,
                    log.ended_at,
                    log.total_count,
                    log.new_count,
                    log.failed_count,
                    log.message,
                    now,
                ),
            )
            return cursor.lastrowid

    def update_sync_log(self, log_id: int, **kwargs) -> None:
        allowed = {"ended_at", "total_count", "new_count", "failed_count", "message"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        sql = "UPDATE sync_logs SET " + ", ".join(f"{k} = ?" for k in fields) + " WHERE id = ?"
        with self._connect() as conn:
            conn.execute(sql, (*fields.values(), log_id))

    def list_sync_logs(self, stock_code: Optional[str] = None, limit: int = 50) -> List[SyncLog]:
        sql = "SELECT * FROM sync_logs WHERE 1=1"
        params = []
        if stock_code:
            sql += " AND stock_code = ?"
            params.append(stock_code)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [SyncLog(**dict(r)) for r in rows]

    # ------------------ source_sync_state ------------------

    def upsert_sync_state(
        self,
        stock_code: str,
        source: str,
        last_data_hash: Optional[str] = None,
        doc_id: Optional[str] = None,
        status: str = "idle",
        message: Optional[str] = None,
    ) -> None:
        """写入或更新数据源同步状态。"""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO source_sync_state
                    (stock_code, source, last_synced_at, last_data_hash, doc_id, status, message, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stock_code, source) DO UPDATE SET
                    last_synced_at=excluded.last_synced_at,
                    last_data_hash=COALESCE(excluded.last_data_hash, source_sync_state.last_data_hash),
                    doc_id=COALESCE(excluded.doc_id, source_sync_state.doc_id),
                    status=excluded.status,
                    message=excluded.message,
                    updated_at=excluded.updated_at
                """,
                (stock_code, source, now, last_data_hash, doc_id, status, message, now),
            )

    def get_sync_state(self, stock_code: str, source: str) -> Optional[dict]:
        """获取某个数据源的同步状态。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM source_sync_state WHERE stock_code = ? AND source = ?",
                (stock_code, source),
            ).fetchone()
            return dict(row) if row else None

    def list_sync_states(self, stock_code: Optional[str] = None) -> List[dict]:
        """列出同步状态，可按股票筛选。"""
        sql = "SELECT * FROM source_sync_state WHERE 1=1"
        params = []
        if stock_code:
            sql += " AND stock_code = ?"
            params.append(stock_code)
        sql += " ORDER BY stock_code, source"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
