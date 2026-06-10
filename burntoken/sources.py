"""目标解析：把 '本地路径 / github:user/repo / https://... / - (stdin)' 统一成本地路径。

克隆走 ~/.cache/burntoken/<host>/<owner>/<repo>/<ref>/，默认浅克隆（--depth 1）。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse


# ============================================================================
#  公开类型
# ============================================================================

@dataclass
class Resolved:
    """解析后的目标。"""
    kind: str            # "local" | "github" | "gitlab" | "bitbucket" | "url" | "stdin"
    local_path: str      # 本地绝对路径（stdin 时为 None）
    display_name: str    # 用于 out-dir 文件名前缀
    subpath: str = ""    # github shorthand 的子路径，拼接时清掉
    ref: str = "HEAD"    # 实际用的 git ref


# ============================================================================
#  常量
# ============================================================================

DEFAULT_CACHE_DIR = os.environ.get(
    "BURNTOKEN_CACHE_DIR", os.path.expanduser("~/.cache/burntoken")
)


# ============================================================================
#  git 工具
# ============================================================================

def _git_available() -> bool:
    return shutil.which("git") is not None


def _run_git(args, cwd: Optional[str] = None, timeout: int = 120) -> Tuple[bool, str, str]:
    try:
        r = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True,
            text=True, encoding="utf-8", timeout=timeout, check=False,
        )
        return r.returncode == 0, r.stdout, r.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, "", str(e)


# ============================================================================
#  缓存管理
# ============================================================================

def _cache_path(host: str, owner: str, repo: str, ref: str) -> str:
    safe_ref = ref.replace("/", "_").replace("..", "_")
    return os.path.join(DEFAULT_CACHE_DIR, host, owner, repo, safe_ref)


def _is_cached(path: str) -> bool:
    return os.path.isdir(path) and os.path.isdir(os.path.join(path, ".git"))


def _clone(url: str, target: str, ref: str) -> None:
    """浅克隆到 target。"""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if not _git_available():
        raise RuntimeError("找不到 git 命令，请先安装 git")
    ok, _, err = _run_git(["clone", "--depth", "1", url, target], timeout=300)
    if not ok:
        raise RuntimeError(f"git clone 失败：{err.strip() or url}")
    # 如果指定了非默认 ref，再 fetch + checkout
    if ref and ref not in ("HEAD", "main", "master"):
        ok, _, err = _run_git(["fetch", "--depth", "1", "origin", ref], cwd=target)
        if not ok:
            # ref 不存在就回退
            return
        _run_git(["checkout", "FETCH_HEAD"], cwd=target)


def _refresh(path: str, ref: str) -> None:
    """从已 clone 的目录拉取最新。"""
    _run_git(["fetch", "--depth", "1", "origin", ref], cwd=path, timeout=120)
    _run_git(["reset", "--hard", f"origin/{ref}"], cwd=path, timeout=60)


# ============================================================================
#  URL 解析
# ============================================================================

def _parse_github_url(url: str) -> Optional[Tuple[str, str, str, Optional[str]]]:
    """解析 https://github.com/owner/repo[.git][/sub/path][@ref] → (host, owner, repo, subpath)
    失败返回 None。
    """
    # 去掉尾部 .git 和 #frag
    url = url.split("#", 1)[0]
    if url.endswith(".git"):
        url = url[:-4]
    if "github.com" not in url:
        return None
    try:
        p = urlparse(url)
    except ValueError:
        return None
    if not p.path:
        return None
    parts = [seg for seg in p.path.split("/") if seg]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    subpath = "/".join(parts[2:]) if len(parts) > 2 else None
    return ("github.com", owner, repo, subpath)


def _parse_git_shorthand(target: str) -> Optional[Tuple[str, str, str, Optional[str]]]:
    """解析 github:user/repo[/subpath] / gitlab:user/repo 等。"""
    if ":" not in target:
        return None
    scheme, rest = target.split(":", 1)
    scheme = scheme.lower()
    if scheme not in ("github", "gitlab", "bitbucket", "git"):
        return None
    parts = [seg for seg in rest.split("/") if seg]
    if len(parts) < 2:
        return None
    host = {
        "github": "github.com",
        "gitlab": "gitlab.com",
        "bitbucket": "bitbucket.org",
    }.get(scheme, scheme + ".com")
    if scheme == "git":
        # git:host/owner/repo → host = parts[0]
        host = parts[0]
        parts = parts[1:]
        if len(parts) < 2:
            return None
    owner, repo = parts[0], parts[1]
    subpath = "/".join(parts[2:]) if len(parts) > 2 else None
    return (host, owner, repo, subpath)


# ============================================================================
#  主入口
# ============================================================================

def resolve_target(
    target: str,
    *,
    ref: str = "HEAD",
    refresh: bool = False,
    no_cache: bool = False,
    cache_dir: Optional[str] = None,
    print_actions: bool = True,
) -> Resolved:
    """把 target 解析成本地路径。

    target 支持：
      - "-"                                 stdin
      - "/abs/path" or "./rel" or "../rel"  本地路径
      - "github:user/repo"                  GitHub shorthand
      - "github:user/repo/sub/path"         GitHub 仓库的子路径
      - "https://github.com/user/repo"      URL
      - "git@github.com:user/repo.git"      SSH

    返回的 local_path 一定存在（stdin 例外）。
    """
    if cache_dir:
        global DEFAULT_CACHE_DIR
        DEFAULT_CACHE_DIR = cache_dir

    # ---- stdin ----
    if target == "-":
        return Resolved(kind="stdin", local_path="", display_name="stdin")

    # ---- GitHub shorthand (github:user/repo[/subpath]) ----
    parsed = _parse_git_shorthand(target)
    if parsed is not None:
        host, owner, repo, subpath = parsed
        return _resolve_clone(
            host=host, owner=owner, repo=repo, subpath=subpath,
            ref=ref, refresh=refresh, no_cache=no_cache,
            url=f"https://{host}/{owner}/{repo}.git",
            print_actions=print_actions,
        )

    # ---- URL ----
    if target.startswith(("http://", "https://", "git@", "ssh://")):
        gh = _parse_github_url(target)
        if gh is not None:
            host, owner, repo, subpath = gh
            return _resolve_clone(
                host=host, owner=owner, repo=repo, subpath=subpath,
                ref=ref, refresh=refresh, no_cache=no_cache,
                url=target, print_actions=print_actions,
            )
        # 任意 git URL：按 urlparse 解析
        p = urlparse(target)
        host = p.hostname or "unknown"
        parts = [seg for seg in (p.path or "").split("/") if seg]
        if len(parts) < 2:
            raise ValueError(f"无法解析 URL：{target}")
        owner, repo = parts[-2], parts[-1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        return _resolve_clone(
            host=host, owner=owner, repo=repo, subpath=None,
            ref=ref, refresh=refresh, no_cache=no_cache,
            url=target, print_actions=print_actions,
        )

    # ---- 本地路径 ----
    abs_path = os.path.abspath(os.path.expanduser(target))
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"路径不存在：{abs_path}")
    name = os.path.basename(abs_path.rstrip("/")) or "root"
    if name == ".":
        name = os.path.basename(os.getcwd())
    return Resolved(
        kind="local",
        local_path=abs_path,
        display_name=name,
        ref="",
    )


def _resolve_clone(
    *, host, owner, repo, subpath, ref, refresh, no_cache, url, print_actions,
) -> Resolved:
    """下载/复用 git 仓库，并定位到子路径。"""
    cache_root = DEFAULT_CACHE_DIR
    if no_cache:
        target = tempfile.mkdtemp(prefix=f"burntoken-{owner}-{repo}-")
        clone_target = target
        ephemeral = True
    else:
        clone_target = _cache_path(host, owner, repo, ref)
        ephemeral = False

    if _is_cached(clone_target) and not refresh:
        if print_actions:
            print(f"  ✓ cache hit: {clone_target}")
    else:
        if print_actions:
            print(f"  ↓ cloning {url} → {clone_target} ...")
        _clone(url, clone_target, ref)
        if print_actions:
            print(f"  ✓ cloned to {clone_target}")

    if subpath:
        sub_abs = os.path.join(clone_target, subpath)
        if not os.path.isdir(sub_abs):
            raise FileNotFoundError(
                f"子路径不存在：{subpath}\n  在 {clone_target} 中找不到"
            )
        local_path = sub_abs
        sub_norm = subpath.replace("/", "_")
        name = f"{owner}__{repo}__{sub_norm}"
    else:
        local_path = clone_target
        name = f"{owner}__{repo}"

    return Resolved(
        kind="github" if host == "github.com" else host.split(".")[0],
        local_path=local_path,
        display_name=name,
        subpath=subpath or "",
        ref=ref,
    )
