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
中国执行信息公开网 & 信用中国 客户端

查询公司被执行信息、失信被执行人、行政处罚等。
使用 akshare 获取数据，降级使用 requests 直接请求。
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import requests


@dataclass
class EnforcementRecord:
    company_name: str
    case_number: str = ""
    court: str = ""
    filing_date: str = ""
    status: str = ""  # 执行中/已结案/失信
    amount: str = ""   # 执行标的
    reason: str = ""   # 案由


@dataclass
class DishonestyRecord:
    company_name: str
    case_number: str = ""
    court: str = ""
    publish_date: str = ""
    reason: str = ""
    performance: str = ""  # 履行情况


@dataclass
class CreditRecord:
    company_name: str
    record_type: str = ""  # 行政许可/行政处罚/红名单/黑名单
    title: str = ""
    publish_date: str = ""
    authority: str = ""
    content: str = ""


class EnforcementClient:
    """执行信息 & 信用中国 客户端"""

    ZXGK_SEARCH_URL = "https://zxgk.court.gov.cn/zhixing/newsearch/search"
    CREDIT_SEARCH_URL = "https://www.creditchina.gov.cn/api/search"

    def __init__(self, delay: float = 2.0):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36"
            ),
            "Accept": "application/json",
        })

    def search_enforcement(
        self,
        company_name: str,
    ) -> List[EnforcementRecord]:
        """查询被执行信息。"""
        records: List[EnforcementRecord] = []
        try:
            resp = self.session.post(
                self.ZXGK_SEARCH_URL,
                json={
                    "searchCourtName": "全国法院",
                    "selectVal": "被执行人",
                    "pName": company_name,
                    "currentPage": 1,
                    "pageSize": 10,
                },
                timeout=30,
            )
            data = resp.json()
            items = data.get("data", data.get("result", []))
            if isinstance(items, dict):
                items = items.get("records", items.get("list", []))

            for item in items:
                records.append(EnforcementRecord(
                    company_name=company_name,
                    case_number=str(item.get("caseCode", item.get("caseno", ""))),
                    court=str(item.get("courtName", item.get("court", ""))),
                    filing_date=str(item.get("filingDate", item.get("regDate", ""))),
                    status=str(item.get("caseState", item.get("status", ""))),
                    amount=str(item.get("execMoney", item.get("amount", ""))),
                    reason=str(item.get("duty", item.get("reason", ""))),
                ))
                time.sleep(0.3)
        except Exception as e:
            print(f"[ENFORCEMENT] 被执行人查询失败: {e}")

        # 也查询失信被执行人
        try:
            time.sleep(self.delay)
            resp = self.session.post(
                self.ZXGK_SEARCH_URL,
                json={
                    "searchCourtName": "全国法院",
                    "selectVal": "失信被执行人",
                    "pName": company_name,
                    "currentPage": 1,
                    "pageSize": 10,
                },
                timeout=30,
            )
            data = resp.json()
            items = data.get("data", data.get("result", []))
            if isinstance(items, dict):
                items = items.get("records", items.get("list", []))

            for item in items:
                # 用 ExecutionRecord 也存失信信息（案由字段不同）
                records.append(EnforcementRecord(
                    company_name=company_name + "（失信）",
                    case_number=str(item.get("caseCode", item.get("caseno", ""))),
                    court=str(item.get("courtName", item.get("court", ""))),
                    filing_date=str(item.get("publishDate", item.get("regDate", ""))),
                    status="失信",
                    amount=str(item.get("disruptTypeName", item.get("amount", ""))),
                    reason=str(item.get("duty", item.get("reason", ""))),
                ))
                time.sleep(0.3)
        except Exception as e:
            print(f"[ENFORCEMENT] 失信查询失败: {e}")

        return records

    def fetch_by_akshare(self, company_name: str) -> List[EnforcementRecord]:
        """使用 akshare 获取执行信息（备选方案）。"""
        try:
            import akshare as ak
            # akshare 有企业信用相关接口
            df = ak.legal_person_enforcement(company_name=company_name)
            records = []
            for _, row in df.iterrows():
                records.append(EnforcementRecord(
                    company_name=company_name,
                    case_number=str(row.get("案号", "")),
                    court=str(row.get("执行法院", "")),
                    filing_date=str(row.get("立案时间", "")),
                    amount=str(row.get("执行标的", "")),
                    reason=str(row.get("案由", "")),
                ))
            return records
        except Exception as e:
            print(f"[ENFORCEMENT] akshare 查询失败: {e}")
            return []

    def to_document_text(
        self,
        enforcement: List[EnforcementRecord],
    ) -> str:
        """将执行/信用记录转为知识库文档文本。"""
        if not enforcement:
            return ""

        company = enforcement[0].company_name.replace("（失信）", "")
        lines = [
            f"# {company} 司法执行及信用信息",
            f"# 更新时间：{datetime.now().strftime('%Y-%m-%d')}",
            "",
        ]

        # 分组：被执行人 vs 失信
        normal = [r for r in enforcement if "失信" not in r.company_name]
        dishonest = [r for r in enforcement if "失信" in r.company_name]

        if normal:
            lines.append(f"## 被执行人信息（{len(normal)} 条）")
            lines.append("")
            for i, r in enumerate(normal, 1):
                lines.append(f"### {i}. {r.case_number}")
                lines.append(f"- 执行法院：{r.court}")
                lines.append(f"- 立案日期：{r.filing_date}")
                lines.append(f"- 执行标的：{r.amount}")
                lines.append(f"- 案由：{r.reason}")
                lines.append("")

        if dishonest:
            lines.append(f"## 失信被执行人信息（{len(dishonest)} 条）")
            lines.append("")
            for i, r in enumerate(dishonest, 1):
                lines.append(f"### {i}. {r.case_number}")
                lines.append(f"- 执行法院：{r.court}")
                lines.append(f"- 发布日期：{r.filing_date}")
                lines.append(f"- 具体情形：{r.amount}")
                lines.append(f"- 义务：{r.reason}")
                lines.append("")

        if not normal and not dishonest:
            lines.append("未查询到相关执行记录。")

        return "\n".join(lines)
