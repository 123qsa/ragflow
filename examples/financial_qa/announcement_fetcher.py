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
金融公告抓取器

整合 cninfo 客户端、本地数据库和 RAGFlow SDK，实现：
- 抓取公告列表
- 增量下载 PDF
- 上传到 RAGFlow 知识库
- 触发解析
- 记录同步状态
"""

import argparse
import hashlib
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from ragflow_sdk import RAGFlow
from ragflow_sdk.modules.dataset import DataSet


def build_parser_config(rag: RAGFlow):
    return DataSet.ParserConfig(
        rag,
        {
            "chunk_token_num": 1024,
            "delimiter": "\\n!?;。；！？",
            "layout_recognize": "DeepDOC",
            "task_page_size": 12,
            "auto_keywords": 0,
            "auto_questions": 0,
            "filename_embd_weight": 0.1,
            "html4excel": True,
        },
    )

from cninfo_client import CninfoClient
from irm_client import IrmClient
from enforcement_client import EnforcementClient
from extra_sources_client import ExtraSourcesClient, SOURCE_REGISTRY
from models import Announcement, Database, Stock, SyncLog


DOWNLOAD_DIR = Path(__file__).parent / "downloads"
SUPPORTED_CATEGORY_MAP = {
    "年度报告": "category_ndbg_szsh",
    "半年度报告": "category_bndbg_szsh",
    "一季度报告": "category_yjdbg_szsh",
    "三季度报告": "category_sjdbg_szsh",
    "业绩预告": "category_yjygjxz_szsh",
    "权益分派": "category_qyfz_szsh",
    "股东大会": "category_gddh_szsh",
    "董事会": "category_dshgg_szsh",
    "监事会": "category_jshgg_szsh",
    "增发": "category_zf_szsh",
    "股权激励": "category_gqjl_szsh",
    "配股": "category_pg_szsh",
    "股权变动": "category_gqbd_szsh",
    "风险提示": "category_fxts_szsh",
    "澄清致歉": "category_cqzq_szsh",
    "日常经营": "category_rcjy_szsh",
    "公司治理": "category_gszl_szsh",
    "中介报告": "category_zj_szsh",
}


def sanitize_filename(name: str) -> str:
    """将公告标题转换为合法文件名。"""
    name = name.replace(" ", "_")
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    return name[:120]


class AnnouncementFetcher:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "http://localhost:9380",
        download_dir: Optional[Path] = None,
        db: Optional[Database] = None,
        cninfo_delay: float = 1.0,
    ):
        self.api_key = api_key or os.getenv("RAGFLOW_API_KEY")
        self.base_url = base_url
        if not self.api_key:
            raise ValueError("请提供 RAGFLOW_API_KEY 或设置环境变量")

        self.rag = RAGFlow(api_key=self.api_key, base_url=self.base_url)
        self.db = db or Database()
        self.cninfo = CninfoClient(delay=cninfo_delay)
        self.irm = IrmClient()
        self.enforcement = EnforcementClient(delay=2.0)
        self.extra = ExtraSourcesClient()
        self.download_dir = download_dir or DOWNLOAD_DIR
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.on_sync_update = None  # SSE callback: (stock_code, event, data)

    def add_stock(
        self,
        code: str,
        name: Optional[str] = None,
        embedding_model: str = "BAAI/bge-m3@SILICONFLOW",
        llm_id: str = "deepseek-chat@DeepSeek",
    ) -> Stock:
        """添加一只股票，自动创建 KB；Chat 在首次同步公告解析完成后创建。"""
        code = code.strip()
        existing = self.db.get_stock(code)
        if existing:
            print(f"[INFO] 股票已存在: {code}")
            return existing

        # 如果未提供名称，尝试从公告列表获取
        if not name:
            anns = self.cninfo.fetch_announcements(code, start_date="2020-01-01", end_date="2099-12-31")
            name = anns[0].stock_name if anns else code

        exchange, market, plate, org_id = self.cninfo.classify_stock(code)
        kb = None
        try:
            # 创建 KB
            kb_name = f"financial_{code}_{name}"
            kb = self.rag.create_dataset(
                name=kb_name,
                embedding_model=embedding_model,
                chunk_method="naive",
                parser_config=build_parser_config(self.rag),
            )
            # SDK 不支持 language 参数，通过 REST API 设置为 Chinese
            try:
                import requests as _req
                _req.put(
                    f"{self.base_url}/api/v1/datasets/{kb.id}",
                    json={"language": "Chinese"},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10,
                )
            except Exception:
                pass
            print(f"[OK] 创建知识库: {kb_name} ({kb.id})")

            # 写入数据库（chat_id 为空，等待首次同步后创建）
            stock = Stock(
                code=code,
                name=name,
                exchange=exchange,
                market=market,
                kb_id=kb.id,
                chat_id=None,
                llm_id=llm_id,
            )
            self.db.add_stock(stock)
            return self.db.get_stock(code)
        except Exception:
            # 失败时清理已创建的知识库
            if kb and kb.id:
                try:
                    self.rag.delete_datasets([kb.id])
                except Exception:
                    pass
            raise

    def _ensure_chat(self, stock: Stock, dataset: DataSet) -> Optional[str]:
        """如果股票还没有 Chat，且知识库已有解析完成的文件，则创建 Chat。"""
        if stock.chat_id:
            return stock.chat_id

        # 检查是否至少有一份已解析完成的文档
        has_parsed = any(
            getattr(d, "run", "") == "DONE" for d in dataset.list_documents()
        )
        if not has_parsed:
            print("[INFO] 知识库暂无解析完成的文档，跳过创建 Chat")
            return None

        chat_name = f"{stock.code}_{stock.name}_问答助手"
        llm_id = stock.llm_id or "deepseek-chat@DeepSeek"
        try:
            chat = self.rag.create_chat(
                name=chat_name,
                dataset_ids=[stock.kb_id],
                llm_id=llm_id,
                prompt_config={
                    "prompt": (
                        "你是一位专业的金融分析师，擅长基于上市公司公告回答投资者提问。\n"
                        "回答时请注意：\n"
                        "1. 所有结论必须基于提供的公告原文；\n"
                        "2. 如果公告中没有相关信息，请明确说明；\n"
                        "3. 涉及财务数据、时间、比例时，请给出具体出处。"
                    ),
                    "opener": "您好，我是您的股票公告分析助手。请直接提问，我将基于公告内容为您解答。",
                    "show_quote": True,
                },
                top_n=8,
                similarity_threshold=0.2,
                vector_similarity_weight=0.7,
            )
            print(f"[OK] 创建 Chat: {chat_name} ({chat.id})")
            self.db.update_stock_kb_chat(stock.code, chat_id=chat.id)
            return chat.id
        except Exception as e:
            print(f"[WARN] 创建 Chat 失败: {e}")
            return None

    def sync_stock(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        category: str = "",
        parse_timeout: int = 1800,
    ) -> SyncLog:
        """同步单只股票的全部/指定类型公告。"""
        stock = self.db.get_stock(code)
        if not stock:
            raise ValueError(f"股票不存在: {code}，请先调用 add_stock")

        if not stock.kb_id:
            raise ValueError(f"股票 {code} 未关联知识库")

        log = SyncLog(
            id=None,
            stock_code=code,
            started_at=datetime.now().isoformat(),
            ended_at=None,
            total_count=0,
            new_count=0,
            failed_count=0,
            message=None,
        )
        log_id = self.db.add_sync_log(log)

        try:
            datasets = self.rag.list_datasets(id=stock.kb_id)
            if not datasets:
                raise ValueError(f"知识库 {stock.kb_id} 不存在")
            dataset = datasets[0]
        except Exception as e:
            self.db.update_sync_log(
                log_id,
                ended_at=datetime.now().isoformat(),
                message=f"获取知识库失败: {e}",
            )
            return self.db.list_sync_logs(stock_code=code, limit=1)[0]

        def _report_progress(stage: str, current: int = 0, total: int = 0):
            """更新同步进度到数据库"""
            self.db.update_sync_log(
                log_id,
                message=f"{stage}|{current}|{total}",
            )
            if self.on_sync_update:
                self.on_sync_update(code, "sync_progress", {
                    "source": "announcements", "stage": stage,
                    "current": current, "total": total,
                })

        _report_progress("fetching")
        print(f"\n[STOCK] 同步 {code} {stock.name}")
        try:
            anns = self.cninfo.fetch_announcements(
                code,
                start_date=start_date,
                end_date=end_date,
                category=category,
            )
        except Exception as e:
            self.db.update_sync_log(
                log_id,
                ended_at=datetime.now().isoformat(),
                message=f"抓取公告列表失败: {e}",
            )
            return self.db.list_sync_logs(stock_code=code, limit=1)[0]

        self.db.update_sync_log(log_id, total_count=len(anns))
        _report_progress("filtering", 0, len(anns))
        print(f"[INFO] 远程共 {len(anns)} 份公告")

        new_anns: List[Announcement] = []
        for ann in anns:
            db_ann = self.db.get_announcement(code, ann.title, ann.announcement_time)
            if db_ann and db_ann.status != "failed":
                # 已成功/处理中的公告不再重复处理
                continue
            if db_ann and db_ann.status == "failed":
                # 失败记录重试：加入待处理列表，数据库记录会被 _process_one_announcement 更新
                new_anns.append(db_ann)
                continue
            new_ann = Announcement(
                id=None,
                stock_code=code,
                title=ann.title,
                announcement_time=ann.announcement_time,
                category=ann.category,
                url=ann.url,
                pdf_path=None,
                doc_id=None,
                status="pending",
            )
            if self.db.add_announcement(new_ann):
                new_anns.append(new_ann)

        print(f"[INFO] 新增 {len(new_anns)} 份公告")
        self.db.update_sync_log(log_id, new_count=len(new_anns))

        failed = 0
        uploaded_doc_ids = []
        doc_id_to_ann: Dict[str, Announcement] = {}
        total_new = len(new_anns)
        for idx, ann in enumerate(new_anns):
            _report_progress("downloading", idx, total_new)
            try:
                doc_id = self._process_one_announcement(dataset, ann)
                if doc_id:
                    uploaded_doc_ids.append(doc_id)
                    doc_id_to_ann[doc_id] = ann
                    # 立即触发单文档解析，避免批量触发时部分文档丢失
                    try:
                        dataset.async_parse_documents([doc_id])
                    except Exception as e:
                        print(f"[WARN] 触发解析失败 {ann.title}: {e}")
                else:
                    failed += 1
            except Exception as e:
                print(f"[ERROR] 处理公告失败 {ann.title}: {e}")
                self.db.update_announcement_status(
                    ann.stock_code, ann.title, ann.announcement_time, "failed"
                )
                failed += 1

        # 补充已上传但尚未解析的文档
        for ann in self.db.list_announcements(code, status="uploaded"):
            if ann.doc_id and ann.doc_id not in doc_id_to_ann:
                doc_id_to_ann[ann.doc_id] = ann

        if not doc_id_to_ann:
            print("[INFO] 没有待解析文档")
        else:
            _report_progress("parsing", 0, len(doc_id_to_ann))
            print(f"[INFO] 等待 {len(doc_id_to_ann)} 份文档解析完成...")
            try:
                self._wait_parse_done(dataset, doc_id_to_ann, timeout=parse_timeout,
                                      progress_callback=lambda cur, total: _report_progress("parsing", cur, total))
            except Exception as e:
                print(f"[WARN] 等待解析失败: {e}")

        # 首次同步且知识库已有解析文件后，自动创建 Chat
        _report_progress("creating_chat")
        try:
            self._ensure_chat(stock, dataset)
        except Exception as e:
            print(f"[WARN] 自动创建 Chat 失败: {e}")

        self.db.update_sync_log(
            log_id,
            ended_at=datetime.now().isoformat(),
            failed_count=failed,
            message=f"同步完成，新增 {len(new_anns) - failed}，失败 {failed}",
        )
        print(f"[OK] {code} 同步完成: 新增 {len(new_anns) - failed}，失败 {failed}")

        return self.db.list_sync_logs(stock_code=code, limit=1)[0]

    def _process_one_announcement(
        self, dataset: DataSet, ann: Announcement
    ) -> Optional[str]:
        """下载并上传单份公告。"""
        if not ann.url:
            return None

        safe_title = sanitize_filename(ann.title)
        pdf_path = (
            self.download_dir
            / ann.stock_code
            / f"{ann.announcement_time}_{safe_title}.pdf"
        )
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"[INFO] 下载: {ann.title}")
        if not self.cninfo.download_pdf(ann.url, str(pdf_path)):
            self.db.update_announcement_status(
                ann.stock_code, ann.title, ann.announcement_time, "failed"
            )
            return None

        self.db.update_announcement_status(
            ann.stock_code,
            ann.title,
            ann.announcement_time,
            "downloaded",
            pdf_path=str(pdf_path),
        )

        print(f"[INFO] 上传: {ann.title}")
        try:
            display_name = ann.title if ann.title.lower().endswith(".pdf") else f"{ann.title}.pdf"
            docs = dataset.upload_documents(
                [{"display_name": display_name, "blob": pdf_path.read_bytes()}]
            )
            doc_id = docs[0].id
        except Exception as e:
            print(f"[ERROR] 上传失败: {e}")
            self.db.update_announcement_status(
                ann.stock_code, ann.title, ann.announcement_time, "failed"
            )
            return None

        self.db.update_announcement_status(
            ann.stock_code,
            ann.title,
            ann.announcement_time,
            "uploaded",
            pdf_path=str(pdf_path),
            doc_id=doc_id,
        )
        return doc_id

    def _wait_parse_done(
        self,
        dataset: DataSet,
        doc_id_to_ann: Dict[str, Announcement],
        timeout: int = 1800,
        poll_interval: int = 10,
        progress_callback: callable = None,
    ) -> None:
        """轮询解析状态直到完成。"""
        doc_ids = list(doc_id_to_ann.keys())
        total = len(doc_ids)
        start = time.time()
        while time.time() - start < timeout:
            done_count = 0
            failed_count = 0
            running_count = 0
            for d in dataset.list_documents(page_size=1000):
                ann = doc_id_to_ann.get(d.id)
                if not ann:
                    continue
                if d.run == "DONE":
                    done_count += 1
                    self.db.update_announcement_status(
                        ann.stock_code,
                        ann.title,
                        ann.announcement_time,
                        "parsed",
                        doc_id=d.id,
                    )
                    continue
                elif d.run == "FAIL":
                    failed_count += 1
                else:
                    running_count += 1

            if progress_callback:
                progress_callback(done_count, total)

            if running_count == 0 and done_count + failed_count >= total:
                print(f"[OK] 解析完成: 成功 {done_count}, 失败 {failed_count}")
                return

            print(
                f"[INFO] 等待解析... 运行中 {running}, 失败 {failed} "
                f"(已等待 {int(time.time() - start)}s)"
            )
            time.sleep(poll_interval)

        print(f"[WARN] 解析超时 (> {timeout}s)")

    def sync_all(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        category: str = "",
        parse_timeout: int = 1800,
    ) -> List[SyncLog]:
        """同步所有股票。"""
        stocks = self.db.list_stocks()
        logs = []
        for stock in stocks:
            log = self.sync_stock(
                stock.code,
                start_date=start_date,
                end_date=end_date,
                category=category,
                parse_timeout=parse_timeout,
            )
            logs.append(log)
        return logs

    # ---- 互动易 ----

    def _compute_hash(self, text: str) -> str:
        """计算文本 MD5 指纹，用于增量检测。"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def _sync_text_source(
        self,
        code: str,
        source: str,
        doc_prefix: str,
        fetch_fn,
        to_text_fn,
    ) -> Optional[str]:
        """通用的文本数据源同步逻辑（IRM / Enforcement 共用）。

        1. 拉取数据 → 生成文本 → 计算 MD5
        2. 与上次指纹比对，无变化则跳过
        3. 有变化 → 删除旧 RAGFlow 文档 → 上传新的 → 更新状态
        """
        stock = self.db.get_stock(code)
        if not stock or not stock.kb_id:
            raise ValueError(f"股票 {code} 未就绪")

        datasets = self.rag.list_datasets(id=stock.kb_id)
        if not datasets:
            raise ValueError(f"知识库 {stock.kb_id} 不存在")
        dataset = datasets[0]

        # 标记运行中
        self.db.upsert_sync_state(code, source, status="running", message="正在拉取数据...")

        try:
            data = fetch_fn()
            text = to_text_fn(data) if data else ""
            if not text:
                self.db.upsert_sync_state(code, source, status="idle", message="无数据")
                return None

            new_hash = self._compute_hash(text)
            prev = self.db.get_sync_state(code, source)

            # 指纹相同 → 无变化
            if prev and prev.get("last_data_hash") == new_hash:
                self.db.upsert_sync_state(code, source, status="idle", message="无新数据")
                print(f"[{source.upper()}] {code} 无变化，跳过")
                return prev.get("doc_id")

            # 有变化 → 删旧文档，传新文档
            if prev and prev.get("doc_id"):
                try:
                    dataset.delete_documents([prev["doc_id"]])
                    print(f"[{source.upper()}] 已删除旧文档 {prev['doc_id']}")
                except Exception as e:
                    print(f"[{source.upper()}] 删除旧文档失败: {e}")

            doc_name = f"{doc_prefix}_{code}_{stock.name}.md"
            doc_id = self._upload_text_document(dataset, doc_name, text)
            if doc_id:
                self.db.upsert_sync_state(
                    code, source,
                    last_data_hash=new_hash,
                    doc_id=doc_id,
                    status="idle",
                    message="同步完成",
                )
                if self.on_sync_update:
                    self.on_sync_update(code, "source_updated", {
                        "source": source, "status": "idle", "changed": True,
                    })
                count = text.count("## 问答") if source == "irm" else text.count("###")
                print(f"[{source.upper()}] {code} 更新完成, doc={doc_id}")
            elif prev and prev.get("last_data_hash") == new_hash:
                if self.on_sync_update:
                    self.on_sync_update(code, "source_updated", {
                        "source": source, "status": "idle", "changed": False,
                    })
            return doc_id

        except Exception as e:
            self.db.upsert_sync_state(code, source, status="error", message=str(e)[:200])
            if self.on_sync_update:
                self.on_sync_update(code, "source_updated", {
                    "source": source, "status": "error", "error": str(e)[:100],
                })
            print(f"[{source.upper()}] 同步失败 {code}: {e}")
            return None

    def sync_irm(self, code: str) -> Optional[str]:
        """同步投资者互动问答（增量，MD5 指纹检测变化）。"""
        def _fetch():
            qs = self.irm.fetch_questions(code)
            return qs if qs else None
        return self._sync_text_source(
            code, "irm", "投资者互动问答",
            _fetch, lambda d: self.irm.to_document_text(d) if d else "",
        )

    # ---- 执行信息 ----

    def sync_enforcement(self, code: str) -> Optional[str]:
        """同步司法执行信息（增量，MD5 指纹检测变化）。"""
        stock_name = (self.db.get_stock(code) or Stock(code=code, name=code, exchange="", market="")).name
        def _fetch():
            records = self.enforcement.search_enforcement(stock_name)
            if not records:
                records = self.enforcement.fetch_by_akshare(stock_name)
            return records if records else None
        return self._sync_text_source(
            code, "enforcement", "司法执行信息",
            _fetch, lambda d: self.enforcement.to_document_text(d) if d else "",
        )

    # ---- 股东变动 ----

    def sync_shareholder(self, code: str) -> Optional[str]:
        def _fetch():
            doc = self.extra.fetch_shareholder_changes(code)
            return doc.text if doc and doc.item_count > 0 else None
        return self._sync_text_source(code, "shareholder", "股东持股变动", _fetch, lambda t: t)

    # ---- 股权质押 ----

    def sync_pledge(self, code: str) -> Optional[str]:
        def _fetch():
            doc = self.extra.fetch_pledge_info(code)
            return doc.text if doc and doc.item_count > 0 else None
        return self._sync_text_source(code, "pledge", "股权质押信息", _fetch, lambda t: t)

    # ---- 股本变动 ----

    def sync_share_change(self, code: str) -> Optional[str]:
        def _fetch():
            doc = self.extra.fetch_share_changes(code)
            return doc.text if doc and doc.item_count > 0 else None
        return self._sync_text_source(code, "share_change", "股本结构变动", _fetch, lambda t: t)

    # ---- 高管变动 ----

    def sync_management(self, code: str) -> Optional[str]:
        def _fetch():
            doc = self.extra.fetch_management_changes(code)
            return doc.text if doc and doc.item_count > 0 else None
        return self._sync_text_source(code, "management", "高管持股变动", _fetch, lambda t: t)

    # ---- 行业变动 ----

    def sync_industry(self, code: str) -> Optional[str]:
        def _fetch():
            doc = self.extra.fetch_industry_changes(code)
            return doc.text if doc and doc.item_count > 0 else None
        return self._sync_text_source(code, "industry", "行业归属变动", _fetch, lambda t: t)

    # ---- 全数据源同步 ----

    def sync_all_sources(self, code: str) -> dict:
        """同步所有数据源。"""
        results = {}
        print(f"\n{'='*50}")
        print(f"[ALL] 开始同步 {code} 全部数据源")
        print(f"{'='*50}")

        sources = [
            ("announcements", lambda: self.sync_stock(
                code, start_date="2020-01-01", end_date="2099-12-31"
            ).message),
            ("irm", lambda: f"doc={self.sync_irm(code)}" if self.sync_irm(code) else "无数据"),
            ("shareholder", lambda: f"doc={self.sync_shareholder(code)}" if self.sync_shareholder(code) else "无数据"),
            ("pledge", lambda: f"doc={self.sync_pledge(code)}" if self.sync_pledge(code) else "无数据"),
            ("share_change", lambda: f"doc={self.sync_share_change(code)}" if self.sync_share_change(code) else "无数据"),
            ("management", lambda: f"doc={self.sync_management(code)}" if self.sync_management(code) else "无数据"),
            ("industry", lambda: f"doc={self.sync_industry(code)}" if self.sync_industry(code) else "无数据"),
            ("enforcement", lambda: f"doc={self.sync_enforcement(code)}" if self.sync_enforcement(code) else "无数据"),
        ]

        for name, fn in sources:
            try:
                results[name] = fn()
            except Exception as e:
                results[name] = f"失败: {e}"

        print(f"[ALL] {code} 全部同步完成: {results}")
        return results

    def _upload_text_document(
        self, dataset, doc_name: str, text: str
    ) -> Optional[str]:
        """上传纯文本文档到知识库并触发解析。"""
        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(text)
            tmp_path = f.name

        try:
            docs = dataset.upload_documents(
                [{"display_name": doc_name, "blob": open(tmp_path, "rb").read()}]
            )
            if docs:
                doc_id = docs[0].id
                dataset.async_parse_documents([doc_id])
                print(f"[OK] 上传文档: {doc_name} (doc_id={doc_id})")
                return doc_id
        finally:
            os.unlink(tmp_path)

        return None


def main():
    parser = argparse.ArgumentParser(description="金融公告抓取工具")
    parser.add_argument("--api-key", default=os.getenv("RAGFLOW_API_KEY"), help="RAGFlow API Key")
    parser.add_argument("--base-url", default="http://localhost:9380", help="RAGFlow Base URL")
    parser.add_argument("--add-stock", help="添加单只股票，例如 000001")
    parser.add_argument("--stock-name", help="股票名称（可选）")
    parser.add_argument("--sync-stock", help="同步单只股票")
    parser.add_argument("--sync-all", action="store_true", help="同步所有股票")
    parser.add_argument("--start-date", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--category", choices=list(SUPPORTED_CATEGORY_MAP.keys()), help="公告类型")
    parser.add_argument("--embedding-model", default="BAAI/bge-m3@SILICONFLOW")
    parser.add_argument("--llm-id", default="deepseek-chat@DeepSeek")
    parser.add_argument("--parse-timeout", type=int, default=1800)
    parser.add_argument("--delay", type=float, default=1.0, help="请求间隔秒数")
    args = parser.parse_args()

    if not args.api_key:
        print("[ERROR] 请提供 --api-key 或设置环境变量 RAGFLOW_API_KEY")
        return

    category_code = SUPPORTED_CATEGORY_MAP.get(args.category, "")

    fetcher = AnnouncementFetcher(
        api_key=args.api_key,
        base_url=args.base_url,
        cninfo_delay=args.delay,
    )

    if args.add_stock:
        fetcher.add_stock(
            args.add_stock,
            name=args.stock_name,
            embedding_model=args.embedding_model,
            llm_id=args.llm_id,
        )

    if args.sync_stock:
        fetcher.sync_stock(
            args.sync_stock,
            start_date=args.start_date,
            end_date=args.end_date,
            category=category_code,
            parse_timeout=args.parse_timeout,
        )

    if args.sync_all:
        fetcher.sync_all(
            start_date=args.start_date,
            end_date=args.end_date,
            category=category_code,
            parse_timeout=args.parse_timeout,
        )


if __name__ == "__main__":
    main()
