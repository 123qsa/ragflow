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
为 RAGFlow 租户配置在线 Embedding Provider。

RAGFlow v0.25.6 Docker 镜像中 provider RESTful API 未启用，
这里使用旧的 /v1/llm/add_llm 接口，把模型写入 tenant_llm 表。

用法：
    .venv/bin/python setup_embedding_provider.py --provider siliconflow --api-key <key>
"""

import argparse
import os
import sys
from pathlib import Path

import requests


def get_env():
    api_key = os.getenv("RAGFLOW_API_KEY")
    base_url = os.getenv("RAGFLOW_BASE_URL", "http://localhost:9380")
    if not api_key:
        path = Path(__file__).parent / ".api_key"
        if path.exists():
            api_key = path.read_text().strip()
    if not api_key:
        print("请先设置 RAGFLOW_API_KEY 环境变量，或存在 .api_key 文件")
        sys.exit(1)
    return api_key, base_url


def add_llm(rag_api_key, base_url, factory, model_name, model_type, api_key):
    url = f"{base_url}/v1/llm/add_llm"
    headers = {"Authorization": f"Bearer {rag_api_key}"}
    payload = {
        "llm_factory": factory,
        "llm_name": model_name,
        "model_type": model_type,
        "api_key": api_key,
        "max_tokens": 8192,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(data.get("message", "add_llm failed"))
    return data.get("data")


def setup_siliconflow(rag_api_key, base_url, embedding_api_key):
    factory = "SILICONFLOW"
    model = "BAAI/bge-m3"
    print(f"配置 SiliconFlow embedding 模型: {model}")
    add_llm(rag_api_key, base_url, factory, model, "embedding", embedding_api_key)
    emb_id = f"{model}@{factory}"
    print(f"[OK] 已配置，embedding 模型标识: {emb_id}")
    return emb_id


def setup_zhipu(rag_api_key, base_url, embedding_api_key):
    factory = "ZHIPU-AI"
    model = "embedding-3"
    print(f"配置智谱 embedding 模型: {model}")
    add_llm(rag_api_key, base_url, factory, model, "embedding", embedding_api_key)
    emb_id = f"{model}@{factory}"
    print(f"[OK] 已配置，embedding 模型标识: {emb_id}")
    return emb_id


def setup_openai(rag_api_key, base_url, embedding_api_key):
    factory = "OpenAI"
    model = "text-embedding-3-small"
    print(f"配置 OpenAI embedding 模型: {model}")
    add_llm(rag_api_key, base_url, factory, model, "embedding", embedding_api_key)
    emb_id = f"{model}@{factory}"
    print(f"[OK] 已配置，embedding 模型标识: {emb_id}")
    return emb_id


PROVIDERS = {
    "siliconflow": setup_siliconflow,
    "zhipu": setup_zhipu,
    "openai": setup_openai,
}


def main():
    parser = argparse.ArgumentParser(description="配置 RAGFlow 在线 Embedding 模型")
    parser.add_argument(
        "--provider",
        choices=list(PROVIDERS.keys()),
        default="siliconflow",
        help="embedding 提供商",
    )
    parser.add_argument("--api-key", required=True, help="提供商的 API Key")
    args = parser.parse_args()

    rag_api_key, base_url = get_env()
    setup_fn = PROVIDERS[args.provider]
    emb_id = setup_fn(rag_api_key, base_url, args.api_key)

    print(f"\n如需使用，请在添加股票时指定 --embedding-model '{emb_id}'")


if __name__ == "__main__":
    main()
