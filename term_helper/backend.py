"""OpenAI-compatible client for the local llama-server. No SDK, no cloud."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from term_helper import config
from term_helper.contract import GBNF, SCHEMA


class BackendError(RuntimeError):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def _payload(role, messages: list[dict], variant: str, stream: bool,
             max_tokens: int) -> dict:
    payload = {
        "model": role.model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if variant == "schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "term_helper", "schema": SCHEMA, "strict": True},
        }
    elif variant == "grammar":
        payload["grammar"] = GBNF
    return payload


def _request(role, messages, variant, stream, on_token, timeout, max_tokens) -> str:
    url = role.base_url.rstrip("/") + "/v1/chat/completions"
    data = json.dumps(_payload(role, messages, variant, stream, max_tokens)).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=_headers())
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        raise BackendError(f"HTTP {exc.code} from {url}: {body}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise BackendError(f"cannot reach {url}: {exc.reason}") from exc

    if not stream:
        try:
            obj = json.loads(response.read().decode("utf-8", "replace"))
            content = obj["choices"][0]["message"].get("content")
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise BackendError(f"malformed response from {url}: {exc}") from exc
        return content or ""

    chunks: list[str] = []
    for raw in response:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        body = line[5:].strip()
        if body == "[DONE]":
            break
        try:
            obj = json.loads(body)
        except json.JSONDecodeError:
            continue
        delta = (obj.get("choices") or [{}])[0].get("delta", {}).get("content") or ""
        if delta:
            chunks.append(delta)
            if on_token:
                on_token("".join(chunks))
    return "".join(chunks)


def chat(role, messages, on_token=None, timeout: int = 300, max_tokens: int = 1024) -> str:
    """Call the model, degrading gracefully if the server rejects the schema."""
    last: BackendError | None = None
    for variant, stream in (("schema", True), ("grammar", True), ("none", False)):
        try:
            return _request(role, messages, variant, stream, on_token, timeout, max_tokens)
        except BackendError as exc:
            last = exc
            if exc.code not in (400, 404, 422):
                raise
    assert last is not None
    raise last


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = config.api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def health(base_url: str, timeout: float = 2.0) -> bool:
    url = base_url.rstrip("/") + "/health"
    try:
        request = urllib.request.Request(url, headers=_headers())
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception:
        return False
