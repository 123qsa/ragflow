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
金融公告问答系统批量搭建脚本

用法：
    1. 确保已安装 ragflow-sdk: pip install ragflow-sdk
    2. 配置环境变量：
       export RAGFLOW_API_KEY="your-api-key"
       export RAGFLOW_BASE_URL="http://localhost:9380"
    3. 按目录整理好公告：
       announcements/000001_平安银行/*.pdf
       announcements/000002_万科A/*.pdf
    4. 运行：
       python setup_financial_kb.py \
           --announcements-dir ./announcements \
           --embedding-model "BAAI/bge-m3@SILICONFLOW" \
           --llm-id "deepseek-chat@DeepSeek"
"""

import argparse
import os
import sys
import time
from pathlib import Path

from ragflow_sdk import RAGFlow
from ragflow_sdk.modules.dataset import DataSet


def build_parser_config(rag: RAGFlow):
    return DataSet.ParserConfig(
        rag,
        {
            "chunk_token_num": 512,
            "delimiter": "\\n!?;。；！？",
            "layout_recognize": "DeepDOC",
            "task_page_size": 12,
            "auto_keywords": 3,
            "auto_questions": 0,
            "filename_embd_weight": 0.1,
        },
    )


SUPPORTED_SUFFIXES = {".pdf", ".docx", ".doc", ".txt", ".md"}


def create_or_get_dataset(rag: RAGFlow, name: str, embedding_model: str):
    """创建知识库，如果已存在则返回已有的。"""
    datasets = rag.list_datasets()
    for ds in datasets:
        if ds.name == name:
            print(f"[INFO] 知识库已存在: {name} (id={ds.id})")
            return ds

    ds = rag.create_dataset(
        name=name,
        embedding_model=embedding_model,
        chunk_method="naive",
        parser_config=build_parser_config(rag),
    )
    print(f"[OK] 创建知识库: {name} (id={ds.id})")
    return ds


def upload_announcements(dataset, stock_dir: Path):
    """批量上传某只股票的全部公告。"""
    files = []
    for path in sorted(stock_dir.iterdir()):
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        files.append({
            "display_name": path.name,
            "blob": path.read_bytes(),
        })

    if not files:
        print(f"[WARN] {stock_dir} 下没有找到支持的文档")
        return []

    print(f"[INFO] 正在上传 {len(files)} 份公告到 {dataset.name} ...")
    docs = dataset.upload_documents(files)
    print(f"[OK] 上传完成: {len(docs)} 份")
    return docs


def parse_and_wait(dataset, docs, timeout_sec=1800, poll_interval=10):
    """触发解析并轮询直到完成。"""
    if not docs:
        return
    doc_ids = [d.id for d in docs]
    print(f"[INFO] 开始解析 {len(doc_ids)} 份文档...")
    dataset.async_parse_documents(doc_ids)

    start = time.time()
    while time.time() - start < timeout_sec:
        all_done = True
        failed = 0
        running = 0
        for d in dataset.list_documents(id=doc_ids):
            if d.run == "DONE":
                continue
            elif d.run == "FAIL":
                failed += 1
            else:
                running += 1
                all_done = False

        if all_done and running == 0:
            print(f"[OK] 解析完成: 成功 {len(doc_ids) - failed}, 失败 {failed}")
            return

        print(
            f"[INFO] 等待解析... 运行中 {running}, 失败 {failed} "
            f"(已等待 {int(time.time() - start)}s)"
        )
        time.sleep(poll_interval)

    print(f"[WARN] 解析超时 (> {timeout_sec}s)，请后续在 Web UI 中检查")


def create_or_get_chat(rag: RAGFlow, name: str, dataset, llm_id: str):
    """创建 Chat Assistant，如果已存在则返回已有的。"""
    chats = rag.list_chats()
    for chat in chats:
        if chat.name == name:
            print(f"[INFO] Chat 已存在: {name} (id={chat.id})")
            return chat

    chat = rag.create_chat(
        name=name,
        dataset_ids=[dataset.id],
        llm_id=llm_id,
        prompt_config={
            "system": (
                "你是一位专业的金融分析师，擅长基于上市公司公告回答投资者提问。\n"
                "回答时请注意：\n"
                "1. 所有结论必须基于提供的公告原文；\n"
                "2. 如果公告中没有相关信息，请明确说明；\n"
                "3. 涉及财务数据、时间、比例时，请给出具体出处。"
            ),
            "prologue": "您好，我是您的股票公告分析助手。请直接提问，我将基于公告内容为您解答。",
        },
        top_n=8,
        similarity_threshold=0.2,
        vector_similarity_weight=0.7,
    )
    print(f"[OK] 创建 Chat: {name} (id={chat.id})")
    return chat


def main():
    parser = argparse.ArgumentParser(description="批量搭建金融公告问答系统")
    parser.add_argument(
        "--announcements-dir",
        required=True,
        type=Path,
        help="公告根目录，子目录名为 股票代码_股票名称",
    )
    parser.add_argument(
        "--embedding-model",
        required=True,
        help="Embedding 模型，例如 BAAI/bge-m3@SILICONFLOW",
    )
    parser.add_argument(
        "--llm-id",
        required=True,
        help="LLM 模型 ID，例如 deepseek-chat@DeepSeek",
    )
    parser.add_argument(
        "--parse-timeout",
        type=int,
        default=1800,
        help="解析等待超时（秒），默认 1800",
    )
    parser.add_argument(
        "--skip-parse",
        action="store_true",
        help="仅上传，不触发解析",
    )
    args = parser.parse_args()

    api_key = os.getenv("RAGFLOW_API_KEY")
    base_url = os.getenv("RAGFLOW_BASE_URL", "http://localhost:9380")
    if not api_key:
        print("[ERROR] 请设置环境变量 RAGFLOW_API_KEY")
        sys.exit(1)

    rag = RAGFlow(api_key=api_key, base_url=base_url)

    root = args.announcements_dir.resolve()
    if not root.is_dir():
        print(f"[ERROR] 目录不存在: {root}")
        sys.exit(1)

    stock_dirs = [d for d in root.iterdir() if d.is_dir()]
    if not stock_dirs:
        print(f"[ERROR] {root} 下没有找到股票子目录")
        sys.exit(1)

    print(f"[INFO] 共发现 {len(stock_dirs)} 只股票")

    for stock_dir in sorted(stock_dirs):
        stock_name = stock_dir.name
        print(f"\n{'=' * 60}")
        print(f"[STOCK] 处理: {stock_name}")
        print(f"{'=' * 60}")

        # 1. 创建知识库
        kb_name = f"financial_{stock_name}"
        dataset = create_or_get_dataset(rag, kb_name, args.embedding_model)

        # 2. 上传公告
        docs = upload_announcements(dataset, stock_dir)

        # 3. 触发解析
        if docs and not args.skip_parse:
            parse_and_wait(dataset, docs, timeout_sec=args.parse_timeout)

        # 4. 创建 Chat
        chat_name = f"{stock_name}_问答助手"
        chat = create_or_get_chat(rag, chat_name, dataset, args.llm_id)

    print("\n[ALL DONE] 全部股票处理完成，请在 Web UI 的 'Chat' 页面查看各问答助手。")


if __name__ == "__main__":
    main()
