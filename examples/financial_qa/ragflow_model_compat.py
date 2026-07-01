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
RAGFlow 0.25.x 与新版前端模型配置页兼容层

新版前端调用 /api/v1/providers、/api/v1/models、/api/v1/models/default，
但 0.25.6 后端只有 /v1/llm/* 与 /api/v1/users/me/models。
本模块将新版接口桥接到旧版接口，使"Set default models"页面可用。
"""

import os
from typing import List, Optional

import requests
from fastapi import APIRouter, HTTPException, Query, Request

RAGFLOW_BASE_URL = os.getenv("RAGFLOW_BASE_URL", "http://localhost:9380")

router = APIRouter(prefix="/api/v1")

# 前端 ModelTypeToField 的键 -> 租户信息字段
MODEL_TYPE_TO_FIELD = {
    "chat": "llm_id",
    "embedding": "embd_id",
    "image2text": "img2txt_id",
    "speech2text": "asr_id",
    "rerank": "rerank_id",
    "tts": "tts_id",
}


def _auth_headers(request: Request) -> dict:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    headers = {}
    if auth:
        headers["Authorization"] = auth
    return headers


def _wrap_ok(data):
    return {"code": 0, "data": data, "message": "success"}


def _ragflow_get(path: str, request: Request, params: Optional[dict] = None):
    url = f"{RAGFLOW_BASE_URL}{path}"
    return requests.get(url, headers=_auth_headers(request), params=params, timeout=30)


def _ragflow_patch(path: str, request: Request, json: dict):
    url = f"{RAGFLOW_BASE_URL}{path}"
    return requests.patch(url, headers=_auth_headers(request), json=json, timeout=30)


def _fetch_my_llms(request: Request) -> dict:
    resp = _ragflow_get("/v1/llm/my_llms", request)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json().get("data") or {}


@router.get("/providers")
def list_providers(request: Request, available: bool = Query(False)):
    """列出可用 provider（all_available=true）或当前租户已配置 provider。"""
    if available:
        resp = _ragflow_get("/v1/llm/factories", request)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        payload = resp.json()
        providers = []
        for f in payload.get("data", []) or []:
            providers.append(
                {
                    "name": f.get("name"),
                    "model_types": f.get("model_types", []),
                    "url": {"default": f.get("url", "")},
                }
            )
        return _wrap_ok(providers)

    # 当前租户已配置的 provider，从 /v1/llm/my_llms 推导
    my_llms = _fetch_my_llms(request)
    providers = []
    for provider_name, group in my_llms.items():
        if provider_name == "Builtin":
            continue
        llms = group.get("llm", []) or []
        model_types = sorted({m.get("type") for m in llms if m.get("type")})
        providers.append(
            {
                "name": provider_name,
                "model_types": list(model_types),
                "url": {"default": ""},
            }
        )
    return _wrap_ok(providers)


@router.get("/providers/{provider_name}/instances")
def list_provider_instances(provider_name: str, request: Request):
    """
    0.25.x 没有 provider instance 概念，把每个已配置 provider 模拟成单个 instance。
    """
    my_llms = _fetch_my_llms(request)
    group = my_llms.get(provider_name)
    if not group:
        return _wrap_ok([])
    return _wrap_ok(
        [
            {
                "id": provider_name,
                "instance_name": provider_name,
                "provider_id": provider_name,
                "provider_name": provider_name,
                "api_key": "***",
                "region": "default",
                "status": "1",
                "base_url": "",
            }
        ]
    )


@router.get("/providers/{provider_name}/instances/{instance_name}")
def show_provider_instance(provider_name: str, instance_name: str, request: Request):
    """查看单个 instance 详情。"""
    my_llms = _fetch_my_llms(request)
    group = my_llms.get(provider_name)
    if not group:
        raise HTTPException(status_code=404, detail="provider not found")
    return _wrap_ok(
        {
            "id": provider_name,
            "instance_name": provider_name,
            "provider_id": provider_name,
            "provider_name": provider_name,
            "api_key": "***",
            "region": "default",
            "status": "1",
            "base_url": "",
        }
    )


@router.get("/providers/{provider_name}/instances/{instance_name}/models")
def list_instance_models(provider_name: str, instance_name: str, request: Request):
    """列出某个 instance 下的模型。"""
    my_llms = _fetch_my_llms(request)
    group = my_llms.get(provider_name)
    if not group:
        return _wrap_ok([])
    models = []
    for m in group.get("llm", []) or []:
        model_type = m.get("type")
        models.append(
            {
                "name": m.get("name"),
                "model_type": [model_type] if model_type else [],
                "max_tokens": 0,
                "status": str(m.get("status", "0")),
            }
        )
    return _wrap_ok(models)


@router.get("/models")
def list_added_models(request: Request, type: Optional[str] = Query(None)):
    """列出当前租户已添加并启用的模型，格式适配新版前端 IAddedModel。"""
    my_llms = _fetch_my_llms(request)
    models: List[dict] = []
    for provider_name, group in my_llms.items():
        for m in group.get("llm", []) or []:
            if str(m.get("status", "0")) != "1":
                continue
            model_type = m.get("type")
            if type and model_type != type:
                continue
            models.append(
                {
                    "name": m.get("name"),
                    "provider_name": provider_name,
                    "instance_name": provider_name,
                    "instance_id": provider_name,
                    "provider_id": provider_name,
                    "model_type": [model_type] if model_type else [],
                }
            )
    return _wrap_ok(models)


@router.get("/models/default")
def list_default_models(request: Request):
    """把 /api/v1/users/me/models 的字段映射成新版 IDefaultModel 列表。"""
    resp = _ragflow_get("/api/v1/users/me/models", request)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    tenant = resp.json().get("data", {})

    models = []
    for model_type, field in MODEL_TYPE_TO_FIELD.items():
        value = tenant.get(field, "") or ""
        if "@" in value:
            model_name, model_provider = value.split("@", 1)
            models.append(
                {
                    "model_type": model_type,
                    "model_name": model_name,
                    "model_provider": model_provider,
                    "model_instance": model_provider,
                    "enable": True,
                }
            )
        else:
            models.append(
                {
                    "model_type": model_type,
                    "model_name": "",
                    "model_provider": "",
                    "model_instance": "",
                    "enable": False,
                }
            )
    return _wrap_ok({"models": models})


@router.patch("/models/default")
async def set_default_model(request: Request):
    """把新版 PATCH /api/v1/models/default 转成旧版 /api/v1/users/me/models。"""
    body = await request.json()
    model_type = body.get("model_type")
    field = MODEL_TYPE_TO_FIELD.get(model_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"unknown model_type {model_type}")

    # 拉取当前租户配置
    resp = _ragflow_get("/api/v1/users/me/models", request)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    tenant = resp.json().get("data", {})

    provider = body.get("model_provider") or ""
    name = body.get("model_name") or ""
    value = f"{name}@{provider}" if name and provider else ""

    update = {
        "tenant_id": tenant.get("tenant_id", ""),
        "llm_id": tenant.get("llm_id", ""),
        "embd_id": tenant.get("embd_id", ""),
        "asr_id": tenant.get("asr_id", ""),
        "img2txt_id": tenant.get("img2txt_id", ""),
        "rerank_id": tenant.get("rerank_id", ""),
        "tts_id": tenant.get("tts_id", ""),
    }
    update[field] = value

    resp = _ragflow_patch("/api/v1/users/me/models", request, update)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()
