#!/usr/bin/env python3
"""fnOS control plane for trim.hermes.

This service is the outer process managed by fnOS. It serves the packaged Web UI,
manages Hermes gateway/api_server as a child process, persists bootstrap config,
and exposes JSON APIs for setup, runtime control, logs, and basic chat.

Canonical adapter source. Sync into app-center via scripts/sync_app_center.sh.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import secrets
import select
import shlex
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

APP_NAME = "trim.hermes"
DEFAULT_CONTROL_PORT = 18123
DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 19119
DEFAULT_API_SERVER_HOST = "127.0.0.1"
DEFAULT_API_SERVER_PORT = 18642
DEFAULT_APPROVAL_MODE = "manual"
DEFAULT_LOG_TAIL_LINES = 120
START_TIMEOUT_SECONDS = 12
API_SERVER_KEY_BYTES = 32

PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openrouter": {
        "label": "OpenRouter",
        "api_key_env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
    },
    "openai": {
        "label": "OpenAI",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
    },
    "anthropic": {
        "label": "Anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": "",
    },
    "zai": {
        "label": "GLM / Z.ai",
        "api_key_env": "GLM_API_KEY",
        "base_url": "https://api.z.ai/api/paas/v4",
    },
    "kimi-coding": {
        "label": "Kimi / Moonshot",
        "api_key_env": "KIMI_API_KEY",
        "base_url": "https://api.moonshot.ai/v1",
    },
    "deepseek": {
        "label": "DeepSeek",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
    },
    "ollama": {
        "label": "Ollama",
        "api_key_env": "OLLAMA_API_KEY",
        "base_url": "http://127.0.0.1:11434/v1",
    },
    "lmstudio": {
        "label": "LM Studio",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "http://127.0.0.1:1234/v1",
    },
    "custom": {
        "label": "Custom OpenAI-Compatible",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "",
    },
}

SUPPORTED_CHAT_PLATFORMS = ("telegram", "discord", "feishu", "dingtalk")

CHAT_PLATFORM_SCHEMAS: dict[str, dict[str, Any]] = {
    "telegram": {
        "id": "telegram",
        "label": "Telegram",
        "description": "使用 Telegram Bot Token 接入私聊、群聊与 topic。",
        "fields": [
            {"id": "enabled", "label": "启用平台", "type": "boolean"},
            {"id": "bot_token", "label": "Bot Token", "type": "secret", "placeholder": "留空则保持当前 token"},
            {"id": "home_chat_id", "label": "Home Chat ID", "type": "text", "placeholder": "例如 123456789 或 -100xxxxxxxxxx"},
            {"id": "home_channel_name", "label": "Home 名称", "type": "text", "placeholder": "默认 Home"},
            {
                "id": "reply_to_mode",
                "label": "回复线程模式",
                "type": "select",
                "options": [
                    {"value": "off", "label": "关闭"},
                    {"value": "first", "label": "仅首条回复"},
                    {"value": "all", "label": "所有分片都回复"},
                ],
            },
            {"id": "require_mention", "label": "必须 @ 机器人", "type": "boolean"},
            {"id": "allow_all_users", "label": "允许所有用户", "type": "boolean"},
            {"id": "allowed_users", "label": "允许用户列表", "type": "textarea", "placeholder": "每行一个用户 ID，或逗号分隔"},
            {"id": "free_response_chats", "label": "免 @ 聊天列表", "type": "textarea", "placeholder": "每行一个 chat id"},
        ],
    },
    "discord": {
        "id": "discord",
        "label": "Discord",
        "description": "使用 Discord Bot Token 接入服务器频道、线程与私聊。",
        "fields": [
            {"id": "enabled", "label": "启用平台", "type": "boolean"},
            {"id": "bot_token", "label": "Bot Token", "type": "secret", "placeholder": "留空则保持当前 token"},
            {"id": "home_chat_id", "label": "Home Channel ID", "type": "text", "placeholder": "例如 123456789012345678"},
            {"id": "home_channel_name", "label": "Home 名称", "type": "text", "placeholder": "默认 Home"},
            {
                "id": "reply_to_mode",
                "label": "回复线程模式",
                "type": "select",
                "options": [
                    {"value": "off", "label": "关闭"},
                    {"value": "first", "label": "仅首条回复"},
                    {"value": "all", "label": "所有分片都回复"},
                ],
            },
            {"id": "require_mention", "label": "必须 @ 机器人", "type": "boolean"},
            {"id": "allow_all_users", "label": "允许所有用户", "type": "boolean"},
            {"id": "allowed_users", "label": "允许用户列表", "type": "textarea", "placeholder": "每行一个用户 ID，或逗号分隔"},
            {"id": "allowed_channels", "label": "允许频道列表", "type": "textarea", "placeholder": "每行一个 channel id"},
            {"id": "ignored_channels", "label": "忽略频道列表", "type": "textarea", "placeholder": "每行一个 channel id"},
            {"id": "auto_thread", "label": "自动创建线程", "type": "boolean"},
        ],
    },
    "feishu": {
        "id": "feishu",
        "label": "Feishu / Lark",
        "description": "使用 App ID / App Secret 接入飞书或 Lark。",
        "fields": [
            {"id": "enabled", "label": "启用平台", "type": "boolean"},
            {"id": "app_id", "label": "App ID", "type": "secret", "placeholder": "留空则保持当前 App ID"},
            {"id": "app_secret", "label": "App Secret", "type": "secret", "placeholder": "留空则保持当前 App Secret"},
            {"id": "home_chat_id", "label": "Home Chat ID", "type": "text", "placeholder": "例如 oc_xxxxx"},
            {"id": "home_channel_name", "label": "Home 名称", "type": "text", "placeholder": "默认 Home"},
            {
                "id": "domain",
                "label": "服务域",
                "type": "select",
                "options": [
                    {"value": "feishu", "label": "Feishu"},
                    {"value": "lark", "label": "Lark"},
                ],
            },
            {
                "id": "connection_mode",
                "label": "连接模式",
                "type": "select",
                "options": [
                    {"value": "websocket", "label": "WebSocket"},
                    {"value": "webhook", "label": "Webhook"},
                ],
            },
            {"id": "encrypt_key", "label": "Encrypt Key", "type": "secret", "placeholder": "可留空"},
            {"id": "verification_token", "label": "Verification Token", "type": "secret", "placeholder": "可留空"},
            {"id": "allow_all_users", "label": "允许所有用户", "type": "boolean"},
            {"id": "allowed_users", "label": "允许用户列表", "type": "textarea", "placeholder": "每行一个 open_id 或 user_id"},
        ],
    },
    "dingtalk": {
        "id": "dingtalk",
        "label": "DingTalk",
        "description": "使用客户端 ID / Secret 通过 Stream Mode 接入钉钉。",
        "fields": [
            {"id": "enabled", "label": "启用平台", "type": "boolean"},
            {"id": "client_id", "label": "Client ID", "type": "secret", "placeholder": "留空则保持当前 Client ID"},
            {"id": "client_secret", "label": "Client Secret", "type": "secret", "placeholder": "留空则保持当前 Client Secret"},
            {"id": "home_chat_id", "label": "Home Chat ID", "type": "text", "placeholder": "可留空"},
            {"id": "home_channel_name", "label": "Home 名称", "type": "text", "placeholder": "默认 Home"},
            {"id": "allow_all_users", "label": "允许所有用户", "type": "boolean"},
            {"id": "allowed_users", "label": "允许用户列表", "type": "textarea", "placeholder": "每行一个用户 ID"},
        ],
    },
}


@dataclass(frozen=True)
class RuntimePaths:
    app_root: Path
    data_root: Path
    web_root: Path
    home_root: Path
    hermes_home: Path
    workspace_root: Path
    state_root: Path
    uploads_root: Path
    logs_root: Path
    env_file: Path
    config_file: Path
    gateway_state_file: Path
    dashboard_state_file: Path
    control_log_file: Path
    gateway_log_file: Path
    dashboard_log_file: Path

    @classmethod
    def from_roots(cls, app_root: Path, data_root: Path) -> "RuntimePaths":
        hermes_home = data_root / "hermes"
        return cls(
            app_root=app_root,
            data_root=data_root,
            web_root=app_root / "web",
            home_root=data_root / "home",
            hermes_home=hermes_home,
            workspace_root=data_root / "workspace",
            state_root=data_root / "state",
            uploads_root=data_root / "uploads",
            logs_root=hermes_home / "logs",
            env_file=hermes_home / ".env",
            config_file=hermes_home / "config.yaml",
            gateway_state_file=data_root / "state" / "gateway-process.json",
            dashboard_state_file=data_root / "state" / "dashboard-process.json",
            control_log_file=hermes_home / "logs" / "control-plane.log",
            gateway_log_file=hermes_home / "logs" / "gateway.log",
            dashboard_log_file=hermes_home / "logs" / "dashboard.log",
        )


def ensure_runtime_layout(paths: RuntimePaths) -> None:
    for path in (
        paths.data_root,
        paths.home_root,
        paths.hermes_home,
        paths.workspace_root,
        paths.state_root,
        paths.uploads_root,
        paths.logs_root,
    ):
        path.mkdir(parents=True, exist_ok=True)

    if not paths.env_file.exists():
        write_env_file(
            paths.env_file,
            {
                "API_SERVER_ENABLED": "true",
                "API_SERVER_HOST": DEFAULT_API_SERVER_HOST,
                "API_SERVER_PORT": str(DEFAULT_API_SERVER_PORT),
                "API_SERVER_CORS_ORIGINS": "",
            },
        )

    if not paths.config_file.exists():
        write_config_file(
            paths.config_file,
            build_config_document(
                provider="openrouter",
                model="",
                base_url=PROVIDER_PRESETS["openrouter"]["base_url"],
                approvals_mode=DEFAULT_APPROVAL_MODE,
                workspace_root=paths.workspace_root,
            ),
        )

    workspace_readme = paths.workspace_root / "README.md"
    if not workspace_readme.exists():
        workspace_readme.write_text(
            "# trim.hermes workspace\n\n"
            "This directory is reserved for Hermes task workspaces and fnOS-approved file operations.\n",
            encoding="utf-8",
        )


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = [
        "# Managed by trim.hermes control plane.",
        "# User-added keys are preserved when possible; provider secrets can be updated from the Web UI.",
        "",
    ]
    for key in sorted(values):
        lines.append(f"{key}={values[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_config_file(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, None
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw), raw
    except json.JSONDecodeError:
        try:
            import yaml

            payload = yaml.safe_load(raw)
            if isinstance(payload, dict):
                return payload, raw
        except Exception:  # noqa: BLE001
            pass
        return None, raw


def write_config_file(path: Path, config: dict[str, Any]) -> None:
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_config_document(
    provider: str,
    model: str,
    base_url: str,
    approvals_mode: str,
    workspace_root: Path,
) -> dict[str, Any]:
    model_block: dict[str, Any] = {
        "default": model.strip(),
        "provider": provider.strip() or "auto",
    }


def env_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in ("true", "1", "yes", "on")


def normalize_csv_text(value: str | list[Any] | None) -> str:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "\n".join(items)
    if not value:
        return ""

    pieces: list[str] = []
    for chunk in str(value).replace("\r", "\n").split("\n"):
        for item in chunk.split(","):
            normalized = item.strip()
            if normalized:
                pieces.append(normalized)
    return "\n".join(pieces)


def csv_text_to_list(value: str | None) -> list[str]:
    if not value:
        return []
    items: list[str] = []
    for chunk in str(value).replace("\r", "\n").split("\n"):
        for item in chunk.split(","):
            normalized = item.strip()
            if normalized:
                items.append(normalized)
    return items


def looks_like_upstream_chat_error(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return False
    if normalized.startswith("Error code: "):
        return True
    lowered = normalized.lower()
    return any(
        marker in lowered
        for marker in (
            "missing authentication header",
            "invalid api key",
            "api key was rejected",
            "non-retryable client error",
        )
    )


def normalize_base_url(provider: str, base_url: str) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if normalized:
        return normalized
    if provider == "anthropic":
        return "https://api.anthropic.com"
    return PROVIDER_PRESETS.get(provider, {}).get("base_url", "").strip().rstrip("/")


def list_to_csv_env(value: str | None) -> str:
    return ",".join(csv_text_to_list(value))


def set_nested_value(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cursor = target
    for part in path[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[part] = next_value
        cursor = next_value
    cursor[path[-1]] = value


def remove_nested_value(target: dict[str, Any], path: tuple[str, ...]) -> None:
    if not path:
        return
    cursor = target
    parents: list[tuple[dict[str, Any], str]] = []
    for part in path[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            return
        parents.append((cursor, part))
        cursor = next_value
    cursor.pop(path[-1], None)
    for parent, key in reversed(parents):
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            parent.pop(key, None)
        else:
            break
    if base_url.strip():
        model_block["base_url"] = base_url.strip()

    return {
        "_managed_by": APP_NAME,
        "_schema_version": 1,
        "model": model_block,
        "toolsets": ["hermes-cli"],
        "platform_toolsets": {
            "api_server": ["hermes-api-server"],
        },
        "approvals": {
            "mode": approvals_mode.strip() or DEFAULT_APPROVAL_MODE,
        },
        "terminal": {
            "backend": "local",
            "cwd": str(workspace_root),
            "persistent_shell": True,
        },
    }


def tail_lines(path: Path, line_count: int = DEFAULT_LOG_TAIL_LINES) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-line_count:]


def read_pid_state(pid: int | None) -> str | None:
    if not pid or pid <= 0:
        return None

    proc_stat = Path(f"/proc/{pid}/stat")
    try:
        raw = proc_stat.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None

    if ") " not in raw:
        return None
    remainder = raw.split(") ", 1)[1]
    if not remainder:
        return None
    return remainder[0]


def reap_child_process(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        waited_pid, _status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return False
    except OSError:
        return False
    return waited_pid == pid


def is_pid_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    state = read_pid_state(pid)
    if state == "Z":
        reap_child_process(pid)
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_gateway_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_gateway_state(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def remove_gateway_state(path: Path) -> None:
    if path.exists():
        path.unlink()


def redact_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 6) + value[-3:]


def generate_api_server_key() -> str:
    return secrets.token_hex(API_SERVER_KEY_BYTES)


def http_json_request(
    url: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 5.0,
) -> tuple[int, dict[str, Any]]:
    data = None
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=data,
        method=method.upper(),
        headers=request_headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            if payload:
                try:
                    return response.status, json.loads(payload)
                except json.JSONDecodeError:
                    return response.status, {"raw": payload}
            return response.status, {}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8") if exc.fp else ""
        if payload:
            try:
                return exc.code, json.loads(payload)
            except json.JSONDecodeError:
                return exc.code, {"error": payload}
        return exc.code, {"error": str(exc)}


def error_message_from_payload(payload: dict[str, Any] | None, default: str) -> str:
    if isinstance(payload, dict):
        error_value = payload.get("error")
        if isinstance(error_value, dict):
            for key in ("message", "detail", "error_description", "code"):
                value = error_value.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(error_value, str) and error_value.strip():
            return error_value.strip()
        for key in ("message", "detail", "error_description", "code"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return default


def normalize_model_catalog(response: Any, owned_by: str = "provider") -> list[dict[str, Any]]:
    if isinstance(response, dict):
        raw_items = response.get("data")
        if not isinstance(raw_items, list):
            raw_items = response.get("models")
        if not isinstance(raw_items, list):
            raw_items = []
    elif isinstance(response, list):
        raw_items = response
    else:
        raw_items = []

    seen: set[str] = set()
    models: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, str):
            model_id = item.strip()
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            models.append(
                {
                    "id": model_id,
                    "object": "model",
                    "owned_by": owned_by,
                }
            )
            continue

        if not isinstance(item, dict):
            continue

        model_id = str(item.get("id", "") or item.get("name", "") or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        normalized = dict(item)
        normalized["id"] = model_id
        normalized.setdefault("object", "model")
        normalized.setdefault("owned_by", owned_by)
        models.append(normalized)

    return models


class HermesControlContext:
    def __init__(
        self,
        paths: RuntimePaths,
        control_host: str,
        control_port: int,
        dashboard_host: str = DEFAULT_DASHBOARD_HOST,
        dashboard_port: int = DEFAULT_DASHBOARD_PORT,
    ) -> None:
        self.paths = paths
        self.control_host = control_host
        self.control_port = control_port
        self.dashboard_host = dashboard_host
        self.dashboard_port = dashboard_port
        self._lock = threading.Lock()
        ensure_runtime_layout(paths)

    def api_server_host(self) -> str:
        env_values = parse_env_file(self.paths.env_file)
        return env_values.get("API_SERVER_HOST", DEFAULT_API_SERVER_HOST)

    def api_server_port(self) -> int:
        env_values = parse_env_file(self.paths.env_file)
        raw = env_values.get("API_SERVER_PORT", str(DEFAULT_API_SERVER_PORT))
        try:
            return int(raw)
        except ValueError:
            return DEFAULT_API_SERVER_PORT

    def api_server_url(self) -> str:
        return f"http://{self.api_server_host()}:{self.api_server_port()}"

    def dashboard_base_url(self) -> str:
        return f"http://{self.dashboard_host}:{self.dashboard_port}"

    def api_server_key(self) -> str:
        env_values = parse_env_file(self.paths.env_file)
        return env_values.get("API_SERVER_KEY", "").strip()

    def ensure_api_server_key(self, env_values: dict[str, str] | None = None) -> str:
        managed_env = env_values if env_values is not None else parse_env_file(self.paths.env_file)
        api_server_key = managed_env.get("API_SERVER_KEY", "").strip()
        if api_server_key:
            return api_server_key

        api_server_key = generate_api_server_key()
        managed_env["API_SERVER_KEY"] = api_server_key
        if env_values is None:
            write_env_file(self.paths.env_file, managed_env)
        logging.info("generated local API_SERVER_KEY for %s", APP_NAME)
        return api_server_key

    def api_server_headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        api_server_key = self.api_server_key()
        if api_server_key:
            headers["Authorization"] = f"Bearer {api_server_key}"
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def runtime_site_packages_path(self) -> Path | None:
        lib_root = self.paths.app_root / "runtime" / "python" / "lib"
        if not lib_root.exists():
            return None
        for candidate in sorted(lib_root.glob("python*/site-packages"), reverse=True):
            if candidate.exists():
                return candidate
        return None

    def session_db_class(self) -> type[Any]:
        try:
            module = importlib.import_module("hermes_state")
            return module.SessionDB
        except ImportError:
            site_packages = self.runtime_site_packages_path()
            if site_packages and str(site_packages) not in sys.path:
                sys.path.insert(0, str(site_packages))
            module = importlib.import_module("hermes_state")
            return module.SessionDB

    def open_session_db(self) -> Any:
        session_db_class = self.session_db_class()
        return session_db_class(db_path=self.paths.hermes_home / "state.db")

    def load_managed_config_document(self) -> tuple[dict[str, Any], str | None]:
        config, raw = load_config_file(self.paths.config_file)
        document = dict(config) if isinstance(config, dict) else {}

        document["_managed_by"] = APP_NAME
        document["_schema_version"] = 1

        model_block = document.get("model")
        if not isinstance(model_block, dict):
            model_block = {}
            document["model"] = model_block

        toolsets = document.get("toolsets")
        if not isinstance(toolsets, list):
            toolsets = []
        if "hermes-cli" not in toolsets:
            toolsets.append("hermes-cli")
        document["toolsets"] = toolsets

        platform_toolsets = document.get("platform_toolsets")
        if not isinstance(platform_toolsets, dict):
            platform_toolsets = {}
        api_toolsets = platform_toolsets.get("api_server")
        if not isinstance(api_toolsets, list):
            api_toolsets = []
        if "hermes-api-server" not in api_toolsets:
            api_toolsets.append("hermes-api-server")
        platform_toolsets["api_server"] = api_toolsets
        document["platform_toolsets"] = platform_toolsets

        approvals = document.get("approvals")
        if not isinstance(approvals, dict):
            approvals = {}
        approvals.setdefault("mode", DEFAULT_APPROVAL_MODE)
        document["approvals"] = approvals

        terminal = document.get("terminal")
        if not isinstance(terminal, dict):
            terminal = {}
        terminal["backend"] = "local"
        terminal["cwd"] = str(self.paths.workspace_root)
        terminal["persistent_shell"] = True
        document["terminal"] = terminal

        platforms = document.get("platforms")
        if not isinstance(platforms, dict):
            document["platforms"] = {}

        return document, raw

    def ensure_runtime_site_packages(self) -> None:
        site_packages = self.runtime_site_packages_path()
        if site_packages and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))

    def platform_schema_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "order": list(SUPPORTED_CHAT_PLATFORMS),
            "platforms": CHAT_PLATFORM_SCHEMAS,
        }

    def platform_summary_status(self, platform_id: str, values: dict[str, Any], dependencies_ok: bool) -> str:
        if not values.get("enabled"):
            return "未启用"
        if not self.platform_is_configured(platform_id, values):
            return "缺少凭据"
        if not dependencies_ok:
            return "缺少依赖"
        return "已保存"

    def platform_is_configured(self, platform_id: str, values: dict[str, Any]) -> bool:
        if platform_id in ("telegram", "discord"):
            return bool(values.get("bot_token"))
        if platform_id == "feishu":
            return bool(values.get("app_id") and values.get("app_secret"))
        if platform_id == "dingtalk":
            return bool(values.get("client_id") and values.get("client_secret"))
        return False

    def platform_dependency_status(self, platform_id: str, values: dict[str, Any]) -> tuple[bool, str]:
        try:
            self.ensure_runtime_site_packages()
            if platform_id == "telegram":
                importlib.import_module("telegram")
                return True, ""
            if platform_id == "discord":
                importlib.import_module("discord")
                return True, ""
            if platform_id == "feishu":
                importlib.import_module("lark_oapi")
                if str(values.get("connection_mode", "websocket") or "websocket") == "webhook":
                    importlib.import_module("aiohttp")
                else:
                    importlib.import_module("websockets")
                return True, ""
            if platform_id == "dingtalk":
                importlib.import_module("dingtalk_stream")
                importlib.import_module("httpx")
                return True, ""
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        return False, "unsupported platform"

    def _home_channel_values(self, platform_block: dict[str, Any]) -> tuple[str, str]:
        home_channel = platform_block.get("home_channel", {})
        if not isinstance(home_channel, dict):
            return "", "Home"
        chat_id = str(home_channel.get("chat_id", "") or "").strip()
        name = str(home_channel.get("name", "") or "Home").strip() or "Home"
        return chat_id, name

    def load_platform_values(self, platform_id: str, include_secrets: bool = False) -> dict[str, Any]:
        config, _raw = self.load_managed_config_document()
        env_values = parse_env_file(self.paths.env_file)
        platforms = config.get("platforms", {})
        platform_block = platforms.get(platform_id, {}) if isinstance(platforms, dict) else {}
        if not isinstance(platform_block, dict):
            platform_block = {}
        home_chat_id, home_channel_name = self._home_channel_values(platform_block)
        reply_to_mode = str(platform_block.get("reply_to_mode", "first") or "first")
        extra = platform_block.get("extra", {})
        if not isinstance(extra, dict):
            extra = {}

        values: dict[str, Any] = {
            "enabled": bool(platform_block.get("enabled", False)),
            "home_chat_id": home_chat_id,
            "home_channel_name": home_channel_name,
        }

        if platform_id == "telegram":
            top_cfg = config.get("telegram", {})
            if not isinstance(top_cfg, dict):
                top_cfg = {}
            secret = env_values.get("TELEGRAM_BOT_TOKEN", "").strip()
            values.update(
                {
                    "bot_token": secret if include_secrets else "",
                    "reply_to_mode": reply_to_mode,
                    "require_mention": bool(top_cfg.get("require_mention", False)),
                    "allow_all_users": env_truthy(env_values.get("TELEGRAM_ALLOW_ALL_USERS")),
                    "allowed_users": normalize_csv_text(env_values.get("TELEGRAM_ALLOWED_USERS")),
                    "free_response_chats": normalize_csv_text(top_cfg.get("free_response_chats")),
                }
            )
            return values

        if platform_id == "discord":
            top_cfg = config.get("discord", {})
            if not isinstance(top_cfg, dict):
                top_cfg = {}
            secret = env_values.get("DISCORD_BOT_TOKEN", "").strip()
            values.update(
                {
                    "bot_token": secret if include_secrets else "",
                    "reply_to_mode": reply_to_mode,
                    "require_mention": bool(top_cfg.get("require_mention", True)),
                    "allow_all_users": env_truthy(env_values.get("DISCORD_ALLOW_ALL_USERS")),
                    "allowed_users": normalize_csv_text(env_values.get("DISCORD_ALLOWED_USERS")),
                    "allowed_channels": normalize_csv_text(top_cfg.get("allowed_channels")),
                    "ignored_channels": normalize_csv_text(top_cfg.get("ignored_channels")),
                    "auto_thread": bool(top_cfg.get("auto_thread", True)),
                }
            )
            return values

        if platform_id == "feishu":
            values.update(
                {
                    "app_id": env_values.get("FEISHU_APP_ID", "").strip() if include_secrets else "",
                    "app_secret": env_values.get("FEISHU_APP_SECRET", "").strip() if include_secrets else "",
                    "domain": str(extra.get("domain", "feishu") or "feishu"),
                    "connection_mode": str(extra.get("connection_mode", "websocket") or "websocket"),
                    "encrypt_key": env_values.get("FEISHU_ENCRYPT_KEY", "").strip() if include_secrets else "",
                    "verification_token": env_values.get("FEISHU_VERIFICATION_TOKEN", "").strip() if include_secrets else "",
                    "allow_all_users": env_truthy(env_values.get("FEISHU_ALLOW_ALL_USERS")),
                    "allowed_users": normalize_csv_text(env_values.get("FEISHU_ALLOWED_USERS")),
                }
            )
            return values

        if platform_id == "dingtalk":
            values.update(
                {
                    "client_id": env_values.get("DINGTALK_CLIENT_ID", "").strip() if include_secrets else "",
                    "client_secret": env_values.get("DINGTALK_CLIENT_SECRET", "").strip() if include_secrets else "",
                    "allow_all_users": env_truthy(env_values.get("DINGTALK_ALLOW_ALL_USERS")),
                    "allowed_users": normalize_csv_text(env_values.get("DINGTALK_ALLOWED_USERS")),
                }
            )
            return values

        raise ValueError(f"unsupported platform: {platform_id}")

    def platform_secret_status(self, platform_id: str, values: dict[str, Any]) -> dict[str, dict[str, Any]]:
        if platform_id == "telegram":
            return {
                "bot_token": {
                    "configured": bool(values.get("bot_token")),
                    "preview": redact_secret(str(values.get("bot_token", "") or "")),
                }
            }
        if platform_id == "discord":
            return {
                "bot_token": {
                    "configured": bool(values.get("bot_token")),
                    "preview": redact_secret(str(values.get("bot_token", "") or "")),
                }
            }
        if platform_id == "feishu":
            return {
                "app_id": {
                    "configured": bool(values.get("app_id")),
                    "preview": redact_secret(str(values.get("app_id", "") or "")),
                },
                "app_secret": {
                    "configured": bool(values.get("app_secret")),
                    "preview": redact_secret(str(values.get("app_secret", "") or "")),
                },
                "encrypt_key": {
                    "configured": bool(values.get("encrypt_key")),
                    "preview": redact_secret(str(values.get("encrypt_key", "") or "")),
                },
                "verification_token": {
                    "configured": bool(values.get("verification_token")),
                    "preview": redact_secret(str(values.get("verification_token", "") or "")),
                },
            }
        if platform_id == "dingtalk":
            return {
                "client_id": {
                    "configured": bool(values.get("client_id")),
                    "preview": redact_secret(str(values.get("client_id", "") or "")),
                },
                "client_secret": {
                    "configured": bool(values.get("client_secret")),
                    "preview": redact_secret(str(values.get("client_secret", "") or "")),
                },
            }
        return {}

    def platform_summary(self, platform_id: str) -> dict[str, Any]:
        if platform_id not in CHAT_PLATFORM_SCHEMAS:
            raise ValueError(f"unsupported platform: {platform_id}")

        values = self.load_platform_values(platform_id, include_secrets=True)
        dependencies_ok, dependency_message = self.platform_dependency_status(platform_id, values)
        secrets = self.platform_secret_status(platform_id, values)
        public_values = dict(values)
        for field_id in secrets:
            public_values[field_id] = ""
        return {
            "id": platform_id,
            "label": CHAT_PLATFORM_SCHEMAS[platform_id]["label"],
            "description": CHAT_PLATFORM_SCHEMAS[platform_id]["description"],
            "enabled": bool(values.get("enabled")),
            "configured": self.platform_is_configured(platform_id, values),
            "dependencies_ok": dependencies_ok,
            "dependencies_message": dependency_message,
            "status": self.platform_summary_status(platform_id, values, dependencies_ok),
            "values": public_values,
            "secrets": secrets,
        }

    def platforms_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "order": list(SUPPORTED_CHAT_PLATFORMS),
            "platforms": {
                platform_id: self.platform_summary(platform_id)
                for platform_id in SUPPORTED_CHAT_PLATFORMS
            },
        }

    def platform_payload(self, platform_id: str) -> dict[str, Any]:
        return {
            "ok": True,
            "platform": self.platform_summary(platform_id),
        }

    def resolve_platform_values(self, platform_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        values = self.load_platform_values(platform_id, include_secrets=True)
        payload = payload or {}
        for key, value in payload.items():
            if key not in values:
                continue
            if key in self.platform_secret_status(platform_id, values):
                if str(value or "").strip():
                    values[key] = str(value).strip()
                continue
            if isinstance(values.get(key), bool):
                values[key] = bool(value)
                continue
            values[key] = value
        return values

    def save_platform(self, platform_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if platform_id not in CHAT_PLATFORM_SCHEMAS:
            return {"ok": False, "message": f"unsupported platform: {platform_id}"}

        values = self.resolve_platform_values(platform_id, payload)
        config, _raw = self.load_managed_config_document()
        env_values = parse_env_file(self.paths.env_file)
        platforms = config.setdefault("platforms", {})
        if not isinstance(platforms, dict):
            platforms = {}
            config["platforms"] = platforms
        platform_block = platforms.get(platform_id, {})
        if not isinstance(platform_block, dict):
            platform_block = {}
        platform_block["enabled"] = bool(values.get("enabled"))

        home_chat_id = str(values.get("home_chat_id", "") or "").strip()
        if home_chat_id:
            platform_block["home_channel"] = {
                "platform": platform_id,
                "chat_id": home_chat_id,
                "name": str(values.get("home_channel_name", "") or "Home").strip() or "Home",
            }
        else:
            platform_block.pop("home_channel", None)

        if platform_id in ("telegram", "discord"):
            platform_block["reply_to_mode"] = str(values.get("reply_to_mode", "first") or "first")
        else:
            platform_block.pop("reply_to_mode", None)

        extra = platform_block.get("extra", {})
        if not isinstance(extra, dict):
            extra = {}

        if platform_id == "telegram":
            if str(values.get("bot_token", "") or "").strip():
                env_values["TELEGRAM_BOT_TOKEN"] = str(values["bot_token"]).strip()
            if values.get("allow_all_users"):
                env_values["TELEGRAM_ALLOW_ALL_USERS"] = "true"
            else:
                env_values.pop("TELEGRAM_ALLOW_ALL_USERS", None)
            allowed_users = list_to_csv_env(str(values.get("allowed_users", "") or ""))
            if allowed_users:
                env_values["TELEGRAM_ALLOWED_USERS"] = allowed_users
            else:
                env_values.pop("TELEGRAM_ALLOWED_USERS", None)

            section = config.get("telegram", {})
            if not isinstance(section, dict):
                section = {}
            section["require_mention"] = bool(values.get("require_mention"))
            free_response_chats = csv_text_to_list(str(values.get("free_response_chats", "") or ""))
            if free_response_chats:
                section["free_response_chats"] = free_response_chats
            else:
                section.pop("free_response_chats", None)
            if section:
                config["telegram"] = section
            else:
                config.pop("telegram", None)

        elif platform_id == "discord":
            if str(values.get("bot_token", "") or "").strip():
                env_values["DISCORD_BOT_TOKEN"] = str(values["bot_token"]).strip()
            if values.get("allow_all_users"):
                env_values["DISCORD_ALLOW_ALL_USERS"] = "true"
            else:
                env_values.pop("DISCORD_ALLOW_ALL_USERS", None)
            allowed_users = list_to_csv_env(str(values.get("allowed_users", "") or ""))
            if allowed_users:
                env_values["DISCORD_ALLOWED_USERS"] = allowed_users
            else:
                env_values.pop("DISCORD_ALLOWED_USERS", None)

            section = config.get("discord", {})
            if not isinstance(section, dict):
                section = {}
            section["require_mention"] = bool(values.get("require_mention"))
            section["auto_thread"] = bool(values.get("auto_thread", True))
            allowed_channels = csv_text_to_list(str(values.get("allowed_channels", "") or ""))
            ignored_channels = csv_text_to_list(str(values.get("ignored_channels", "") or ""))
            if allowed_channels:
                section["allowed_channels"] = allowed_channels
            else:
                section.pop("allowed_channels", None)
            if ignored_channels:
                section["ignored_channels"] = ignored_channels
            else:
                section.pop("ignored_channels", None)
            if section:
                config["discord"] = section
            else:
                config.pop("discord", None)

        elif platform_id == "feishu":
            if str(values.get("app_id", "") or "").strip():
                env_values["FEISHU_APP_ID"] = str(values["app_id"]).strip()
            if str(values.get("app_secret", "") or "").strip():
                env_values["FEISHU_APP_SECRET"] = str(values["app_secret"]).strip()
            if str(values.get("encrypt_key", "") or "").strip():
                env_values["FEISHU_ENCRYPT_KEY"] = str(values["encrypt_key"]).strip()
            if str(values.get("verification_token", "") or "").strip():
                env_values["FEISHU_VERIFICATION_TOKEN"] = str(values["verification_token"]).strip()
            if values.get("allow_all_users"):
                env_values["FEISHU_ALLOW_ALL_USERS"] = "true"
            else:
                env_values.pop("FEISHU_ALLOW_ALL_USERS", None)
            allowed_users = list_to_csv_env(str(values.get("allowed_users", "") or ""))
            if allowed_users:
                env_values["FEISHU_ALLOWED_USERS"] = allowed_users
            else:
                env_values.pop("FEISHU_ALLOWED_USERS", None)

            extra["domain"] = str(values.get("domain", "feishu") or "feishu")
            extra["connection_mode"] = str(values.get("connection_mode", "websocket") or "websocket")
            platform_block["extra"] = extra

        elif platform_id == "dingtalk":
            if str(values.get("client_id", "") or "").strip():
                env_values["DINGTALK_CLIENT_ID"] = str(values["client_id"]).strip()
            if str(values.get("client_secret", "") or "").strip():
                env_values["DINGTALK_CLIENT_SECRET"] = str(values["client_secret"]).strip()
            if values.get("allow_all_users"):
                env_values["DINGTALK_ALLOW_ALL_USERS"] = "true"
            else:
                env_values.pop("DINGTALK_ALLOW_ALL_USERS", None)
            allowed_users = list_to_csv_env(str(values.get("allowed_users", "") or ""))
            if allowed_users:
                env_values["DINGTALK_ALLOWED_USERS"] = allowed_users
            else:
                env_values.pop("DINGTALK_ALLOWED_USERS", None)

        platforms[platform_id] = platform_block
        config["platforms"] = platforms
        write_config_file(self.paths.config_file, config)
        write_env_file(self.paths.env_file, env_values)
        logging.info("saved chat platform config platform=%s enabled=%s", platform_id, values.get("enabled"))
        return {
            "ok": True,
            "message": f"{CHAT_PLATFORM_SCHEMAS[platform_id]['label']} 配置已保存；需要重启 Hermes gateway 才会生效。",
            "restart_required": True,
            "platform": self.platform_summary(platform_id),
        }

    def test_platform_connection(self, platform_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if platform_id not in CHAT_PLATFORM_SCHEMAS:
            return {"ok": False, "message": f"unsupported platform: {platform_id}"}

        values = self.resolve_platform_values(platform_id, payload)
        dependencies_ok, dependency_message = self.platform_dependency_status(platform_id, values)
        if not dependencies_ok:
            return {
                "ok": False,
                "message": f"依赖不可用：{dependency_message}",
                "platform": platform_id,
            }

        if platform_id == "telegram":
            token = str(values.get("bot_token", "") or "").strip()
            if not token:
                return {"ok": False, "message": "缺少 Telegram Bot Token", "platform": platform_id}
            status_code, response = http_json_request(
                url=f"https://api.telegram.org/bot{token}/getMe",
                timeout=8,
            )
            if status_code == 200 and response.get("ok"):
                result = response.get("result", {}) if isinstance(response, dict) else {}
                username = str(result.get("username", "") or "").strip()
                return {
                    "ok": True,
                    "message": f"Telegram 连接成功：{username or 'bot 已认证'}",
                    "platform": platform_id,
                    "details": result,
                }
            return {
                "ok": False,
                "message": error_message_from_payload(response, f"Telegram 鉴权失败：HTTP {status_code}"),
                "platform": platform_id,
                "status_code": status_code,
            }

        if platform_id == "discord":
            token = str(values.get("bot_token", "") or "").strip()
            if not token:
                return {"ok": False, "message": "缺少 Discord Bot Token", "platform": platform_id}
            status_code, response = http_json_request(
                url="https://discord.com/api/v10/users/@me",
                headers={"Authorization": f"Bot {token}"},
                timeout=8,
            )
            if status_code == 200:
                username = str(response.get("username", "") or "").strip()
                discriminator = str(response.get("discriminator", "") or "").strip()
                display_name = f"{username}#{discriminator}" if username and discriminator else username or "bot 已认证"
                return {
                    "ok": True,
                    "message": f"Discord 连接成功：{display_name}",
                    "platform": platform_id,
                    "details": response,
                }
            return {
                "ok": False,
                "message": error_message_from_payload(response, f"Discord 鉴权失败：HTTP {status_code}"),
                "platform": platform_id,
                "status_code": status_code,
            }

        if platform_id == "feishu":
            app_id = str(values.get("app_id", "") or "").strip()
            app_secret = str(values.get("app_secret", "") or "").strip()
            if not app_id or not app_secret:
                return {"ok": False, "message": "缺少 Feishu App ID 或 App Secret", "platform": platform_id}
            domain = str(values.get("domain", "feishu") or "feishu").strip().lower()
            base_url = "https://open.larksuite.com" if domain == "lark" else "https://open.feishu.cn"
            status_code, response = http_json_request(
                url=f"{base_url}/open-apis/auth/v3/tenant_access_token/internal",
                method="POST",
                body={"app_id": app_id, "app_secret": app_secret},
                timeout=10,
            )
            if status_code == 200 and isinstance(response, dict) and response.get("tenant_access_token"):
                return {
                    "ok": True,
                    "message": f"Feishu 连接成功：{domain} / {values.get('connection_mode', 'websocket')}",
                    "platform": platform_id,
                    "details": {
                        "expire": response.get("expire"),
                        "domain": domain,
                        "connection_mode": values.get("connection_mode", "websocket"),
                    },
                }
            return {
                "ok": False,
                "message": error_message_from_payload(response, f"Feishu 鉴权失败：HTTP {status_code}"),
                "platform": platform_id,
                "status_code": status_code,
            }

        if platform_id == "dingtalk":
            client_id = str(values.get("client_id", "") or "").strip()
            client_secret = str(values.get("client_secret", "") or "").strip()
            if not client_id or not client_secret:
                return {"ok": False, "message": "缺少 DingTalk Client ID 或 Client Secret", "platform": platform_id}
            status_code, response = http_json_request(
                url="https://api.dingtalk.com/v1.0/oauth2/accessToken",
                method="POST",
                body={"appKey": client_id, "appSecret": client_secret},
                timeout=10,
            )
            if status_code == 200 and isinstance(response, dict) and response.get("accessToken"):
                return {
                    "ok": True,
                    "message": "DingTalk 连接成功，已获取 access token。",
                    "platform": platform_id,
                    "details": {
                        "expireIn": response.get("expireIn"),
                    },
                }
            return {
                "ok": False,
                "message": error_message_from_payload(response, f"DingTalk 鉴权失败：HTTP {status_code}"),
                "platform": platform_id,
                "status_code": status_code,
            }

        return {"ok": False, "message": "unsupported platform", "platform": platform_id}

    def api_server_health(self) -> dict[str, Any]:
        url = f"{self.api_server_url()}/health"
        try:
            status, payload = http_json_request(
                url,
                headers=self.api_server_headers(),
                timeout=1.5,
            )
            return {
                "ok": status == 200,
                "status_code": status,
                "url": url,
                "payload": payload,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "status_code": 0,
                "url": url,
                "error": str(exc),
            }

    def _python_can_import_hermes(self, python_command: list[str]) -> bool:
        try:
            result = subprocess.run(
                python_command + ["-c", "import hermes_cli.main"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=4,
                check=False,
            )
            return result.returncode == 0
        except Exception:  # noqa: BLE001
            return False

    def resolve_hermes_command(self) -> tuple[list[str] | None, list[str]]:
        attempted: list[str] = []

        override = os.getenv("TRIM_HERMES_EXECUTABLE", "").strip()
        if override:
            command = shlex.split(override)
            attempted.append("override:" + " ".join(command))
            return command, attempted

        bundled_binary = self.paths.app_root / "runtime" / "python" / "bin" / "hermes"
        if bundled_binary.exists() and os.access(bundled_binary, os.X_OK):
            attempted.append(str(bundled_binary))
            return [str(bundled_binary)], attempted
        attempted.append(str(bundled_binary))

        hermes_on_path = shutil.which("hermes")
        if hermes_on_path:
            attempted.append(hermes_on_path)
            return [hermes_on_path], attempted
        attempted.append("PATH:hermes")

        bundled_python = self.paths.app_root / "runtime" / "python" / "bin" / "python3"
        if bundled_python.exists() and os.access(bundled_python, os.X_OK):
            attempted.append(f"{bundled_python} -m hermes_cli.main")
            if self._python_can_import_hermes([str(bundled_python)]):
                return [str(bundled_python), "-m", "hermes_cli.main"], attempted

        system_python = shutil.which("python3") or sys.executable
        attempted.append(f"{system_python} -m hermes_cli.main")
        if self._python_can_import_hermes([system_python]):
            return [system_python, "-m", "hermes_cli.main"], attempted

        return None, attempted

    def load_setup_summary(self) -> dict[str, Any]:
        config, raw = load_config_file(self.paths.config_file)
        env_values = parse_env_file(self.paths.env_file)

        model_block = config.get("model", {}) if isinstance(config, dict) else {}
        provider = ""
        model_name = ""
        base_url = ""
        approvals_mode = DEFAULT_APPROVAL_MODE
        if isinstance(model_block, dict):
            provider = str(model_block.get("provider", "") or "")
            model_name = str(model_block.get("default", "") or "")
            base_url = str(model_block.get("base_url", "") or "")
        if isinstance(config, dict):
            approvals_mode = str(config.get("approvals", {}).get("mode", DEFAULT_APPROVAL_MODE) or DEFAULT_APPROVAL_MODE)

        preset = PROVIDER_PRESETS.get(provider, {})
        api_key_env = preset.get("api_key_env", "OPENAI_API_KEY")
        api_key_value = env_values.get(api_key_env, "")

        return {
            "provider": provider,
            "model": model_name,
            "base_url": base_url,
            "approvals_mode": approvals_mode,
            "api_key_env": api_key_env,
            "api_key_configured": bool(api_key_value),
            "api_key_preview": redact_secret(api_key_value),
            "api_server_host": env_values.get("API_SERVER_HOST", DEFAULT_API_SERVER_HOST),
            "api_server_port": env_values.get("API_SERVER_PORT", str(DEFAULT_API_SERVER_PORT)),
            "api_server_key_configured": bool(env_values.get("API_SERVER_KEY", "").strip()),
            "api_server_key_preview": redact_secret(env_values.get("API_SERVER_KEY", "").strip()),
            "raw_config_is_json": config is not None,
            "raw_config_preview": raw[:400] if raw and config is None else "",
        }

    def resolve_setup_values(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        saved = self.load_setup_summary()
        payload = payload or {}

        provider = str(payload.get("provider", "") or saved.get("provider") or "openrouter").strip() or "openrouter"
        preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["custom"])
        model = str(payload.get("model", "") or saved.get("model") or "").strip()
        base_url = str(payload.get("base_url", "") or saved.get("base_url") or preset.get("base_url", "")).strip()
        approvals_mode = str(payload.get("approvals_mode", "") or saved.get("approvals_mode") or DEFAULT_APPROVAL_MODE).strip() or DEFAULT_APPROVAL_MODE

        env_values = parse_env_file(self.paths.env_file)
        api_key_env = preset.get("api_key_env", "OPENAI_API_KEY")
        payload_api_key = str(payload.get("api_key", "") or "").strip()
        api_key = payload_api_key or env_values.get(api_key_env, "").strip()

        return {
            "provider": provider,
            "model": model,
            "base_url": normalize_base_url(provider, base_url),
            "approvals_mode": approvals_mode,
            "api_key_env": api_key_env,
            "api_key": api_key,
        }

    def provider_models_headers(self, provider: str, api_key: str) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
        }
        if provider == "anthropic":
            headers["anthropic-version"] = "2023-06-01"
            if api_key:
                headers["x-api-key"] = api_key
            return headers

        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def provider_models_candidates(self, provider: str, base_url: str) -> list[tuple[str, bool]]:
        normalized = (base_url or "").strip().rstrip("/")
        if provider == "anthropic":
            if not normalized:
                normalized = "https://api.anthropic.com"
            if normalized.endswith("/v1"):
                return [(normalized, False)]
            return [(normalized, False), (normalized + "/v1", True)]

        if not normalized:
            return []

        if normalized.endswith("/v1"):
            alternate_base = normalized[:-3].rstrip("/")
        else:
            alternate_base = normalized + "/v1"

        candidates: list[tuple[str, bool]] = [(normalized, False)]
        if alternate_base and alternate_base != normalized:
            candidates.append((alternate_base, True))
        return candidates

    def provider_models(self) -> dict[str, Any]:
        setup = self.resolve_setup_values()
        provider = str(setup.get("provider", "") or "").strip() or "custom"
        base_url = str(setup.get("base_url", "") or "").strip()
        api_key = str(setup.get("api_key", "") or "").strip()
        candidates = self.provider_models_candidates(provider, base_url)

        if not candidates:
            return {
                "ok": False,
                "status_code": 0,
                "message": "provider base URL is not configured",
                "response": {
                    "object": "list",
                    "data": [],
                },
                "source": "provider",
                "provider": provider,
            }

        headers = self.provider_models_headers(provider, api_key)
        tried: list[str] = []
        last_status = 0
        last_message = "failed to fetch provider models"

        for candidate_base, used_fallback in candidates:
            if provider == "anthropic":
                url = candidate_base.rstrip("/") + "/models?limit=1000"
            else:
                url = candidate_base.rstrip("/") + "/models"
            tried.append(url)

            try:
                status_code, response = http_json_request(
                    url=url,
                    headers=headers,
                    timeout=5,
                )
            except Exception as exc:  # noqa: BLE001
                last_message = str(exc)
                continue

            last_status = status_code
            if status_code != 200:
                last_message = error_message_from_payload(
                    response,
                    f"provider models request failed: HTTP {status_code}",
                )
                continue

            models = normalize_model_catalog(response)
            message = ""
            if used_fallback:
                message = f"model listing worked via `{candidate_base}`; current base URL may be missing `/v1`"

            return {
                "ok": True,
                "status_code": status_code,
                "message": message,
                "response": {
                    "object": "list",
                    "data": models,
                },
                "source": "provider",
                "provider": provider,
                "probed_url": url,
                "resolved_base_url": candidate_base,
                "attempted": tried,
            }

        return {
            "ok": False,
            "status_code": last_status,
            "message": last_message,
            "response": {
                "object": "list",
                "data": [],
            },
            "source": "provider",
            "provider": provider,
            "attempted": tried,
        }

    def provider_chat_test_candidates(self, provider: str, base_url: str) -> list[tuple[str, bool]]:
        return self.provider_models_candidates(provider, base_url)

    def provider_chat_test(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        setup = self.resolve_setup_values(payload)
        provider = str(setup.get("provider", "") or "").strip() or "custom"
        model = str(setup.get("model", "") or "").strip()
        base_url = str(setup.get("base_url", "") or "").strip()
        api_key = str(setup.get("api_key", "") or "").strip()

        if not model:
            return {
                "ok": False,
                "message": "默认模型不能为空",
                "provider": provider,
            }

        candidates = self.provider_chat_test_candidates(provider, base_url)
        if not candidates:
            return {
                "ok": False,
                "message": "provider base URL is not configured",
                "provider": provider,
            }

        tried: list[str] = []
        last_status = 0
        last_message = "failed to probe provider chat endpoint"

        for candidate_base, used_fallback in candidates:
            if provider == "anthropic":
                url = candidate_base.rstrip("/") + "/messages"
                body = {
                    "model": model,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "ping"}],
                }
            else:
                url = candidate_base.rstrip("/") + "/chat/completions"
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "stream": False,
                    "max_tokens": 1,
                }

            tried.append(url)
            try:
                status_code, response = http_json_request(
                    url=url,
                    method="POST",
                    body=body,
                    headers=self.provider_models_headers(provider, api_key),
                    timeout=20,
                )
            except Exception as exc:  # noqa: BLE001
                last_message = str(exc)
                continue

            last_status = status_code
            if isinstance(response, dict) and isinstance(response.get("raw"), str):
                raw_text = str(response.get("raw", "") or "").strip()
                last_message = (
                    f"provider chat endpoint returned a non-JSON response: {raw_text[:200]}"
                    if raw_text
                    else "provider chat endpoint returned an empty response"
                )
                continue
            if status_code == 200:
                message = "模型配置测试通过。"
                if used_fallback:
                    message += f" 实际使用 `{candidate_base}` 访问成功，建议将 Base URL 改为该值。"
                return {
                    "ok": True,
                    "message": message,
                    "provider": provider,
                    "model": model,
                    "status_code": status_code,
                    "resolved_base_url": candidate_base,
                    "probed_url": url,
                    "attempted": tried,
                }

            last_message = error_message_from_payload(
                response,
                f"provider chat test failed: HTTP {status_code}",
            )

        return {
            "ok": False,
            "message": last_message,
            "provider": provider,
            "model": model,
            "status_code": last_status,
            "attempted": tried,
        }

    def config_test(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        setup = self.resolve_setup_values(payload)
        provider = str(setup.get("provider", "") or "").strip() or "custom"
        model = str(setup.get("model", "") or "").strip()

        if not model:
            return {
                "ok": False,
                "message": "默认模型不能为空",
                "provider": provider,
            }

        models_payload = self.provider_models() if not payload else self._provider_models_for_payload(payload)
        if not models_payload.get("ok"):
            return {
                "ok": False,
                "message": f"模型目录测试失败：{models_payload.get('message', 'unknown error')}",
                "provider": provider,
                "stage": "models",
                "details": models_payload,
            }

        model_ids = {
            str(item.get("id", "") or "").strip()
            for item in models_payload.get("response", {}).get("data", [])
            if isinstance(item, dict)
        }
        if model_ids and model not in model_ids:
            return {
                "ok": False,
                "message": f"默认模型 `{model}` 不在当前供应商返回的模型列表中。",
                "provider": provider,
                "stage": "models",
                "details": models_payload,
            }

        chat_payload = self.provider_chat_test(payload)
        if not chat_payload.get("ok"):
            return {
                "ok": False,
                "message": f"模型请求测试失败：{chat_payload.get('message', 'unknown error')}",
                "provider": provider,
                "model": model,
                "stage": "chat",
                "details": chat_payload,
            }

        return {
            "ok": True,
            "message": chat_payload.get("message") or "模型配置测试通过。",
            "provider": provider,
            "model": model,
            "stage": "chat",
            "details": {
                "models": models_payload,
                "chat": chat_payload,
            },
        }

    def _provider_models_for_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        setup = self.resolve_setup_values(payload)
        provider = str(setup.get("provider", "") or "").strip() or "custom"
        base_url = str(setup.get("base_url", "") or "").strip()
        api_key = str(setup.get("api_key", "") or "").strip()
        candidates = self.provider_models_candidates(provider, base_url)

        if not candidates:
            return {
                "ok": False,
                "status_code": 0,
                "message": "provider base URL is not configured",
                "response": {"object": "list", "data": []},
                "source": "provider",
                "provider": provider,
            }

        headers = self.provider_models_headers(provider, api_key)
        tried: list[str] = []
        last_status = 0
        last_message = "failed to fetch provider models"

        for candidate_base, used_fallback in candidates:
            url = candidate_base.rstrip("/") + ("/models?limit=1000" if provider == "anthropic" else "/models")
            tried.append(url)
            try:
                status_code, response = http_json_request(url=url, headers=headers, timeout=5)
            except Exception as exc:  # noqa: BLE001
                last_message = str(exc)
                continue
            last_status = status_code
            if status_code != 200:
                last_message = error_message_from_payload(response, f"provider models request failed: HTTP {status_code}")
                continue
            models = normalize_model_catalog(response)
            message = ""
            if used_fallback:
                message = f"model listing worked via `{candidate_base}`; current base URL may be missing `/v1`"
            return {
                "ok": True,
                "status_code": status_code,
                "message": message,
                "response": {"object": "list", "data": models},
                "source": "provider",
                "provider": provider,
                "probed_url": url,
                "resolved_base_url": candidate_base,
                "attempted": tried,
            }

        return {
            "ok": False,
            "status_code": last_status,
            "message": last_message,
            "response": {"object": "list", "data": []},
            "source": "provider",
            "provider": provider,
            "attempted": tried,
        }

    def save_setup(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider = str(payload.get("provider", "") or "").strip() or "openrouter"
        preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["custom"])
        model = str(payload.get("model", "") or "").strip()
        base_url = str(payload.get("base_url", "") or "").strip() or preset.get("base_url", "")
        approvals_mode = str(payload.get("approvals_mode", DEFAULT_APPROVAL_MODE) or DEFAULT_APPROVAL_MODE)
        api_key = str(payload.get("api_key", "") or "").strip()

        config, _raw = self.load_managed_config_document()
        model_block = config.setdefault("model", {})
        if not isinstance(model_block, dict):
            model_block = {}
            config["model"] = model_block
        model_block["default"] = model
        model_block["provider"] = provider
        if base_url:
            model_block["base_url"] = base_url
        else:
            model_block.pop("base_url", None)

        approvals = config.setdefault("approvals", {})
        if not isinstance(approvals, dict):
            approvals = {}
            config["approvals"] = approvals
        approvals["mode"] = approvals_mode
        write_config_file(self.paths.config_file, config)

        env_values = parse_env_file(self.paths.env_file)
        env_values["API_SERVER_ENABLED"] = "true"
        env_values["API_SERVER_HOST"] = DEFAULT_API_SERVER_HOST
        env_values["API_SERVER_PORT"] = str(DEFAULT_API_SERVER_PORT)
        env_values["API_SERVER_CORS_ORIGINS"] = ""
        env_values["API_SERVER_MODEL_NAME"] = model
        self.ensure_api_server_key(env_values)

        api_key_env = preset.get("api_key_env", "OPENAI_API_KEY")
        if api_key:
            env_values[api_key_env] = api_key
        write_env_file(self.paths.env_file, env_values)

        logging.info("saved trim.hermes setup provider=%s model=%s", provider, model)
        return self.load_setup_summary()

    def build_gateway_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(parse_env_file(self.paths.env_file))
        env["HOME"] = str(self.paths.home_root)
        env["HERMES_HOME"] = str(self.paths.hermes_home)
        env["HERMES_WRITE_SAFE_ROOT"] = str(self.paths.workspace_root)
        env["HERMES_MANAGED_BY"] = APP_NAME
        return env

    def dashboard_health(self) -> dict[str, Any]:
        url = self.dashboard_base_url() + "/api/status"
        try:
            status_code, payload = http_json_request(url, timeout=2)
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "status_code": 0,
                "url": url,
                "message": str(exc),
            }
        return {
            "ok": status_code == 200,
            "status_code": status_code,
            "url": url,
            "payload": payload,
        }

    def dashboard_status(self) -> dict[str, Any]:
        state = read_gateway_state(self.paths.dashboard_state_file)
        pid = int(state.get("pid", 0)) if isinstance(state, dict) else 0
        running = is_pid_running(pid)
        if state and not running:
            remove_gateway_state(self.paths.dashboard_state_file)
            state = None
            pid = 0

        command, attempted = self.resolve_hermes_command()
        return {
            "running": running,
            "pid": pid,
            "started_at": state.get("started_at") if isinstance(state, dict) else None,
            "command": state.get("command") if isinstance(state, dict) else None,
            "health": self.dashboard_health(),
            "url": self.dashboard_base_url(),
            "hermes_command": command,
            "hermes_command_candidates": attempted,
            "dashboard_log": str(self.paths.dashboard_log_file),
        }

    def start_dashboard(self) -> dict[str, Any]:
        with self._lock:
            status = self.dashboard_status()
            if status["running"]:
                return {"ok": True, "message": "Hermes dashboard already running.", "status": status}

            command, attempted = self.resolve_hermes_command()
            if not command:
                return {
                    "ok": False,
                    "message": "Hermes runtime is not bundled yet and no system `hermes` command was found.",
                    "status": status,
                    "attempted": attempted,
                }

            env = self.build_gateway_env()
            full_command = command + [
                "dashboard",
                "--host",
                self.dashboard_host,
                "--port",
                str(self.dashboard_port),
                "--no-open",
            ]
            self.paths.dashboard_log_file.parent.mkdir(parents=True, exist_ok=True)
            with self.paths.dashboard_log_file.open("ab") as log_handle:
                process = subprocess.Popen(
                    full_command,
                    cwd=str(self.paths.workspace_root),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            write_gateway_state(
                self.paths.dashboard_state_file,
                {
                    "pid": process.pid,
                    "command": full_command,
                    "started_at": time.time(),
                },
            )
            logging.info("started Hermes dashboard pid=%s command=%s", process.pid, " ".join(full_command))

            deadline = time.time() + START_TIMEOUT_SECONDS
            while time.time() < deadline:
                if process.poll() is not None:
                    return {
                        "ok": False,
                        "message": "Hermes dashboard exited during startup.",
                        "status": self.dashboard_status(),
                        "log_tail": tail_lines(self.paths.dashboard_log_file, 80),
                    }
                health = self.dashboard_health()
                if health["ok"]:
                    return {
                        "ok": True,
                        "message": "Hermes dashboard started successfully.",
                        "status": self.dashboard_status(),
                    }
                time.sleep(1)

            return {
                "ok": True,
                "message": "Hermes dashboard process started; health check is still warming up.",
                "status": self.dashboard_status(),
            }

    def stop_dashboard(self) -> dict[str, Any]:
        with self._lock:
            state = read_gateway_state(self.paths.dashboard_state_file)
            pid = int(state.get("pid", 0)) if isinstance(state, dict) else 0
            if not is_pid_running(pid):
                remove_gateway_state(self.paths.dashboard_state_file)
                return {"ok": True, "message": "Hermes dashboard is already stopped.", "status": self.dashboard_status()}

            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                os.kill(pid, signal.SIGTERM)

            deadline = time.time() + 10
            while time.time() < deadline:
                if not is_pid_running(pid):
                    remove_gateway_state(self.paths.dashboard_state_file)
                    logging.info("stopped Hermes dashboard pid=%s", pid)
                    return {"ok": True, "message": "Hermes dashboard stopped.", "status": self.dashboard_status()}
                time.sleep(0.5)

            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                os.kill(pid, signal.SIGKILL)
            remove_gateway_state(self.paths.dashboard_state_file)
            logging.warning("force-killed Hermes dashboard pid=%s", pid)
            return {"ok": True, "message": "Hermes dashboard stopped with SIGKILL.", "status": self.dashboard_status()}

    def gateway_status(self) -> dict[str, Any]:
        state = read_gateway_state(self.paths.gateway_state_file)
        pid = int(state.get("pid", 0)) if isinstance(state, dict) else 0
        running = is_pid_running(pid)
        if state and not running:
            remove_gateway_state(self.paths.gateway_state_file)
            state = None
            pid = 0

        command, attempted = self.resolve_hermes_command()
        return {
            "running": running,
            "pid": pid,
            "started_at": state.get("started_at") if isinstance(state, dict) else None,
            "command": state.get("command") if isinstance(state, dict) else None,
            "api_server": self.api_server_health(),
            "hermes_command": command,
            "hermes_command_candidates": attempted,
            "gateway_log": str(self.paths.gateway_log_file),
            "control_log": str(self.paths.control_log_file),
        }

    def start_gateway(self) -> dict[str, Any]:
        with self._lock:
            self.ensure_api_server_key()
            status = self.gateway_status()
            if status["running"]:
                return {
                    "ok": True,
                    "message": "Hermes gateway already running.",
                    "status": status,
                }

            command, attempted = self.resolve_hermes_command()
            if not command:
                return {
                    "ok": False,
                    "message": "Hermes runtime is not bundled yet and no system `hermes` command was found.",
                    "status": status,
                    "attempted": attempted,
                }

            env = self.build_gateway_env()
            full_command = command + ["gateway", "run", "--replace"]
            self.paths.gateway_log_file.parent.mkdir(parents=True, exist_ok=True)
            with self.paths.gateway_log_file.open("ab") as log_handle:
                process = subprocess.Popen(
                    full_command,
                    cwd=str(self.paths.workspace_root),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            write_gateway_state(
                self.paths.gateway_state_file,
                {
                    "pid": process.pid,
                    "command": full_command,
                    "started_at": time.time(),
                },
            )
            logging.info("started Hermes gateway pid=%s command=%s", process.pid, " ".join(full_command))

            deadline = time.time() + START_TIMEOUT_SECONDS
            while time.time() < deadline:
                if process.poll() is not None:
                    return {
                        "ok": False,
                        "message": "Hermes gateway exited during startup.",
                        "status": self.gateway_status(),
                        "log_tail": tail_lines(self.paths.gateway_log_file, 60),
                    }
                api_health = self.api_server_health()
                if api_health["ok"]:
                    return {
                        "ok": True,
                        "message": "Hermes gateway started successfully.",
                        "status": self.gateway_status(),
                    }
                time.sleep(1)

            return {
                "ok": True,
                "message": "Hermes gateway process started; api_server is still warming up.",
                "status": self.gateway_status(),
            }

    def stop_gateway(self) -> dict[str, Any]:
        with self._lock:
            state = read_gateway_state(self.paths.gateway_state_file)
            pid = int(state.get("pid", 0)) if isinstance(state, dict) else 0
            if not is_pid_running(pid):
                remove_gateway_state(self.paths.gateway_state_file)
                return {
                    "ok": True,
                    "message": "Hermes gateway is already stopped.",
                    "status": self.gateway_status(),
                }

            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                os.kill(pid, signal.SIGTERM)

            deadline = time.time() + 10
            while time.time() < deadline:
                if not is_pid_running(pid):
                    remove_gateway_state(self.paths.gateway_state_file)
                    logging.info("stopped Hermes gateway pid=%s", pid)
                    return {
                        "ok": True,
                        "message": "Hermes gateway stopped.",
                        "status": self.gateway_status(),
                    }
                time.sleep(0.5)

            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                os.kill(pid, signal.SIGKILL)
            remove_gateway_state(self.paths.gateway_state_file)
            logging.warning("force-killed Hermes gateway pid=%s", pid)
            return {
                "ok": True,
                "message": "Hermes gateway stopped with SIGKILL.",
                "status": self.gateway_status(),
            }

    def restart_gateway(self) -> dict[str, Any]:
        stopped = self.stop_gateway()
        started = self.start_gateway()
        return {
            "ok": bool(stopped.get("ok") and started.get("ok")),
            "message": "Hermes gateway restarted." if started.get("ok") else started.get("message", "Failed to restart gateway."),
            "stop": stopped,
            "start": started,
            "status": self.gateway_status(),
        }

    def system_status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": APP_NAME,
            "mode": "fnos-dashboard-wrapper",
            "paths": {
                "app_root": str(self.paths.app_root),
                "data_root": str(self.paths.data_root),
                "hermes_home": str(self.paths.hermes_home),
                "workspace_root": str(self.paths.workspace_root),
                "config_file": str(self.paths.config_file),
                "env_file": str(self.paths.env_file),
            },
            "setup": self.load_setup_summary(),
            "gateway": self.gateway_status(),
            "dashboard": self.dashboard_status(),
        }

    def logs_payload(self, log_name: str, line_count: int) -> dict[str, Any]:
        line_count = max(20, min(line_count, 400))
        path = self.paths.gateway_log_file if log_name == "gateway" else self.paths.control_log_file
        return {
            "ok": True,
            "log": log_name,
            "path": str(path),
            "lines": tail_lines(path, line_count),
        }

    def sessions_payload(self, limit: int, offset: int) -> dict[str, Any]:
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        try:
            db = self.open_session_db()
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "sessions": [],
                "message": f"Session store unavailable: {exc}",
            }

        try:
            sessions = db.list_sessions_rich(limit=limit, offset=offset)
            total = db.session_count()
            now = time.time()
            for session in sessions:
                session["is_active"] = (
                    session.get("ended_at") is None
                    and (now - session.get("last_active", session.get("started_at", 0))) < 300
                )
            return {
                "ok": True,
                "sessions": sessions,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        finally:
            db.close()

    def session_messages_payload(self, session_id: str) -> tuple[dict[str, Any], HTTPStatus]:
        try:
            db = self.open_session_db()
        except Exception as exc:  # noqa: BLE001
            return (
                {
                    "ok": False,
                    "message": f"Session store unavailable: {exc}",
                },
                HTTPStatus.SERVICE_UNAVAILABLE,
            )

        try:
            resolved_session_id = db.resolve_session_id(session_id)
            if not resolved_session_id:
                return (
                    {
                        "ok": False,
                        "message": "Session not found",
                        "session_id": session_id,
                        "messages": [],
                    },
                    HTTPStatus.NOT_FOUND,
                )
            session = db.get_session(resolved_session_id) or {}
            messages = db.get_messages(resolved_session_id)
            return (
                {
                    "ok": True,
                    "session_id": resolved_session_id,
                    "session": session,
                    "messages": messages,
                },
                HTTPStatus.OK,
            )
        finally:
            db.close()

    def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        gateway = self.gateway_status()
        if not gateway["api_server"]["ok"]:
            return {
                "ok": False,
                "message": "Hermes api_server is not ready. Start the runtime first.",
                "status": gateway,
            }

        message = str(payload.get("message", "") or "").strip()
        if not message:
            return {"ok": False, "message": "message is required"}

        setup = self.load_setup_summary()
        model = str(payload.get("model", "") or setup.get("model") or "hermes-agent")
        session_id = str(payload.get("session_id", "") or uuid.uuid4())
        request_body = {
            "model": model,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": message,
                }
            ],
        }
        try:
            status_code, response = http_json_request(
                url=f"{self.api_server_url()}/v1/chat/completions",
                method="POST",
                body=request_body,
                headers=self.api_server_headers({"X-Hermes-Session-Id": session_id}),
                timeout=120,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "message": str(exc),
            }

        assistant_text = ""
        choices = response.get("choices", []) if isinstance(response, dict) else []
        if choices:
            assistant_text = str(choices[0].get("message", {}).get("content", "") or "")

        upstream_error = looks_like_upstream_chat_error(assistant_text)
        message_text = assistant_text if upstream_error else ""

        return {
            "ok": status_code == 200 and not upstream_error,
            "status_code": status_code,
            "session_id": session_id,
            "assistant_text": assistant_text,
            "message": message_text,
            "error_type": "upstream_provider_error" if upstream_error else "",
            "response": response,
        }

    def models(self) -> dict[str, Any]:
        return self.provider_models()

    def shutdown(self) -> None:
        try:
            self.stop_gateway()
        except Exception as exc:  # noqa: BLE001
            logging.warning("failed to stop Hermes gateway during shutdown: %s", exc)


class ControlPlaneHandler(SimpleHTTPRequestHandler):
    server_version = "trim-hermes-control/0.2"
    hop_by_hop_headers = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }

    def __init__(self, *args: Any, directory: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, directory=directory, **kwargs)

    @property
    def context(self) -> HermesControlContext:
        return self.server.control_context

    def _is_gateway_authenticated_admin(self) -> bool:
        raw_value = (self.headers.get("X-Trim-Isadmin") or "").strip().lower()
        return raw_value in {"1", "true", "yes"}

    def _write_forbidden(self) -> None:
        self._write_json(
            {
                "ok": False,
                "error": "fnos_admin_required",
                "message": "Only fnOS administrators can access Hermes.",
            },
            status=HTTPStatus.FORBIDDEN,
        )

    def _write_update_blocked(self) -> None:
        self._write_json(
            {
                "ok": False,
                "error": "docker_update_unsupported",
                "message": "This Hermes installation is managed by fnOS. Please update Hermes from fnOS App Center.",
                "update_command": "Update Hermes from fnOS App Center",
            },
            status=HTTPStatus.OK,
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self._write_json(self.context.system_status())
            return
        if not self._is_gateway_authenticated_admin():
            self._write_forbidden()
            return
        if parsed.path == "/api/v1/status":
            self._write_json(self.context.system_status())
            return
        if parsed.path == "/api/v1/config":
            self._write_json({"ok": True, "config": self.context.load_setup_summary()})
            return
        if parsed.path == "/api/v1/config/test":
            self._write_json(self.context.config_test(), status=None)
            return
        if parsed.path == "/api/v1/platforms":
            self._write_json(self.context.platforms_payload(), status=None)
            return
        if parsed.path == "/api/v1/platforms/schema":
            self._write_json(self.context.platform_schema_payload(), status=None)
            return
        if parsed.path.startswith("/api/v1/platforms/"):
            platform_id = urllib.parse.unquote(parsed.path[len("/api/v1/platforms/") :]).strip("/")
            if platform_id in CHAT_PLATFORM_SCHEMAS:
                self._write_json(self.context.platform_payload(platform_id), status=None)
                return
        if parsed.path == "/api/v1/logs":
            query = urllib.parse.parse_qs(parsed.query)
            log_name = query.get("name", ["control"])[0]
            try:
                line_count = int(query.get("lines", [str(DEFAULT_LOG_TAIL_LINES)])[0])
            except ValueError:
                line_count = DEFAULT_LOG_TAIL_LINES
            self._write_json(self.context.logs_payload(log_name, line_count))
            return
        if parsed.path == "/api/v1/sessions":
            query = urllib.parse.parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["20"])[0])
            except ValueError:
                limit = 20
            try:
                offset = int(query.get("offset", ["0"])[0])
            except ValueError:
                offset = 0
            self._write_json(self.context.sessions_payload(limit, offset), status=None)
            return
        if parsed.path.startswith("/api/v1/sessions/") and parsed.path.endswith("/messages"):
            session_id = urllib.parse.unquote(parsed.path[len("/api/v1/sessions/") : -len("/messages")]).strip("/")
            payload, status = self.context.session_messages_payload(session_id)
            self._write_json(payload, status=status)
            return
        if parsed.path == "/api/v1/models":
            self._write_json(self.context.models(), status=None)
            return
        self._proxy_dashboard_request("GET")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if not self._is_gateway_authenticated_admin():
            self._write_forbidden()
            return
        if parsed.path == "/api/hermes/update":
            self._write_update_blocked()
            return
        if not parsed.path.startswith("/api/v1/"):
            self._proxy_dashboard_request("POST")
            return

        payload = self._read_json_body()
        if parsed.path == "/api/v1/config":
            self._write_json({"ok": True, "config": self.context.save_setup(payload)})
            return
        if parsed.path == "/api/v1/config/test":
            self._write_json(self.context.config_test(payload), status=None)
            return
        if parsed.path.startswith("/api/v1/platforms/") and parsed.path.endswith("/test"):
            platform_id = urllib.parse.unquote(parsed.path[len("/api/v1/platforms/") : -len("/test")]).strip("/")
            self._write_json(self.context.test_platform_connection(platform_id, payload), status=None)
            return
        if parsed.path.startswith("/api/v1/platforms/"):
            platform_id = urllib.parse.unquote(parsed.path[len("/api/v1/platforms/") :]).strip("/")
            self._write_json(self.context.save_platform(platform_id, payload), status=None)
            return
        if parsed.path == "/api/v1/runtime/start":
            self._write_json(self.context.start_gateway(), status=None)
            return
        if parsed.path == "/api/v1/runtime/stop":
            self._write_json(self.context.stop_gateway(), status=None)
            return
        if parsed.path == "/api/v1/runtime/restart":
            self._write_json(self.context.restart_gateway(), status=None)
            return
        if parsed.path == "/api/v1/chat":
            self._write_json(self.context.chat(payload), status=None)
            return
        self._proxy_dashboard_request("POST")

    def do_PUT(self) -> None:  # noqa: N802
        if not self._is_gateway_authenticated_admin():
            self._write_forbidden()
            return
        self._proxy_dashboard_request("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        if not self._is_gateway_authenticated_admin():
            self._write_forbidden()
            return
        self._proxy_dashboard_request("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._is_gateway_authenticated_admin():
            self._write_forbidden()
            return
        self._proxy_dashboard_request("DELETE")

    def log_message(self, fmt: str, *args: Any) -> None:
        logging.info("%s - %s", self.address_string(), fmt % args)

    def address_string(self) -> str:
        if isinstance(self.client_address, tuple) and self.client_address:
            return str(self.client_address[0])
        return "fnos-gateway"

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0").strip() or "0"
        try:
            length = int(raw_length)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        if not body:
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}

    def _write_json(self, payload: dict[str, Any], status: HTTPStatus | None = HTTPStatus.OK) -> None:
        http_status = status if status is not None else (HTTPStatus.OK if payload.get("ok", True) else HTTPStatus.BAD_REQUEST)
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(http_status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy_dashboard_request(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if not self.context.dashboard_status().get("running"):
            started = self.context.start_dashboard()
            if not started.get("ok"):
                self._write_json(started, status=HTTPStatus.BAD_GATEWAY)
                return

        if (self.headers.get("Upgrade") or "").strip().lower() == "websocket":
            self._proxy_dashboard_websocket(method)
            return

        target_url = self.context.dashboard_base_url() + self.path
        body = None
        if method.upper() in {"POST", "PUT", "PATCH"}:
            raw_length = self.headers.get("Content-Length", "0").strip() or "0"
            try:
                length = int(raw_length)
            except ValueError:
                length = 0
            if length > 0:
                body = self.rfile.read(length)

        headers: dict[str, str] = {}
        for key, value in self.headers.items():
            lower_key = key.lower()
            if lower_key in self.hop_by_hop_headers or lower_key == "host":
                continue
            headers[key] = value
        headers["Host"] = f"{self.context.dashboard_host}:{self.context.dashboard_port}"
        headers["X-Forwarded-Prefix"] = "/app/trim-hermes"
        headers["X-Forwarded-For"] = self.client_address[0] if self.client_address else ""

        request = urllib.request.Request(target_url, data=body, method=method.upper(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response_body = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() in self.hop_by_hop_headers:
                        continue
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(response_body)
        except urllib.error.HTTPError as exc:
            response_body = exc.read()
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() in self.hop_by_hop_headers:
                    continue
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(response_body)
        except Exception as exc:  # noqa: BLE001
            logging.warning("dashboard proxy failed for %s %s: %s", method, parsed.path, exc)
            self._write_json(
                {
                    "ok": False,
                    "error": "dashboard_proxy_failed",
                    "message": str(exc),
                },
                status=HTTPStatus.BAD_GATEWAY,
            )

    def _proxy_dashboard_websocket(self, method: str) -> None:
        try:
            upstream = socket.create_connection((self.context.dashboard_host, self.context.dashboard_port), timeout=10)
        except OSError as exc:
            logging.warning("dashboard websocket connect failed: %s", exc)
            self._write_json(
                {
                    "ok": False,
                    "error": "dashboard_websocket_connect_failed",
                    "message": str(exc),
                },
                status=HTTPStatus.BAD_GATEWAY,
            )
            return

        try:
            upstream_file = upstream.makefile("rwb", buffering=0)
            path = self.path or "/"
            request_lines = [f"{method.upper()} {path} HTTP/1.1\r\n"]
            for key, value in self.headers.items():
                lower_key = key.lower()
                if lower_key == "host":
                    request_lines.append(f"Host: {self.context.dashboard_host}:{self.context.dashboard_port}\r\n")
                    continue
                if lower_key in {"proxy-authorization", "proxy-authenticate"}:
                    continue
                request_lines.append(f"{key}: {value}\r\n")
            if not any(line.lower().startswith("host:") for line in request_lines):
                request_lines.append(f"Host: {self.context.dashboard_host}:{self.context.dashboard_port}\r\n")
            request_lines.append("X-Forwarded-Prefix: /app/trim-hermes\r\n")
            request_lines.append(f"X-Forwarded-For: {self.client_address[0] if isinstance(self.client_address, tuple) and self.client_address else ''}\r\n")
            request_lines.append("\r\n")
            upstream_file.write("".join(request_lines).encode("iso-8859-1"))

            sockets = [self.connection, upstream]
            while True:
                readable, _, errored = select.select(sockets, [], sockets, 60)
                if errored or not readable:
                    break
                for sock in readable:
                    data = sock.recv(65536)
                    if not data:
                        return
                    target = upstream if sock is self.connection else self.connection
                    target.sendall(data)
        except OSError as exc:
            logging.info("dashboard websocket tunnel closed: %s", exc)
        finally:
            try:
                upstream.close()
            except OSError:
                pass


class ControlPlaneServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[ControlPlaneHandler],
        control_context: HermesControlContext,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.control_context = control_context


class UnixControlPlaneServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        socket_path: str,
        handler_class: type[ControlPlaneHandler],
        control_context: HermesControlContext,
    ) -> None:
        socket_file = Path(socket_path)
        socket_file.parent.mkdir(parents=True, exist_ok=True)
        if socket_file.exists():
            socket_file.unlink()
        super().__init__(socket_path, handler_class)
        self.control_context = control_context

    def server_close(self) -> None:
        socket_path = Path(str(self.server_address))
        super().server_close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="trim.hermes fnOS control plane")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_CONTROL_PORT)
    parser.add_argument("--socket", default="", help="Unix socket path for fnOS gateway mode")
    parser.add_argument("--dashboard-host", default=DEFAULT_DASHBOARD_HOST)
    parser.add_argument("--dashboard-port", type=int, default=DEFAULT_DASHBOARD_PORT)
    parser.add_argument("--app-root", required=True)
    parser.add_argument("--data-root", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = RuntimePaths.from_roots(
        app_root=Path(args.app_root).resolve(),
        data_root=Path(args.data_root).resolve(),
    )
    ensure_runtime_layout(paths)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(paths.control_log_file),
            logging.StreamHandler(),
        ],
    )

    context = HermesControlContext(
        paths,
        control_host=args.host,
        control_port=args.port,
        dashboard_host=args.dashboard_host,
        dashboard_port=args.dashboard_port,
    )
    handler = lambda *a, **kw: ControlPlaneHandler(*a, directory=str(paths.web_root), **kw)
    if args.socket:
        server = UnixControlPlaneServer(args.socket, handler, context)
    else:
        server = ControlPlaneServer((args.host, args.port), handler, context)

    shutdown_started = {"value": False}

    def initiate_shutdown(signum: int) -> None:
        if shutdown_started["value"]:
            return
        shutdown_started["value"] = True
        logging.info("received signal %s, shutting down trim.hermes control plane", signum)

        def _worker() -> None:
            context.shutdown()
            server.shutdown()

        threading.Thread(target=_worker, daemon=True).start()

    def handle_signal(signum: int, _frame: Any) -> None:
        initiate_shutdown(signum)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    if args.socket:
        logging.info("starting trim.hermes control plane on unix socket %s", args.socket)
    else:
        logging.info("starting trim.hermes control plane on %s:%s", args.host, args.port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        logging.info("trim.hermes control plane stopped")


if __name__ == "__main__":
    main()
