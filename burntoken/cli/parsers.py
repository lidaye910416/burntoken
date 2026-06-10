"""argparse builders for burntoken CLI.

Each `add_<cmd>_parser` function attaches arguments to a subparser. The
top-level `build_parser` wires them all together and returns the parser.
"""
from __future__ import annotations

import argparse

from .._version import __version__
from ..presets import list_names
from ..tasks import list_tasks


def _common_log_file(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--log-file",
        default=None,
        metavar="PATH",
        help="把每次调用的结构化事件（JSONL）追加到 PATH",
    )


def add_run_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("run", help="单次调用（默认命令）")
    p.add_argument("-p", "--prompt", help="用户消息")
    p.add_argument("-s", "--system", help="系统消息")
    p.add_argument("-m", "--model", help="模型名（默认 HBS_MODEL）")
    p.add_argument("-t", "--temperature", type=float, default=1.0)
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--stream", action="store_true", help="流式输出")
    p.add_argument("--save", help="把结果落盘到 jsonl")
    p.add_argument("--preset", choices=list_names(), help="套用预设的 system prompt")
    _common_log_file(p)
    return p


def add_burn_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("burn", help="批量烧：N 次请求，P 个并发")
    p.add_argument("-n", "--count", type=int, default=10)
    p.add_argument("-P", "--parallel", type=int, default=2)
    p.add_argument("--preset", choices=list_names(), default="chat")
    p.add_argument("--multi-turn", type=int, default=6, help="longctx 模式：塞入 N 轮历史")
    p.add_argument("-m", "--model", help="模型名（默认 HBS_MODEL）")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--save", help="把每条结果落盘到 jsonl")
    p.add_argument("--max-tokens", type=int, default=None, help="预算：总 token 阈值")
    p.add_argument("--max-cost", type=float, default=None, help="预算：总成本阈值")
    _common_log_file(p)
    return p


def add_repl_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("repl", help="交互式 REPL")
    p.add_argument("-m", "--model", help="模型名（默认 HBS_MODEL）")
    p.add_argument("-s", "--system", help="系统消息")
    p.add_argument("-t", "--temperature", type=float, default=1.0)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--max-history", type=int, default=20, help="最多保留多少轮对话")
    _common_log_file(p)
    return p


def add_models_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    return sub.add_parser("models", help="列出已配置 provider 上的模型")


def add_config_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("config", help="配置管理: show/init/path")
    p.add_argument("action", choices=["show", "init", "path"])
    return p


def add_providers_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    return sub.add_parser("providers", help="列出所有已配置 provider")


def add_use_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("use", help="切换默认 provider（写到 ~/.config/burntoken/active）")
    p.add_argument("name", help="provider 名字")
    return p


def add_team_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser(
        "team", help="Agent team: Strategist→Dispatcher→Accountant→Reviewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "mode:\n"
            "  meaningful   真实任务（review/docs/tests/...）\n"
            "  pointless   无意义合成 prompt\n"
            "  mixed       一半一半\n\n"
            "示例:\n"
            "  burntoken team --mode meaningful -n 5\n"
            "  burntoken team --mode pointless -n 100 -P 4\n"
            "  burntoken team --mode mixed -n 20 --max-tokens 100000\n"
        ),
    )
    p.add_argument("--mode", choices=["meaningful", "pointless", "mixed"],
                   default=None, help="烧的模式（默认从 config 读）")
    p.add_argument("-n", "--count", type=int, default=10)
    p.add_argument("-P", "--parallel", type=int, default=2)
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--max-tokens-per-file", type=int, default=None,
                   help="单次调用最大输出 token（覆盖任务的默认值）")
    p.add_argument("--max-cost", type=float, default=None)
    p.add_argument("--provider", default=None, help="用哪个 provider（默认 default_provider）")
    p.add_argument("--model", default=None, help="用哪个模型（默认 provider 的 default_model）")
    p.add_argument("--no-reviewer", action="store_true", help="关闭 Reviewer agent")
    p.add_argument("--save", help="落盘 jsonl")
    p.add_argument("--quiet", action="store_true", help="不打印每次明细")
    return p


def add_review_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser(
        "review", help="review 整个项目：本地路径 / github:user/repo / URL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "目标形式:\n"
            "  ./local/project                 本地目录/文件\n"
            "  /abs/path                       绝对路径\n"
            "  github:user/repo                GitHub 仓库（自动 clone 到缓存）\n"
            "  github:user/repo/src/api        仓库的子路径\n"
            "  https://github.com/user/repo    URL\n"
            "  git@github.com:user/repo.git    SSH\n"
            "  -                               stdin\n\n"
            "示例:\n"
            "  burntoken review .\n"
            "  burntoken review github:fastapi/fastapi --ext py -P 4\n"
            "  burntoken review github:pallets/flask/src --ref main\n"
            "  burntoken review https://github.com/psf/requests -n 10\n"
        ),
    )
    p.add_argument("target", help="路径 / github:user/repo / URL / -")
    p.add_argument("--ref", default="HEAD", help="git ref (branch/tag/sha)")
    p.add_argument("--refresh", action="store_true", help="强制重新 clone")
    p.add_argument("--no-cache", action="store_true", help="不用缓存")
    p.add_argument("--cache-dir", default=None, help="覆盖缓存目录")
    p.add_argument("--ext", default=None, help="文件扩展名 (默认 py)")
    p.add_argument("--recursive/--no-recursive", dest="recursive",
                   action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("-m", "--model", help="模型名")
    p.add_argument("-n", "--count", type=int, default=None)
    p.add_argument("-P", "--parallel", type=int, default=2)
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--max-cost", type=float, default=None)
    p.add_argument("--max-tokens-per-file", type=int, default=None)
    p.add_argument("--max-bytes", type=int, default=200_000)
    p.add_argument("--save", help="结果落盘 jsonl")
    p.add_argument("--out-dir", help="输出目录（自动按源命名）")
    p.add_argument("--show", action="store_true")
    p.add_argument("--show-chars", type=int, default=800)
    p.add_argument("--seed", type=int, default=None)
    return p


def add_work_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser(
        "work", help="真实任务烧：review/docs/tests/... 真干活",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  burntoken work review src/main.py\n"
            "  burntoken work docs src/ --ext py --out-dir docs/\n"
            "  burntoken work tests burntoken/*.py -P 4\n"
            "  burntoken work review --git staged\n"
            "  burntoken work commit --git staged\n"
            "  burntoken work explain burntoken/client.py --show\n"
            "  cat foo.py | burntoken work review -\n"
        ),
    )
    p.add_argument("task", choices=list_tasks(), help="任务类型")
    p.add_argument("path", nargs="?", default="-",
                   help="文件/目录/glob，- 表示 stdin")
    p.add_argument("--git", choices=["staged", "working", "branch", "range"],
                   default=None, help="从 git 读取输入")
    p.add_argument("--git-ref", default="HEAD", help="配合 --git branch/range")
    p.add_argument("--ext", default=None,
                   help="目录模式下只处理此扩展名（默认 py）")
    p.add_argument("--recursive/--no-recursive", dest="recursive",
                   action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("-m", "--model", help="模型名（默认 HBS_MODEL）")
    p.add_argument("-n", "--count", type=int, default=None,
                   help="最多处理 N 个文件")
    p.add_argument("-P", "--parallel", type=int, default=2)
    p.add_argument("--max-tokens", type=int, default=None,
                   help="累计 token 阈值熔断")
    p.add_argument("--max-cost", type=float, default=None,
                   help="累计成本阈值熔断")
    p.add_argument("--max-tokens-per-file", type=int, default=None,
                   help="覆盖任务默认的 max_tokens")
    p.add_argument("--max-bytes", type=int, default=200_000,
                   help="单个文件最大读取字节数")
    p.add_argument("--save", help="所有结果落盘到 jsonl")
    p.add_argument("--out-dir", help="把每个文件输出写到该目录")
    p.add_argument("--show", action="store_true", help="把回复打到终端")
    p.add_argument("--show-chars", type=int, default=800,
                   help="--show 模式下每条最多打多少字符")
    p.add_argument("--seed", type=int, default=None)
    _common_log_file(p)
    return p


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser. Order of subcommands is preserved to
    keep --help output identical to the pre-refactor monolithic cli.py."""
    p = argparse.ArgumentParser(
        prog="burntoken",
        description="直接调 hbscloud 接口的 Token 燃烧器（无需 Claude Code / LiteLLM）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  burntoken -p "hello"
  burntoken -p "写首诗" --stream --model gpt-4o
  burntoken --burntoken --preset math --count 20 --parallel 4
  burntoken --repl --model gpt-4o --max-tokens 1024
  burntoken --models
""",
    )
    p.add_argument("--version", action="version", version=f"burntoken {__version__}")
    p.add_argument(
        "--log-file",
        default=None,
        metavar="PATH",
        help="把每次调用的结构化事件（JSONL）追加到 PATH，每行一个 event object；"
             "默认走人类可读的 stderr logger。",
    )
    sub = p.add_subparsers(dest="cmd")
    add_run_parser(sub)
    add_burn_parser(sub)
    add_repl_parser(sub)
    add_models_parser(sub)
    add_config_parser(sub)
    add_providers_parser(sub)
    add_use_parser(sub)
    add_team_parser(sub)
    add_review_parser(sub)
    add_work_parser(sub)
    return p
