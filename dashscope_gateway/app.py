"""
DashScope 网关：接收 Anthropic Messages API 格式请求，转发到阿里云 DashScope（通义），
并将响应转回 Anthropic 格式，供 NanoClaw 容器内 Claude Agent SDK 使用。

用法：
  - 本机启动: uvicorn app:app --host 0.0.0.0 --port 8005
  - NanoClaw .env 中设置:
      ANTHROPIC_BASE_URL=http://host.docker.internal:8005
      ANTHROPIC_API_KEY=<你的 DashScope API Key>
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Union

import httpx
from fastapi import FastAPI, Request, Header
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

# ------------------------- 配置 -------------------------
DASHSCOPE_BASE = os.environ.get(
    "DASHSCOPE_BASE",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
# Anthropic 的 model 名会原样传过来，映射到 DashScope 模型名
DEFAULT_DASHSCOPE_MODEL = os.environ.get("DASHSCOPE_MODEL", "qwen-plus")
MODEL_MAP = {
    "claude-3-5-sonnet-20241022": "qwen-plus",
    "claude-3-opus-20240229": "qwen-max",
    "claude-3-sonnet-20240229": "qwen-plus",
    "claude-3-haiku-20240307": "qwen-turbo",
}
# 从 x-api-key 取 DashScope API Key（NanoClaw credential proxy 会注入）
AUTH_HEADER_NAME = "x-api-key"

app = FastAPI(title="DashScope Gateway for NanoClaw", version="0.1.0")


# ------------------------- 请求/响应模型（Anthropic 兼容） -------------------------
class AnthropicContentBlock(BaseModel):
    type: str = "text"
    text: str = ""


class AnthropicMessage(BaseModel):
    role: str
    content: Union[str, List[AnthropicContentBlock]]


class AnthropicMessagesRequest(BaseModel):
    model: str = "claude-3-5-sonnet-20241022"
    max_tokens: int = 4096
    messages: List[Dict[str, Any]]
    system: Optional[str] = None
    stream: bool = False
    temperature: Optional[float] = None


# ------------------------- 工具函数 -------------------------
def content_to_string(content: Union[str, list]) -> str:
    """将 Anthropic 的 content（字符串或 block 列表）转为单段文本。"""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "\n".join(parts).strip()
    return ""


def anthropic_messages_to_openai(
    messages: List[dict],
    system: Optional[str],
) -> List[Dict[str, str]]:
    """Anthropic messages -> OpenAI/DashScope messages（role + content 字符串）。"""
    out: List[Dict[str, str]] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        role = m.get("role", "user")
        content = content_to_string(m.get("content", ""))
        if role in ("user", "assistant", "system") and content:
            out.append({"role": role, "content": content})
    return out


def map_to_dashscope_model(anthropic_model: str) -> str:
    """Anthropic 模型名 -> DashScope 模型名。"""
    return MODEL_MAP.get(
        anthropic_model,
        DEFAULT_DASHSCOPE_MODEL,
    )


async def call_dashscope(
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 4096,
    stream: bool = False,
    temperature: Optional[float] = None,
) -> Any:
    """调用 DashScope 兼容接口。"""
    url = f"{DASHSCOPE_BASE.rstrip('/')}/chat/completions"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        if stream:
            return await stream_dashscope(client, url, headers, payload)
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def stream_dashscope(client: httpx.AsyncClient, url: str, headers: dict, payload: dict):
    """流式调用 DashScope，返回 SSE 流（需在视图中包装为 StreamingResponse）。"""
    payload["stream"] = True
    async with client.stream("POST", url, json=payload, headers=headers) as r:
        r.raise_for_status()
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                data = line[6:].strip()
                if data == "[DONE]":
                    yield f"data: [DONE]\n\n"
                    break
                try:
                    obj = json.loads(data)
                    yield f"data: {data}\n\n"
                except json.JSONDecodeError:
                    pass


def openai_choice_to_anthropic_content(choice: dict) -> List[dict]:
    """OpenAI choices[0].message.content -> Anthropic content blocks。"""
    msg = choice.get("message", {})
    content = msg.get("content")
    if content is None:
        return [{"type": "text", "text": ""}]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        texts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                texts.append(c.get("text", ""))
        return [{"type": "text", "text": "\n".join(texts)}] if texts else [{"type": "text", "text": ""}]
    return [{"type": "text", "text": str(content)}]


def openai_to_anthropic_response(openai_resp: dict, anthropic_model: str) -> dict:
    """将 DashScope(OpenAI 兼容) 的响应转为 Anthropic Messages API 响应格式。"""
    choices = openai_resp.get("choices", [])
    if not choices:
        return {
            "id": "dashscope-gateway-1",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": ""}],
            "model": anthropic_model,
            "stop_reason": "end_turn",
        }
    choice = choices[0]
    content = openai_choice_to_anthropic_content(choice)
    return {
        "id": openai_resp.get("id", "dashscope-gateway-1"),
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": anthropic_model,
        "stop_reason": choice.get("finish_reason", "end_turn"),
    }


def stream_line_to_anthropic_sse(line: str, anthropic_model: str) -> Optional[str]:
    """将 DashScope SSE 的一行（data: {...}）转为 Anthropic 风格 SSE。"""
    if not line.startswith("data: "):
        return None
    raw = line[6:].strip()
    if raw == "[DONE]":
        return None  # 由 sse_stream 统一发 message_stop
    try:
        obj = json.loads(raw)
        choices = obj.get("choices", [])
        if not choices:
            return None
        delta = choices[0].get("delta", {})
        content = delta.get("content")
        if content is None or content == "":
            return None
        block = {"type": "text_delta", "text": content}
        out = {"type": "content_block_delta", "index": 0, "delta": block}
        return f"data: {json.dumps(out)}\n\n"
    except (json.JSONDecodeError, KeyError):
        return None


def anthropic_stream_start(anthropic_model: str) -> str:
    """Anthropic 流式开头：message_start + content_block_start。"""
    msg_start = {
        "type": "message_start",
        "message": {
            "id": "dashscope-msg-1",
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": anthropic_model,
        },
    }
    block_start = {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}
    return f"data: {json.dumps(msg_start)}\n\ndata: {json.dumps(block_start)}\n\n"


def anthropic_stream_stop(anthropic_model: str) -> str:
    """Anthropic 流式结尾：content_block_stop + message_delta + message_stop。"""
    block_stop = {"type": "content_block_stop", "index": 0}
    msg_delta = {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 0}}
    msg_stop = {"type": "message_stop"}
    return f"data: {json.dumps(block_stop)}\n\ndata: {json.dumps(msg_delta)}\n\ndata: {json.dumps(msg_stop)}\n\n"


# ------------------------- 路由 -------------------------
@app.post("/v1/messages")
async def anthropic_messages(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    """接收 Anthropic 格式 POST /v1/messages，转发到 DashScope 并返回 Anthropic 格式。"""
    api_key = x_api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        return JSONResponse(
            status_code=401,
            content={"error": "missing x-api-key or DASHSCOPE_API_KEY"},
        )
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    stream = body.get("stream", False)
    model = body.get("model", "claude-3-5-sonnet-20241022")
    max_tokens = body.get("max_tokens", 4096)
    system = body.get("system")
    messages = body.get("messages", [])
    temperature = body.get("temperature")

    dashscope_model = map_to_dashscope_model(model)
    openai_messages = anthropic_messages_to_openai(messages, system)
    if not openai_messages:
        return JSONResponse(status_code=400, content={"error": "messages required"})

    if stream:
        async def sse_stream():
            yield anthropic_stream_start(model)
            url = f"{DASHSCOPE_BASE.rstrip('/')}/chat/completions"
            payload = {
                "model": dashscope_model,
                "messages": openai_messages,
                "max_tokens": max_tokens,
                "stream": True,
            }
            if temperature is not None:
                payload["temperature"] = temperature
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if line.startswith("data: "):
                            out = stream_line_to_anthropic_sse(line, model)
                            if out:
                                yield out
            yield anthropic_stream_stop(model)

        return StreamingResponse(
            sse_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    try:
        openai_resp = await call_dashscope(
            api_key=api_key,
            model=dashscope_model,
            messages=openai_messages,
            max_tokens=max_tokens,
            stream=False,
            temperature=temperature,
        )
    except httpx.HTTPStatusError as e:
        return JSONResponse(
            status_code=e.response.status_code,
            content={"error": e.response.text or str(e)},
        )
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})

    anthropic_resp = openai_to_anthropic_response(openai_resp, model)
    return JSONResponse(content=anthropic_resp)


@app.get("/health")
async def health():
    return {"status": "ok", "gateway": "dashscope"}
