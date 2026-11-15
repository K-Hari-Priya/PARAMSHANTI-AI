"""
llm.py - one function, chat(system, user), that asks a large language model.

Two kinds of provider are supported, chosen by LLM_PROVIDER in .env:
   gemini  -> Google Gemini API (free key from Google AI Studio)
   openai  -> any "OpenAI-compatible" API such as Groq (set LLM_BASE_URL too)

Model names change often. If LLM_MODEL is not set in .env we use the model that
step5_test_llm.py found working, or the faster one step6_speed_test.py picked
(both save their choice in data\\llm_model.txt), else a default.
"""
import re
import time

import requests

import config

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
MODEL_FILE = config.DATA / "llm_model.txt"
DEFAULTS = {"gemini": "gemini-3.8-flash", "openai": "openai/gpt-oss-120b"}


class LLMError(Exception):
    """Raised when the LLM provider returns an error, with a readable explanation."""


def _saved() -> tuple[str, str]:
    """(model, thinking setting) chosen by step 5 or step 6, e.g. 'gemini-x-flash-lite|level:minimal'."""
    if MODEL_FILE.exists():
        model, _, thinking = MODEL_FILE.read_text(encoding="utf-8").strip().partition("|")
        return model.strip(), thinking.strip()
    return "", ""


def current_model() -> str:
    if config.LLM_MODEL:                                   # 1. what you wrote in .env
        return config.LLM_MODEL
    return _saved()[0] or DEFAULTS.get(config.LLM_PROVIDER, DEFAULTS["gemini"])   # 2. saved, 3. default


def current_thinking() -> str:
    """How much the model should 'think' before answering ('' = the model's own default)."""
    return "" if config.LLM_MODEL else _saved()[1]


def thinking_config(setting: str) -> dict:
    """Gemini models can think before they answer. Less thinking = a faster reply.
    'level:minimal' or 'level:low' suits newer models, 'budget:0' suits older ones."""
    kind, _, value = setting.partition(":")
    if kind == "level" and value:
        return {"thinkingConfig": {"thinkingLevel": value}}
    if kind == "budget" and value.isdigit():
        return {"thinkingConfig": {"thinkingBudget": int(value)}}
    return {}


def _explain(resp: requests.Response) -> str:
    try:
        err = resp.json().get("error", {})
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
    except Exception:
        msg = resp.text[:300]
    hint = {
        400: "Often a wrong model name or a bad key.",
        401: "The LLM key is wrong. Check LLM_API_KEY in .env.",
        403: "The LLM key is not allowed to do this. Check LLM_API_KEY in .env.",
        404: "This model name does not exist for your key. Run: python step5_test_llm.py",
        429: "Free-tier limit reached. Wait one minute and try again.",
    }.get(resp.status_code, "")
    return f"HTTP {resp.status_code}: {msg[:300]} {hint}".strip()


def _post(url: str, headers: dict, body: dict, timeout: int = 45, attempts: int = 2) -> dict:
    """POST, with an automatic retry when the provider is busy or slow."""
    problem = "No reply from the LLM provider."
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as e:      # no internet, or no reply in time
            problem = (f"The LLM did not reply in time ({e.__class__.__name__}). "
                       f"Check the internet connection and ask again.")
            continue
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 503) and attempt < attempts:
            time.sleep(8)
            continue
        raise LLMError(_explain(resp))
    raise LLMError(problem)


def chat(system: str, user: str, model: str | None = None, temperature: float = 0.2,
         thinking: str | None = None, timeout: int = 45, attempts: int = 2) -> str:
    """Send a system instruction plus a user message; return the model's text."""
    key = config.need(config.LLM_API_KEY, "LLM_API_KEY")
    if thinking is None:                 # use the saved setting only with the saved model
        thinking = current_thinking() if model in (None, current_model()) else ""
    model = model or current_model()

    if config.LLM_PROVIDER == "openai":
        data = _post(
            f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            {"model": model, "temperature": temperature,
             "messages": [{"role": "system", "content": system},
                          {"role": "user", "content": user}]},
            timeout, attempts,
        )
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"Unexpected reply: {str(data)[:300]}")
    else:  # gemini
        data = _post(
            f"{GEMINI_URL}/models/{model}:generateContent",
            {"x-goog-api-key": key, "Content-Type": "application/json"},
            {"system_instruction": {"parts": [{"text": system}]},
             "contents": [{"role": "user", "parts": [{"text": user}]}],
             "generationConfig": {"temperature": temperature, **thinking_config(thinking)}},
            timeout, attempts,
        )
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMError(f"The model returned no answer: {str(data)[:300]}")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise LLMError(f"Empty answer (finishReason={candidates[0].get('finishReason')}).")
    return text.strip()


def list_models() -> list[str]:
    """Names of the chat models your key can use."""
    key = config.need(config.LLM_API_KEY, "LLM_API_KEY")
    if config.LLM_PROVIDER == "openai":
        resp = requests.get(f"{config.LLM_BASE_URL.rstrip('/')}/models",
                            headers={"Authorization": f"Bearer {key}"}, timeout=60)
        if resp.status_code != 200:
            raise LLMError(_explain(resp))
        return sorted(m.get("id", "") for m in resp.json().get("data", []))
    resp = requests.get(f"{GEMINI_URL}/models", params={"pageSize": 1000},
                        headers={"x-goog-api-key": key}, timeout=60)
    if resp.status_code != 200:
        raise LLMError(_explain(resp))
    names = []
    for m in resp.json().get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            names.append(m.get("name", "").removeprefix("models/"))
    return sorted(names)


def best_gemini_candidates(names: list[str]) -> list[str]:
    """Order Gemini text models: newest 'flash' first, previews and 'lite' later."""
    skip = ("image", "tts", "audio", "live", "embed", "robotics", "computer", "aqa", "learnlm", "omni")
    scored = []
    for name in names:
        n = name.lower()
        if not n.startswith("gemini") or "flash" not in n or any(s in n for s in skip):
            continue
        nums = [int(x) for x in re.findall(r"\d+", n.split("flash")[0])[:2]] or [0]
        version = nums[0] * 100 + (nums[1] if len(nums) > 1 else 0)
        penalty = (2 if ("preview" in n or "exp" in n) else 0) + (1 if "lite" in n else 0)
        scored.append((penalty, -version, len(n), name))
    return [name for *_, name in sorted(scored)]
