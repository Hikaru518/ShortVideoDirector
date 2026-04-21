#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///
"""tools/check-structure.py — 源结构与产物一致性校验器（骨架）。

本文件目前是 TASK-001 引入的骨架；完整校验逻辑由 TASK-008 实现：
  - tools/runtime-config.yml 的 agents.<owner> mapping 中所有 skill 名都
    必须对应 src/skills/<name>/SKILL.md 实际文件
  - workflows.user_invocable + workflows.internal 集合 = src/workflows/*.md 全集
  - 每个产物 frontmatter 字段符合 runtime-config.yml 中声明的 schema
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    # TASK-001 骨架：尚无校验逻辑，直接返回成功。
    return 0


if __name__ == "__main__":
    sys.exit(main())
