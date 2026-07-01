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
金融数据定时同步调度器

多数据源自动更新：
  每日 02:00  →  公告 + 互动易（增量）
  每周日 03:00 → 执行信息（增量）
  启动时自动补齐超过间隔未同步的数据源

用法：
    python sync_scheduler.py --time 02:00
    python sync_scheduler.py --time 02:00 --run-immediately
"""

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta

from announcement_fetcher import AnnouncementFetcher


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "sync_scheduler.log"), encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger(__name__)

# 数据源调度配置
SOURCE_SCHEDULE = {
    "announcement": {"interval_hours": 24, "label": "公告"},
    "irm": {"interval_hours": 24, "label": "互动易"},
    "shareholder": {"interval_hours": 24, "label": "股东变动"},
    "pledge": {"interval_hours": 24, "label": "股权质押"},
    "share_change": {"interval_hours": 168, "label": "股本变动"},
    "management": {"interval_hours": 24, "label": "高管变动"},
    "industry": {"interval_hours": 168, "label": "行业变动"},
    "enforcement": {"interval_hours": 168, "label": "执行信息"},
}


class SyncScheduler:
    def __init__(self, api_key: str, base_url: str, sync_time: str = "02:00", delay: float = 1.0):
        self.api_key = api_key
        self.base_url = base_url
        self.sync_time = sync_time
        self.delay = delay
        self.fetcher = AnnouncementFetcher(
            api_key=api_key, base_url=base_url, cninfo_delay=delay
        )
        self._running = True

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        logger.info(f"收到信号 {signum}，调度器即将退出...")
        self._running = False

    def _seconds_until_next_run(self) -> float:
        now = datetime.now()
        hour, minute = map(int, self.sync_time.split(":"))
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        return (next_run - now).total_seconds()

    def _should_sync(self, stock_code: str, source: str) -> bool:
        """检查某数据源是否已超过同步间隔，需要更新。"""
        config = SOURCE_SCHEDULE[source]
        state = self.fetcher.db.get_sync_state(stock_code, source)
        if not state or not state.get("last_synced_at"):
            return True
        last_sync = datetime.fromisoformat(state["last_synced_at"])
        elapsed = datetime.now() - last_sync
        return elapsed > timedelta(hours=config["interval_hours"])

    def _sync_source_for_stock(self, stock_code: str, source: str) -> dict:
        """对某只股票的某个数据源执行增量同步。"""
        label = SOURCE_SCHEDULE[source]["label"]
        result = {"source": source, "stock": stock_code, "changed": False, "error": None}

        sync_methods = {
            "announcement": lambda: self.fetcher.sync_stock(
                stock_code,
                start_date=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
                end_date=datetime.now().strftime("%Y-%m-%d"),
            ),
            "irm": lambda: self.fetcher.sync_irm(stock_code),
            "shareholder": lambda: self.fetcher.sync_shareholder(stock_code),
            "pledge": lambda: self.fetcher.sync_pledge(stock_code),
            "share_change": lambda: self.fetcher.sync_share_change(stock_code),
            "management": lambda: self.fetcher.sync_management(stock_code),
            "industry": lambda: self.fetcher.sync_industry(stock_code),
            "enforcement": lambda: self.fetcher.sync_enforcement(stock_code),
        }

        try:
            fn = sync_methods.get(source)
            if fn:
                ret = fn()
                if source == "announcement":
                    result["changed"] = (ret.new_count > 0)
                    result["new_count"] = ret.new_count
                else:
                    result["changed"] = ret is not None
        except Exception as e:
            result["error"] = str(e)[:200]
        return result

    def run_once(self, force: bool = False) -> None:
        """执行一轮全量检查：遍历所有股票，对需要更新的数据源做增量同步。"""
        logger.info("=" * 50)
        logger.info("开始增量同步检查..." + (" (强制模式)" if force else ""))

        stocks = self.fetcher.db.list_stocks()
        if not stocks:
            logger.info("暂无股票，跳过")
            return

        is_sunday = datetime.now().weekday() == 6
        results = []

        for stock in stocks:
            for source, config in SOURCE_SCHEDULE.items():
                # 执行信息只在周日同步
                if source == "enforcement" and not is_sunday:
                    continue

                if force or self._should_sync(stock.code, source):
                    label = config["label"]
                    logger.info(f"  [{label}] {stock.code} {stock.name} 需要更新...")
                    result = self._sync_source_for_stock(stock.code, source)
                    results.append(result)
                    status = "✅ 有新数据" if result["changed"] else "⏭️ 无变化"
                    if result["error"]:
                        status = f"❌ {result['error']}"
                    logger.info(f"  [{label}] {stock.code} {status}")
                else:
                    # 未到同步间隔，初始化状态
                    pass

        changed = sum(1 for r in results if r["changed"])
        errors = sum(1 for r in results if r["error"])
        logger.info(f"本轮完成: {len(results)} 次检查, {changed} 次有更新, {errors} 次出错")
        logger.info("=" * 50)

    def run_on_startup(self) -> None:
        """启动时补齐所有超过间隔的数据源。"""
        logger.info("启动检查：强制检查所有数据源...")
        self.run_once(force=True)

    def run(self, run_immediately: bool = False) -> None:
        """启动定时循环。"""
        logger.info(f"定时同步调度器启动，每天 {self.sync_time} 执行")
        logger.info(f"数据源: 公告(24h) | 互动易(24h) | 执行信息(每周日)")

        if run_immediately:
            self.run_on_startup()

        while self._running:
            wait_seconds = self._seconds_until_next_run()
            logger.info(f"距离下次同步还有 {wait_seconds / 3600:.2f} 小时")

            while wait_seconds > 0 and self._running:
                sleep_time = min(wait_seconds, 60)
                time.sleep(sleep_time)
                wait_seconds -= sleep_time

            if self._running:
                self.run_once()

        logger.info("调度器已停止")


def main():
    parser = argparse.ArgumentParser(description="金融数据定时同步调度器")
    parser.add_argument("--api-key", default=os.getenv("RAGFLOW_API_KEY"), help="RAGFlow API Key")
    parser.add_argument("--base-url", default="http://localhost:9380", help="RAGFlow Base URL")
    parser.add_argument("--time", default="02:00", help="每天同步时间，例如 02:00")
    parser.add_argument("--run-immediately", action="store_true", help="启动时立即补齐过期数据")
    parser.add_argument("--delay", type=float, default=1.0, help="请求间隔秒数")
    args = parser.parse_args()

    if not args.api_key:
        print("[ERROR] 请提供 --api-key 或设置环境变量 RAGFLOW_API_KEY")
        sys.exit(1)

    scheduler = SyncScheduler(
        api_key=args.api_key,
        base_url=args.base_url,
        sync_time=args.time,
        delay=args.delay,
    )
    scheduler.run(run_immediately=args.run_immediately)


if __name__ == "__main__":
    main()
