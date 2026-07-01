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
金融公告问答系统 - 管理 API 服务

为前端提供股票、公告、同步日志的管理接口。

启动：
    pip install fastapi uvicorn
    python api_server.py

默认监听：http://localhost:9500
"""

import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional

import asyncio
import json
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))

from announcement_fetcher import AnnouncementFetcher, SUPPORTED_CATEGORY_MAP
from models import Announcement, Database, Stock, SyncLog
from ragflow_model_compat import router as ragflow_model_router


RAGFLOW_API_KEY = os.getenv("RAGFLOW_API_KEY")
RAGFLOW_BASE_URL = os.getenv("RAGFLOW_BASE_URL", "http://localhost:9380")
API_PORT = int(os.getenv("FINANCIAL_API_PORT", "9500"))


def get_fetcher():
    if not RAGFLOW_API_KEY:
        raise RuntimeError("环境变量 RAGFLOW_API_KEY 未设置")
    fetcher = AnnouncementFetcher(api_key=RAGFLOW_API_KEY, base_url=RAGFLOW_BASE_URL)
    # 注入 SSE 回调：数据变化时推送事件
    def _on_sync_update(stock_code: str, event: str, data: dict):
        _sse_publish(stock_code, event, data)
    fetcher.on_sync_update = _on_sync_update
    return fetcher


# 全局数据库实例
db = Database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时检查 RAGFlow 连接
    try:
        get_fetcher()
    except Exception as e:
        print(f"[WARN] RAGFlow 连接检查失败: {e}")
    yield


app = FastAPI(
    title="Financial Q&A API",
    description="金融公告问答系统管理接口",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ragflow_model_router)


# ------------------ SSE Event Hub ------------------

_sse_queues: dict = {}  # stock_code -> list[asyncio.Queue]

def _sse_publish(stock_code: str, event: str, data: dict):
    """向所有监听该股票的 SSE 客户端推送事件。"""
    msg = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    targets = _sse_queues.get(stock_code, []) + _sse_queues.get("*", [])
    for q in targets:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass

# ------------------ Pydantic Models ------------------

class StockCreate(BaseModel):
    code: str
    name: Optional[str] = None
    embedding_model: str = "BAAI/bge-m3@SILICONFLOW"
    llm_id: str = "deepseek-chat@DeepSeek"


class StockOut(BaseModel):
    code: str
    name: str
    exchange: str
    market: str
    kb_id: Optional[str]
    chat_id: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    announcement_count: int = 0
    sync_progress: Optional[dict] = None
    source_states: Optional[dict] = None  # {source: {last_synced_at, last_data_hash, status, message}}


class AnnouncementOut(BaseModel):
    id: Optional[int]
    stock_code: str
    stock_name: Optional[str]
    title: str
    announcement_time: str
    category: Optional[str]
    url: str
    status: str
    created_at: Optional[str]


class SyncLogOut(BaseModel):
    id: Optional[int]
    stock_code: str
    started_at: str
    ended_at: Optional[str]
    total_count: int
    new_count: int
    failed_count: int
    message: Optional[str]


class SyncRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    category: Optional[str] = None


# ------------------ Helpers ------------------

def _stock_out(stock: Stock) -> StockOut:
    progress = None
    logs = db.list_sync_logs(stock_code=stock.code, limit=1)
    if logs and not logs[0].ended_at and logs[0].message:
        parts = logs[0].message.split("|")
        if len(parts) == 3:
            progress = {
                "stage": parts[0],
                "current": int(parts[1]),
                "total": int(parts[2]),
                "total_anns": logs[0].total_count,
                "new_anns": logs[0].new_count,
            }
        elif len(parts) == 1:
            progress = {
                "stage": parts[0],
                "total_anns": logs[0].total_count,
                "new_anns": logs[0].new_count,
            }

    # 各数据源同步状态
    states = db.list_sync_states(stock_code=stock.code)
    source_states = {}
    for s in states:
        source_states[s["source"]] = {
            "last_synced_at": s.get("last_synced_at"),
            "last_data_hash": s.get("last_data_hash", "")[:8] if s.get("last_data_hash") else None,
            "status": s.get("status"),
            "message": s.get("message"),
        }

    return StockOut(
        **{k: v for k, v in stock.__dict__.items()},
        announcement_count=db.count_announcements(stock.code),
        sync_progress=progress,
        source_states=source_states if source_states else None,
    )


def _ann_out(ann: Announcement) -> AnnouncementOut:
    stock = db.get_stock(ann.stock_code)
    return AnnouncementOut(
        id=ann.id,
        stock_code=ann.stock_code,
        stock_name=stock.name if stock else None,
        title=ann.title,
        announcement_time=ann.announcement_time,
        category=ann.category,
        url=ann.url,
        status=ann.status,
        created_at=ann.created_at,
    )


# ------------------ API Endpoints ------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/events/{stock_code}")
async def sse_events(stock_code: str):
    """SSE 端点：当数据有更新时主动推送事件给前端。"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _sse_queues.setdefault(stock_code, []).append(queue)

    async def event_stream():
        try:
            # 初始连接确认
            yield f"event: connected\ndata: {json.dumps({'stock_code': stock_code})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _sse_queues.get(stock_code, []).remove(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/stocks", response_model=List[StockOut])
def list_stocks():
    stocks = db.list_stocks()
    return [_stock_out(s) for s in stocks]


@app.post("/api/stocks", response_model=StockOut)
async def create_stock(req: StockCreate, background_tasks: BackgroundTasks):
    fetcher = get_fetcher()
    code = req.code.strip()

    # 输入可能是代码或名称：非纯数字则按名称搜索
    if not code.isdigit() or len(code) != 6:
        resolved = fetcher.cninfo.search_code_by_name(code)
        if not resolved:
            raise HTTPException(status_code=400, detail=f"未找到匹配的股票：{code}")
        code = resolved

    # 自动补充股票名称
    name = req.name
    if not name:
        name = fetcher.cninfo.get_stock_name(code) or code
    try:
        stock = fetcher.add_stock(
            code,
            name=name or None,
            embedding_model=req.embedding_model,
            llm_id=req.llm_id,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 后台自动同步所有数据源
    def _sync():
        try:
            results = fetcher.sync_all_sources(code)
            print(f"[AUTO_SYNC] {code} 全部同步完成: {results}")
        except Exception as e:
            print(f"[AUTO_SYNC] {code} 同步失败: {e}")

    background_tasks.add_task(_sync)
    return _stock_out(stock)


@app.delete("/api/stocks/{code}")
def delete_stock(code: str):
    db.delete_stock(code)
    return {"message": f"股票 {code} 已删除"}


@app.post("/api/stocks/{code}/sync")
def sync_stock(code: str, req: SyncRequest):
    fetcher = get_fetcher()
    category_code = SUPPORTED_CATEGORY_MAP.get(req.category, "") if req.category else ""
    # 默认只同步最近 30 天，首次同步更快，便于快速创建 Chat；后续可全量同步
    start_date = req.start_date or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    try:
        log = fetcher.sync_stock(
            code,
            start_date=start_date,
            end_date=req.end_date,
            category=category_code,
        )
        return {
            "stock_code": log.stock_code,
            "total_count": log.total_count,
            "new_count": log.new_count,
            "failed_count": log.failed_count,
            "message": log.message,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/stocks/sync-all")
def sync_all(req: SyncRequest):
    fetcher = get_fetcher()
    category_code = SUPPORTED_CATEGORY_MAP.get(req.category, "") if req.category else ""
    try:
        logs = fetcher.sync_all(
            start_date=req.start_date,
            end_date=req.end_date,
            category=category_code,
        )
        return [
            {
                "stock_code": log.stock_code,
                "total_count": log.total_count,
                "new_count": log.new_count,
                "failed_count": log.failed_count,
                "message": log.message,
            }
            for log in logs
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/stocks/{code}/sync-irm")
def sync_stock_irm(code: str):
    """同步投资者互动问答（增量，MD5 指纹去重）。"""
    fetcher = get_fetcher()
    try:
        prev_state = db.get_sync_state(code, "irm")
        prev_hash = prev_state.get("last_data_hash") if prev_state else None
        doc_id = fetcher.sync_irm(code)
        new_state = db.get_sync_state(code, "irm")
        new_hash = new_state.get("last_data_hash") if new_state else None
        changed = (prev_hash != new_hash)
        return {
            "message": "同步完成" if changed else ("无新数据" if doc_id else "无互动问答数据"),
            "doc_id": doc_id,
            "changed": changed,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/stocks/{code}/sync-enforcement")
def sync_stock_enforcement(code: str):
    """同步司法执行信息（增量，MD5 指纹去重）。"""
    fetcher = get_fetcher()
    try:
        prev_state = db.get_sync_state(code, "enforcement")
        prev_hash = prev_state.get("last_data_hash") if prev_state else None
        doc_id = fetcher.sync_enforcement(code)
        new_state = db.get_sync_state(code, "enforcement")
        new_hash = new_state.get("last_data_hash") if new_state else None
        changed = (prev_hash != new_hash)
        return {
            "message": "同步完成" if changed else ("无新数据" if doc_id else "无执行信息"),
            "doc_id": doc_id,
            "changed": changed,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---- 扩展数据源同步端点（统一模式：增量 + MD5 指纹去重）----

_EXTRA_SOURCES = {
    "shareholder": ("股东持股变动", "sync_shareholder"),
    "pledge": ("股权质押", "sync_pledge"),
    "share_change": ("股本结构变动", "sync_share_change"),
    "management": ("高管持股变动", "sync_management"),
    "industry": ("行业归属变动", "sync_industry"),
}

def _make_sync_endpoint(source: str, label: str, method: str):
    """工厂函数：为每个数据源生成标准化的同步端点。"""
    def handler(code: str):
        fetcher = get_fetcher()
        try:
            prev_state = db.get_sync_state(code, source)
            prev_hash = prev_state.get("last_data_hash") if prev_state else None
            doc_id = getattr(fetcher, method)(code)
            new_state = db.get_sync_state(code, source)
            new_hash = new_state.get("last_data_hash") if new_state else None
            changed = (prev_hash != new_hash)
            return {
                "message": "同步完成" if changed else ("无新数据" if doc_id else f"无{label}数据"),
                "doc_id": doc_id,
                "changed": changed,
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    return handler

for src, (label, method) in _EXTRA_SOURCES.items():
    app.post(f"/api/stocks/{{code}}/sync-{src}")(
        _make_sync_endpoint(src, label, method)
    )

@app.get("/api/announcements", response_model=List[AnnouncementOut])
def list_announcements(stock_code: Optional[str] = None, status: Optional[str] = None):
    anns = db.list_announcements(stock_code=stock_code, status=status)
    return [_ann_out(a) for a in anns]


@app.get("/api/sync-logs", response_model=List[SyncLogOut])
def list_sync_logs(stock_code: Optional[str] = None, limit: int = 50):
    logs = db.list_sync_logs(stock_code=stock_code, limit=limit)
    return [SyncLogOut(**log.__dict__) for log in logs]


@app.get("/api/categories")
def list_categories():
    return list(SUPPORTED_CATEGORY_MAP.keys())


if __name__ == "__main__":
    import uvicorn

    print(f"启动金融公告管理 API，监听 http://0.0.0.0:{API_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
