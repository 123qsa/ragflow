#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#
"""
扩展数据源客户端 — 股东变动、股权质押、股本变动、高管变动、行业变动

所有数据源通过 akshare 获取，统一转为 Markdown 文本后入库。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import pandas as pd

# ============================================================
# 通用接口
# ============================================================

@dataclass
class SourceDoc:
    """每个数据源产出一份文本文档"""
    text: str
    item_count: int


class ExtraSourcesClient:
    """扩展数据源统一客户端"""

    def __init__(self):
        self._pledge_cache: Optional[pd.DataFrame] = None
        self._pledge_cache_time: Optional[datetime] = None

    # ---- 股东持股变动 ----

    def fetch_shareholder_changes(self, stock_code: str) -> SourceDoc:
        """股东 / 董监高持股变动。"""
        rows = []
        # 深交所
        try:
            import akshare as ak
            df = ak.stock_share_hold_change_szse(symbol=stock_code)
            if df is not None and len(df) > 0:
                rows.append(f"## 深交所持股变动 ({len(df)} 条)")
                rows.append("")
                rows.append(df.head(100).to_markdown(index=False))
                rows.append("")
        except Exception as e:
            rows.append(f"_深交所持股变动获取失败: {e}_")

        # 上交所
        try:
            import akshare as ak
            df = ak.stock_share_hold_change_sse(symbol=stock_code)
            if df is not None and len(df) > 0:
                rows.append(f"## 上交所持股变动 ({len(df)} 条)")
                rows.append("")
                rows.append(df.head(100).to_markdown(index=False))
                rows.append("")
        except Exception:
            pass  # 深市股票正常没有上交所数据

        if not rows:
            return SourceDoc("", 0)

        header = [
            f"# 股东及董监高持股变动",
            f"# 股票：{stock_code}",
            f"# 更新时间：{datetime.now().strftime('%Y-%m-%d')}",
            "",
        ]
        return SourceDoc("\n".join(header + rows), len(rows) - 1)

    # ---- 股权质押 ----

    def fetch_pledge_info(self, stock_code: str) -> SourceDoc:
        """股权质押比例（全市场数据，缓存 24h）。"""
        cache_age = (
            (datetime.now() - self._pledge_cache_time).total_seconds()
            if self._pledge_cache_time else 99999
        )
        try:
            import akshare as ak
            if self._pledge_cache is None or cache_age > 86400:
                self._pledge_cache = ak.stock_gpzy_pledge_ratio_em()
                self._pledge_cache_time = datetime.now()
            df_all = self._pledge_cache
        except Exception as e:
            return SourceDoc(f"# 股权质押信息\n\n_获取失败: {e}_\n", 0)

        if df_all is None or len(df_all) == 0 or "股票代码" not in df_all.columns:
            return SourceDoc("", 0)

        matched = df_all[df_all["股票代码"] == stock_code]
        if len(matched) == 0:
            return SourceDoc("", 0)

        header = [
            f"# 股权质押信息",
            f"# 股票：{stock_code}",
            f"# 更新时间：{datetime.now().strftime('%Y-%m-%d')}",
            "",
            f"## 股权质押比例",
            "",
            matched.to_markdown(index=False),
        ]
        return SourceDoc("\n".join(header), len(matched))

    # ---- 股本变动 ----

    def fetch_share_changes(self, stock_code: str) -> SourceDoc:
        """公司股本结构变动。"""
        try:
            import akshare as ak
            df = ak.stock_share_change_cninfo(symbol=stock_code)
            if df is None or len(df) == 0:
                return SourceDoc("", 0)

            lines = [
                f"# 股本结构变动",
                f"# 股票：{stock_code}",
                f"# 更新时间：{datetime.now().strftime('%Y-%m-%d')}",
                f"# 共 {len(df)} 条记录",
                "",
                df.head(100).to_markdown(index=False),
            ]
            return SourceDoc("\n".join(lines), len(df))
        except Exception as e:
            print(f"[SHARE_CHANGE] {stock_code} 失败: {e}")
            return SourceDoc("", 0)

    # ---- 高管变动 ----

    def fetch_management_changes(self, stock_code: str) -> SourceDoc:
        """高管持股及人事变动。"""
        try:
            import akshare as ak
            df = ak.stock_management_change_ths(symbol=stock_code)
            if df is None or len(df) == 0:
                return SourceDoc("", 0)

            lines = [
                f"# 高管持股变动",
                f"# 股票：{stock_code}",
                f"# 更新时间：{datetime.now().strftime('%Y-%m-%d')}",
                f"# 共 {len(df)} 条记录",
                "",
                df.head(100).to_markdown(index=False),
            ]
            return SourceDoc("\n".join(lines), len(df))
        except Exception as e:
            print(f"[MGMT_CHANGE] {stock_code} 失败: {e}")
            return SourceDoc("", 0)

    # ---- 行业变动 ----

    def fetch_industry_changes(self, stock_code: str) -> SourceDoc:
        """行业归属变动。"""
        try:
            import akshare as ak
            df = ak.stock_industry_change_cninfo(symbol=stock_code)
            if df is None or len(df) == 0:
                return SourceDoc("", 0)

            lines = [
                f"# 行业归属变动",
                f"# 股票：{stock_code}",
                f"# 更新时间：{datetime.now().strftime('%Y-%m-%d')}",
                f"# 共 {len(df)} 条记录",
                "",
                df.head(100).to_markdown(index=False),
            ]
            return SourceDoc("\n".join(lines), len(df))
        except Exception as e:
            print(f"[INDUSTRY] {stock_code} 失败: {e}")
            return SourceDoc("", 0)


# ============================================================
# 数据源注册表
# ============================================================

SOURCE_REGISTRY = {
    "irm": {
        "label": "互动易",
        "doc_prefix": "投资者互动问答",
        "interval_hours": 24,
    },
    "enforcement": {
        "label": "执行信息",
        "doc_prefix": "司法执行信息",
        "interval_hours": 168,
    },
    "shareholder": {
        "label": "股东变动",
        "doc_prefix": "股东持股变动",
        "interval_hours": 24,
    },
    "pledge": {
        "label": "股权质押",
        "doc_prefix": "股权质押信息",
        "interval_hours": 24,
    },
    "share_change": {
        "label": "股本变动",
        "doc_prefix": "股本结构变动",
        "interval_hours": 168,
    },
    "management": {
        "label": "高管变动",
        "doc_prefix": "高管持股变动",
        "interval_hours": 24,
    },
    "industry": {
        "label": "行业变动",
        "doc_prefix": "行业归属变动",
        "interval_hours": 168,
    },
}
