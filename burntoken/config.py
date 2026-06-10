"""TOML 配置 + 多 provider 管理。

默认路径:
  - macOS/Linux:  $XDG_CONFIG_HOME/burntoken/config.toml  或  ~/.config/burntoken/config.toml
  - 覆盖:         BURNTOKEN_CONFIG 环境变量

也兼容旧的 .env（仅作 fallback）。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:  # Python 3.10
    import tomli as tomllib  # type: ignore

from .tracker import TokenPricing


# ---------------------------------------------------------------------------
#  数据类
# ---------------------------------------------------------------------------

@dataclass
class ProviderSpec:
    """单个 provider 的完整配置。"""
    name: str
    type: str = "openai"            # openai | anthropic
    api_key: str = ""
    base_url: Optional[str] = None
    default_model: str = ""
    timeout: float = 180.0
    verify: bool = True    # 关闭 SSL 验证（hbscloud 证书场景）
    pricing: TokenPricing = field(default_factory=TokenPricing)
    extra: Dict[str, str] = field(default_factory=dict)


@dataclass
class TeamConfig:
    """Agent team 默认配置。"""
    mode: str = "meaningful"        # meaningful | pointless | mixed
    parallel: int = 2
    strategist_provider: Optional[str] = None
    strategist_model: Optional[str] = None


@dataclass
class Config:
    """整个配置文件反序列化后的对象。"""
    default_provider: Optional[str] = None
    providers: Dict[str, ProviderSpec] = field(default_factory=dict)
    team: TeamConfig = field(default_factory=TeamConfig)
    config_path: Optional[str] = None

    def get_provider(self, name: Optional[str] = None) -> ProviderSpec:
        name = name or self.default_provider
        if not name:
            raise ValueError("未指定 provider，且 default_provider 未设置")
        if name not in self.providers:
            raise KeyError(f"provider 未配置：{name!r}（已配置：{list(self.providers)}）")
        return self.providers[name]

    def default(self) -> ProviderSpec:
        return self.get_provider(self.default_provider)


# ---------------------------------------------------------------------------
#  路径解析
# ---------------------------------------------------------------------------

def default_config_path() -> Optional[Path]:
    # 1. env
    env = os.environ.get("BURNTOKEN_CONFIG")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p
    # 2. XDG
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    p = Path(xdg) / "burntoken" / "config.toml"
    if p.exists():
        return p
    # 3. ~/.config/burntoken
    p2 = Path.home() / ".config" / "burntoken" / "config.toml"
    if p2.exists():
        return p2
    return None


# ---------------------------------------------------------------------------
#  解析
# ---------------------------------------------------------------------------

_PRICING_KEYS = ("prompt_per_1k", "completion_per_1k", "input_per_1k", "output_per_1k")


def _parse_pricing(d: dict) -> TokenPricing:
    return TokenPricing(
        prompt_per_1k=float(d.get("prompt_per_1k", d.get("input_per_1k", 0)) or 0),
        completion_per_1k=float(d.get("completion_per_1k", d.get("output_per_1k", 0)) or 0),
    )


def _parse_provider(name: str, d: dict) -> ProviderSpec:
    extra = {k: v for k, v in d.items()
             if k not in {"type", "api_key", "base_url", "default_model",
                          "timeout", "prompt_per_1k", "completion_per_1k",
                          "input_per_1k", "output_per_1k"}}
    return ProviderSpec(
        name=name,
        type=d.get("type", "openai"),
        api_key=_resolve_env(d.get("api_key", "")),
        base_url=d.get("base_url"),
        default_model=d.get("default_model", ""),
        timeout=float(d.get("timeout", 180) or 180),
        verify=bool(d.get("verify", True)),
        pricing=_parse_pricing(d),
        extra=extra,
    )


_ENV_REF = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}|\$([A-Z_][A-Z0-9_]*)")


def _resolve_env(value: str) -> str:
    """把 ${VAR} / $VAR 替换成环境变量。"""
    if not isinstance(value, str) or "$" not in value:
        return value
    def repl(m):
        var = m.group(1) or m.group(2)
        return os.environ.get(var, m.group(0))
    return _ENV_REF.sub(repl, value)


def load_config(path: Optional[str] = None) -> Config:
    """加载配置。如果文件不存在，返回一个空 Config（允许走 .env fallback）。"""
    p = Path(path).expanduser() if path else default_config_path()
    cfg = Config(config_path=str(p) if p else None)
    if not p or not p.exists():
        return cfg
    with open(p, "rb") as f:
        raw = tomllib.load(f)
    cfg.default_provider = raw.get("default_provider")
    for name, spec in (raw.get("providers") or {}).items():
        cfg.providers[name] = _parse_provider(name, spec)
    if "team" in raw:
        td = raw["team"]
        cfg.team = TeamConfig(
            mode=td.get("mode", "meaningful"),
            parallel=int(td.get("parallel", 2) or 2),
            strategist_provider=td.get("strategist_provider"),
            strategist_model=td.get("strategist_model"),
        )
    return cfg


# ---------------------------------------------------------------------------
#  HBS_* direct env resolution (read-only, pure)
# ---------------------------------------------------------------------------

_HBS_VERIFY_TRUTHY = frozenset({"1", "true", "yes", "on"})
_HBS_VERIFY_FALSY = frozenset({"0", "false", "no", "off"})
_HBS_BASE_URL_DEFAULT = "https://model.hbscloud.com.cn/v1"


def _truthy(value: str) -> bool:
    """Parse a CLI/env boolean. ``"false"``/``"0"``/``"no"``/``"off"`` → False.

    Whitespace is stripped; case is ignored. Anything that is *not* a known
    falsy spelling is treated as truthy — matches shell conventions where
    "set" means "true".
    """
    s = (value or "").strip().lower()
    if s in _HBS_VERIFY_FALSY:
        return False
    if s in _HBS_VERIFY_TRUTHY:
        return True
    # Unknown spellings default to truthy (matches common shell behaviour).
    return bool(s)


def load_hbs_env(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Read HBS_* environment variables into a plain dict.

    The helper is pure: it does not mutate ``os.environ`` (callers that want
    .env-side-effect behaviour should use :func:`load_env_fallback`).

    Returned keys (always present):

    * ``api_key``       — ``HBS_API_KEY`` or ``""``
    * ``base_url``      — ``HBS_BASE_URL`` or canonical hbscloud default
    * ``model``         — ``HBS_MODEL`` or ``""``
    * ``verify``        — ``HBS_VERIFY`` parsed as bool; **default ``False``**
                         (hbscloud cert chain is broken; opt in to enable)
    * ``pricing``       — :class:`TokenPricing` from HBS_PRICE_PROMPT /
                         HBS_PRICE_COMPLETION (default 0/0)
    * ``env_path``      — ``None`` (this helper does not touch disk)
    """
    src = env if env is not None else os.environ
    api_key = src.get("HBS_API_KEY", "") or ""
    base_url = src.get("HBS_BASE_URL") or _HBS_BASE_URL_DEFAULT
    model = src.get("HBS_MODEL", "") or ""
    verify_raw = src.get("HBS_VERIFY", "false")
    verify = _truthy(verify_raw) if verify_raw.strip() else False
    pricing = TokenPricing(
        prompt_per_1k=float(src.get("HBS_PRICE_PROMPT", "0") or 0),
        completion_per_1k=float(src.get("HBS_PRICE_COMPLETION", "0") or 0),
    )
    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "verify": verify,
        "pricing": pricing,
        "env_path": None,
    }


def load_env_fallback() -> Dict[str, str]:
    """从 .env 读 HBS_API_KEY 等（保持向后兼容）。"""
    candidates = [
        os.path.expanduser("~/claude-code-hbscloud/.env"),
        os.path.expanduser("~/.claude-code-hbscloud/.env"),
        "/Users/jasonlee/claude-code-hbscloud/.env",
        os.path.join(os.getcwd(), ".env"),
    ]
    out: Dict[str, str] = {}
    for c in candidates:
        if not os.path.exists(c):
            continue
        with open(c) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    out[k] = v
        break
    return out


def ensure_default_config() -> Path:
    """如果配置不存在，写一份带注释的模板。"""
    p = default_config_path()
    if p is None:
        xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        p = Path(xdg) / "burntoken" / "config.toml"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(_TEMPLATE)
    return p


_TEMPLATE = '''# burntoken 主配置 · 多个 provider 自由切换
# 文档: https://github.com/your/repo  (示意)

default_provider = "hbscloud"

# ---------------------------------------------------------------
# Provider 1: hbscloud (OpenAI 兼容)
# ---------------------------------------------------------------
[providers.hbscloud]
type           = "openai"
base_url       = "https://model.hbscloud.com.cn/v1"
api_key        = "${HBS_API_KEY}"            # 优先从环境变量读
default_model  = "hbscloud-deepseek"
timeout        = 180
verify         = false                       # hbscloud 证书链有问题，关掉
prompt_per_1k  = 0.001                       # 用于成本估算
completion_per_1k = 0.002

# ---------------------------------------------------------------
# Provider 2: Anthropic 直连
# ---------------------------------------------------------------
[providers.anthropic]
type           = "anthropic"
api_key        = "${ANTHROPIC_API_KEY}"
default_model  = "claude-3-5-sonnet-20241022"
timeout        = 180

# ---------------------------------------------------------------
# Provider 3: OpenAI 官方
# ---------------------------------------------------------------
[providers.openai]
type           = "openai"
base_url       = "https://api.openai.com/v1"
api_key        = "${OPENAI_API_KEY}"
default_model  = "gpt-4o"

# ---------------------------------------------------------------
# Agent team 默认
# ---------------------------------------------------------------
[team]
mode                   = "meaningful"        # meaningful | pointless | mixed
parallel               = 2
# strategist_provider = "hbscloud"          # 不填则用 default_provider
# strategist_model    = "hbscloud-deepseek"
'''


# ---------------------------------------------------------------------------
#  CLI helper: 临时改 active provider
# ---------------------------------------------------------------------------

_ACTIVE_FILE = Path.home() / ".config" / "burntoken" / "active"


def set_active(name: str) -> None:
    _ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ACTIVE_FILE.write_text(name)


def get_active() -> Optional[str]:
    if _ACTIVE_FILE.exists():
        return _ACTIVE_FILE.read_text().strip() or None
    return None
