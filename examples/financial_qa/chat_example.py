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
金融公告问答调用示例

用法：
    export RAGFLOW_API_KEY="your-api-key"
    python chat_example.py --stock "000001_平安银行" --question "2024年的净利润是多少？"
"""

import argparse
import os
import sys

from ragflow_sdk import RAGFlow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock", required=True, help="股票目录名，例如 000001_平安银行")
    parser.add_argument("--question", required=True, help="要问的问题")
    parser.add_argument("--base-url", default="http://localhost:9380")
    parser.add_argument("--stream", action="store_true", default=True, help="是否流式输出")
    args = parser.parse_args()

    api_key = os.getenv("RAGFLOW_API_KEY")
    if not api_key:
        print("[ERROR] 请设置环境变量 RAGFLOW_API_KEY")
        sys.exit(1)

    rag = RAGFlow(api_key=api_key, base_url=args.base_url)

    chat_name = f"{args.stock}_问答助手"
    chats = [c for c in rag.list_chats() if c.name == chat_name]
    if not chats:
        print(f"[ERROR] 未找到 Chat: {chat_name}，请先运行 setup_financial_kb.py")
        sys.exit(1)

    chat = chats[0]
    session = chat.create_session(name="默认会话")

    print(f"[用户] {args.question}\n")
    print("[助手] ", end="", flush=True)
    for msg in session.ask(args.question, stream=args.stream):
        print(msg.content, end="", flush=True)
    print()


if __name__ == "__main__":
    main()
