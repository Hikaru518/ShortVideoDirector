#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "python-frontmatter>=1.1",
#   "PyYAML>=6.0",
# ]
# ///
"""tools/build.py — 双端产物构建器（骨架）。

按 tools/runtime-config.yml 的规则，将 src/{skills,agents,workflows}/
canonical 源转换为 .claude/{skills,agents}/ + .opencode/{skills,commands,agents}/
两端产物。

本文件目前是 TASK-001 引入的骨架，仅提供 CLI 参数解析；业务构建逻辑由
后续 TASK-005~008 实现。
"""

# NOTE(TASK-001): stub 阶段不要 import python-frontmatter / yaml；这两个依赖
# 只能在 `uv run` 环境中通过 PEP 723 头自动拉取。直接 `python3 tools/build.py`
# 时 stdlib 之外的 import 会失败。骨架只用 argparse / sys。

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build.py",
        description=(
            "构建 Claude Code + opencode 双端产物。"
            "骨架版本：仅解析 CLI 参数，未实现业务逻辑。"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅校验源结构与 runtime-config.yml 一致性，不写产物（CI 用）",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="先清空已有双端产物目录再生成",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="打印每个文件的 source → output 映射",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # TASK-001 骨架：不执行任何业务逻辑，直接返回成功。
    if args.verbose:
        print(
            f"[build.py:stub] check={args.check} clean={args.clean} "
            f"verbose={args.verbose}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
