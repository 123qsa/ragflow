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
巨潮资讯网 (cninfo.com.cn) 公告抓取客户端

不依赖 akshare，直接使用 requests 调用公开 API。
"""

import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urljoin

import requests


CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_PDF_BASE = "http://static.cninfo.com.cn/"
CNINFO_ALL_STOCK_URL = "http://www.cninfo.com.cn/new/data/all_stock.json"

# 交易所和板块映射（新版巨潮 plate 参数）
EXCHANGE_MAP = {
    "60": ("sse", "sh", "shmb"),   # 沪市主板
    "600": ("sse", "sh", "shmb"),
    "601": ("sse", "sh", "shmb"),
    "603": ("sse", "sh", "shmb"),
    "605": ("sse", "sh", "shmb"),
    "68": ("sse", "kcb", "shkcp"),  # 科创板
    "30": ("szse", "cyb", "szcy"), # 创业板
    "300": ("szse", "cyb", "szcy"),
    "301": ("szse", "cyb", "szcy"),
    "00": ("szse", "sz", "szmb"),  # 深市主板
    "000": ("szse", "sz", "szmb"),
    "001": ("szse", "sz", "szmb"),
    "002": ("szse", "sz", "szmb"),
    "003": ("szse", "sz", "szmb"),
    "8": ("bse", "bj", "bjse"),    # 北交所
    "4": ("bse", "bj", "bjse"),
    "92": ("bse", "bj", "bjse"),
}


@dataclass
class CninfoAnnouncement:
    stock_code: str
    stock_name: str
    title: str
    announcement_time: str
    category: str
    url: str
    adjunct_url: str


class CninfoClient:
    def __init__(self, delay: float = 1.0, max_retries: int = 3):
        self.delay = delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self._stock_cache: dict = {}
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "http://www.cninfo.com.cn",
                "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
            }
        )

    def _load_stock_cache(self) -> None:
        if self._stock_cache:
            return
        try:
            resp = self.session.get(CNINFO_ALL_STOCK_URL, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("stockList", []):
                self._stock_cache[item["code"]] = item
        except Exception as e:
            print(f"[WARN] 加载股票清单失败: {e}")

    def _get_stock_info(self, code: str) -> dict:
        self._load_stock_cache()
        return self._stock_cache.get(code, {})

    def get_stock_name(self, code: str) -> str:
        """根据股票代码查询股票简称，查不到返回空字符串"""
        info = self._get_stock_info(code.strip())
        return info.get("zwjc", "")

    def search_code_by_name(self, keyword: str) -> Optional[str]:
        """根据股票名称（或拼音）模糊搜索股票代码，返回最匹配的一个。"""
        self._load_stock_cache()
        keyword_lower = keyword.strip().lower()
        # 精确匹配
        for code, info in self._stock_cache.items():
            if info.get("zwjc", "") == keyword.strip():
                return code
        # 模糊匹配（名称包含关键字）
        matches = []
        for code, info in self._stock_cache.items():
            name = info.get("zwjc", "")
            pinyin = info.get("pinyin", "")
            if keyword_lower in name.lower() or keyword_lower in pinyin.lower():
                matches.append((code, name))
        # 返回最短代码（通常是主板股票）
        if matches:
            matches.sort(key=lambda x: len(x[0]))
            return matches[0][0]
        return None

    @staticmethod
    def _classify_by_code(code: str) -> tuple:
        """根据股票代码判断交易所、板块、plate。"""
        code = code.strip()
        for prefix in ["68", "301", "30", "605", "603", "601", "60", "003", "002", "001", "00", "92", "8", "4"]:
            if code.startswith(prefix):
                return EXCHANGE_MAP.get(prefix, ("szse", "sz", "szmb"))
        return EXCHANGE_MAP.get(code[:2], ("szse", "sz", "szmb"))

    def classify_stock(self, code: str) -> tuple:
        """返回 (exchange, market, plate, org_id)。"""
        code = code.strip()
        info = self._get_stock_info(code)
        exchange, market, plate = self._classify_by_code(code)
        org_id = info.get("orgId", "")
        return exchange, market, plate, org_id

    def _post(self, data: dict) -> dict:
        for attempt in range(self.max_retries):
            try:
                resp = self.session.post(CNINFO_QUERY_URL, data=data, timeout=30)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.delay * (attempt + 1) + random.uniform(0, 1))
        return {}

    def fetch_announcements(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        category: str = "",
    ) -> List[CninfoAnnouncement]:
        """
        抓取指定股票的全部公告。

        Args:
            stock_code: 股票代码，例如 "000001"
            start_date: 开始日期，格式 "YYYY-MM-DD"，默认一年前
            end_date: 结束日期，格式 "YYYY-MM-DD"，默认今天
            category: 公告类型代码，空字符串表示全部
        """
        exchange, market, plate, org_id = self.classify_stock(stock_code)
        if not org_id:
            raise ValueError(f"无法获取股票 {stock_code} 的 orgId，请检查代码是否正确")

        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

        se_date = f"{start_date}~{end_date}"
        stock_param = f"{stock_code},{org_id}"

        page_num = 1
        page_size = 30
        results: List[CninfoAnnouncement] = []

        while True:
            data = {
                "pageNum": page_num,
                "pageSize": page_size,
                "tabName": "fulltext",
                "column": exchange,
                "stock": stock_param,
                "searchkey": "",
                "secid": "",
                "plate": plate,
                "category": category,
                "trade": "",
                "seDate": se_date,
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            }

            resp = self._post(data)
            announcements = resp.get("announcements") or []

            if not announcements:
                break

            for item in announcements:
                adjunct = item.get("adjunctUrl", "")
                url = urljoin(CNINFO_PDF_BASE, adjunct) if adjunct else ""
                ts = item.get("announcementTime")
                if isinstance(ts, (int, float)):
                    # 巨潮返回毫秒时间戳
                    announcement_time = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
                elif isinstance(ts, str):
                    announcement_time = ts.strip()[:10]
                else:
                    announcement_time = ""
                results.append(
                    CninfoAnnouncement(
                        stock_code=item.get("secCode", stock_code).strip(),
                        stock_name=item.get("secName", "").strip(),
                        title=item.get("announcementTitle", "").strip(),
                        announcement_time=announcement_time,
                        category=item.get("category", "").strip(),
                        url=url,
                        adjunct_url=adjunct,
                    )
                )

            total = resp.get("totalRecordNum", 0)
            if page_num * page_size >= total:
                break

            page_num += 1
            time.sleep(self.delay + random.uniform(0, 0.5))

        return results

    def download_pdf(self, url: str, save_path: str) -> bool:
        """下载 PDF 文件。"""
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(url, timeout=60, stream=True)
                resp.raise_for_status()
                with open(save_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            except Exception:
                if attempt == self.max_retries - 1:
                    return False
                time.sleep(self.delay * (attempt + 1) + random.uniform(0, 1))
        return False
