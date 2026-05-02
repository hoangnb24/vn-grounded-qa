"""Optional Google Gemini JSON completion adapter."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError


T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    def __init__(self, failure_type: str, message: str, metadata: dict[str, object] | None = None):
        super().__init__(message)
        self.failure_type = failure_type
        self.metadata = metadata or {}


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "google"
    model: str = "gemini-2.5-flash"
    timeout_ms: int = 30000
    retry_attempts: int = 2
    use_vertex: bool = False
    project: str = ""
    location: str = ""


def load_config(model: str | None = None) -> LLMConfig:
    return LLMConfig(
        provider=os.environ.get("VN_GROUNDED_QA_LLM_PROVIDER", "google"),
        model=model or os.environ.get("VN_GROUNDED_QA_LLM_MODEL", "gemini-2.5-flash"),
        timeout_ms=int(os.environ.get("VN_GROUNDED_QA_LLM_TIMEOUT_MS", "30000")),
        retry_attempts=max(0, int(os.environ.get("VN_GROUNDED_QA_LLM_RETRY_ATTEMPTS", "2"))),
        use_vertex=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {"1", "true", "yes"},
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", ""),
    )


def complete_json(prompt: str, schema: type[T], model: str | None = None) -> T:
    config = load_config(model)
    if config.provider != "google":
        raise LLMError("llm_dependency_missing", f"Unsupported LLM provider: {config.provider}", metadata_from_config(config, schema))
    if not config.use_vertex and not os.environ.get("GEMINI_API_KEY"):
        raise LLMError("llm_auth_missing", "GEMINI_API_KEY is required for Gemini Developer API.", metadata_from_config(config, schema))
    if config.use_vertex and (not config.project or not config.location):
        raise LLMError("llm_auth_missing", "GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION are required for Vertex AI.", metadata_from_config(config, schema))
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise LLMError("llm_dependency_missing", "Install LLM dependencies with: pip install -e '.[llm]'", metadata_from_config(config, schema)) from exc

    client_kwargs: dict[str, object] = {}
    if config.use_vertex:
        client_kwargs.update(vertexai=True, project=config.project, location=config.location)
    else:
        client_kwargs["api_key"] = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(**client_kwargs)
    http_options = types.HttpOptions(timeout=config.timeout_ms)
    request_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=schema.model_json_schema(),
        http_options=http_options,
    )
    attempts = config.retry_attempts + 1
    last_error: Exception | None = None
    started = time.perf_counter()
    for attempt in range(attempts):
        try:
            response = client.models.generate_content(
                model=config.model,
                contents=prompt,
                config=request_config,
            )
            text = response.text or ""
            try:
                return schema.model_validate_json(text)
            except ValidationError as exc:
                raise LLMError("llm_schema_validation_failed", str(exc), metadata_from_config(config, schema, started, attempt + 1)) from exc
            except ValueError as exc:
                raise LLMError("llm_invalid_json", str(exc), metadata_from_config(config, schema, started, attempt + 1)) from exc
        except LLMError:
            raise
        except Exception as exc:  # provider exceptions vary by installed SDK version
            last_error = exc
            if not is_transient_provider_error(exc) or attempt == attempts - 1:
                failure_type = "llm_timeout" if "timeout" in str(exc).lower() else "llm_retry_exhausted"
                raise LLMError(failure_type, str(exc), metadata_from_config(config, schema, started, attempt + 1)) from exc
    raise LLMError("llm_retry_exhausted", str(last_error or "unknown provider error"), metadata_from_config(config, schema, started, attempts))


def is_transient_provider_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(code in text for code in ["408", "429", "500", "502", "503", "504", "timeout", "temporarily"])


def metadata_from_config(config: LLMConfig, schema: type[BaseModel], started: float | None = None, attempts: int = 0) -> dict[str, object]:
    metadata: dict[str, object] = {
        "provider": config.provider,
        "model": config.model,
        "timeout_ms": config.timeout_ms,
        "retry_attempts": config.retry_attempts,
        "schema": schema.__name__,
        "use_vertex": config.use_vertex,
        "attempts": attempts,
    }
    if started is not None:
        metadata["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return metadata

