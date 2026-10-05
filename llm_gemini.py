#!/usr/bin/env python3
"""Gemini APIクライアント（video-studio用の薄いラッパー）

~/.secrets/gemini.env を共有参照する（video-studio独自の.envは作らない）。
super-data-archiver/archivers/llm.py の _gemini_chat() と同じ構成（APIキー方式、無料枠内）。
"""
import os
from pathlib import Path
from typing import Optional

DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
GEMINI_FALLBACK_MODELS = ["gemini-3.1-flash-lite", "gemini-2.5-flash"]


def load_gemini_env() -> None:
    """~/.secrets/gemini.env を読み込みos.environにセット（既存値は上書きしない）"""
    if os.environ.get("GEMINI_API_KEY"):
        return
    env_path = Path.home() / ".secrets" / "gemini.env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def gemini_available() -> bool:
    load_gemini_env()
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("GEMINI_API_KEY"))


def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.3,
    response_json_schema: Optional[dict] = None,
) -> Optional[str]:
    """Gemini呼び出し。モデル候補を順に試し、全滅でNone（呼び出し元でOllamaにフォールバック）"""
    load_gemini_env()
    if not os.environ.get("GEMINI_API_KEY"):
        return None
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    contents = []
    system_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=content)]))

    config_kwargs = {"temperature": temperature}
    if system_parts:
        config_kwargs["system_instruction"] = "\n\n".join(system_parts)
    if response_json_schema:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = response_json_schema
    config = types.GenerateContentConfig(**config_kwargs)

    candidates = [model or DEFAULT_GEMINI_MODEL]
    candidates += [m for m in GEMINI_FALLBACK_MODELS if m not in candidates]

    for candidate in candidates:
        try:
            resp = client.models.generate_content(model=candidate, contents=contents, config=config)
            if resp.text:
                return resp.text
        except Exception as e:
            print(f"  Warning: Gemini {candidate} 失敗: {e}")
    return None
