#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "python-frontmatter>=1.1",
#   "PyYAML>=6.0",
# ]
# ///
"""tools/build.py — 双端产物构建器。

按 tools/runtime-config.yml 的规则，将 src/{skills,agents,workflows}/
canonical 源转换为 .claude/{skills,agents}/ + .opencode/{skills,commands,agents}/
两端产物。

TASK-005 实现范围：
    - 业务 skill：src/skills/<name>/ → .claude/skills/<name>/ + .opencode/skills/<name>/
    - 附属文件（rules.md 等）原样复制到两端
    - 顶层 `--check` / `--clean` / `--verbose` CLI 接口保留

workflow / agent 的双端构建由后续 TASK-006/007 实现。
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import frontmatter
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNTIME_CONFIG = REPO_ROOT / "tools" / "runtime-config.yml"
DEFAULT_SRC_ROOT = REPO_ROOT / "src"
DEFAULT_CLAUDE_ROOT = REPO_ROOT / ".claude"
DEFAULT_OPENCODE_ROOT = REPO_ROOT / ".opencode"

# 业务 skill 源 frontmatter 仅允许这两个字段
ALLOWED_SOURCE_SKILL_FIELDS = {"name", "description"}

# 双端产物 frontmatter 字段顺序（确定性，避免 git diff 噪音）
CLAUDE_SKILL_FIELD_ORDER: tuple[str, ...] = (
    "name",
    "description",
    "user-invocable",
    "context",
    "agent",
)
OPENCODE_SKILL_FIELD_ORDER: tuple[str, ...] = ("name", "description")


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------


def load_runtime_config(path: Path) -> dict[str, Any]:
    """读取 runtime-config.yml，返回 dict。"""
    if not path.exists():
        raise FileNotFoundError(f"runtime config 不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"runtime config 顶层不是 mapping: {path}")
    return data


def build_skill_to_owner_index(config: dict[str, Any]) -> dict[str, str]:
    """把 agents 配置反转为 {skill_name: owner_name}。

    重复声明（同一 skill 出现在多个 owner 下）视为配置错误，立即报错。
    """
    agents = config.get("agents")
    if not isinstance(agents, dict):
        raise ValueError("runtime-config.yml 缺少 agents mapping 或类型错误")
    index: dict[str, str] = {}
    for owner, skills in agents.items():
        if not isinstance(skills, list):
            raise ValueError(
                f"runtime-config.yml agents.{owner} 不是 list（得到 {type(skills).__name__}）"
            )
        for skill in skills:
            if skill in index:
                raise ValueError(
                    f"runtime-config.yml: skill '{skill}' 在多个 owner 下重复声明 "
                    f"（{index[skill]} 与 {owner}）"
                )
            index[skill] = owner
    return index


# ---------------------------------------------------------------------------
# Skill 解析与 frontmatter 注入
# ---------------------------------------------------------------------------


def parse_skill(path: Path) -> frontmatter.Post:
    """读取 SKILL.md，返回 frontmatter.Post（仅用于 metadata 解析）。

    注意：post.content 会被 python-frontmatter strip 前导空白，因此正文应通过
    extract_raw_body() 取得，不要用 post.content。
    """
    if not path.exists():
        raise FileNotFoundError(f"skill 文件不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        return frontmatter.load(f)


_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def extract_raw_body(path: Path) -> str:
    """读取源文件原始 body（保留 closing `---\\n` 之后的所有字符，含前导空行）。

    若文件无 frontmatter 头，返回整个文件内容。
    """
    text = path.read_text(encoding="utf-8")
    return _FRONTMATTER_RE.sub("", text, count=1)


def _ordered_metadata(
    metadata: dict[str, Any], field_order: tuple[str, ...]
) -> dict[str, Any]:
    """按 field_order 重新排序 dict（Python 3.7+ 保留插入顺序）。

    field_order 中没列出的字段按字母序追加到末尾（防御性，避免无声丢字段）。
    """
    ordered: dict[str, Any] = {}
    for key in field_order:
        if key in metadata:
            ordered[key] = metadata[key]
    for key in sorted(k for k in metadata.keys() if k not in field_order):
        ordered[key] = metadata[key]
    return ordered


def inject_frontmatter(
    src_metadata: dict[str, Any],
    runtime_inject: dict[str, Any],
    extra_fields: dict[str, Any] | None = None,
    field_order: tuple[str, ...] = (),
) -> dict[str, Any]:
    """合并源 metadata + runtime 注入 + extra_fields，返回新的 dict（按 field_order 排序）。

    冲突优先级：extra_fields > runtime_inject > 源 frontmatter
    （这意味着 runtime-config.yml 里的注入字段会覆盖源的同名字段，但当前业务
    skill 源 frontmatter 仅含 name/description，不会冲突。）
    """
    merged: dict[str, Any] = dict(src_metadata)
    merged.update(runtime_inject or {})
    if extra_fields:
        merged.update(extra_fields)
    if field_order:
        merged = _ordered_metadata(merged, field_order)
    return merged


def _yaml_dump_metadata(metadata: dict[str, Any]) -> str:
    """按确定性 yaml 风格 dump metadata。"""
    return yaml.safe_dump(
        metadata,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


def write_output(metadata: dict[str, Any], body: str, output_path: Path) -> None:
    """以 `---\\n<yaml>---\\n<body>` 格式写出（自动建目录、覆盖已存在文件）。

    body 原样写出，不做任何 strip / normalize（保证三端正文一致）。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = _yaml_dump_metadata(metadata)
    output_path.write_text(
        f"---\n{fm_text}---\n{body}",
        encoding="utf-8",
    )


def copy_attachments(src_dir: Path, output_dir: Path) -> list[Path]:
    """把 src_dir 下除 SKILL.md 之外的所有常规文件原样复制到 output_dir。

    返回成功复制的目标路径列表（用于 verbose 日志 / 测试断言）。
    子目录目前不递归（业务 skill 目前都是平坦结构，含 rules.md 即够）；
    若未来出现子目录可在此扩展。
    """
    copied: list[Path] = []
    if not src_dir.exists():
        return copied
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in sorted(src_dir.iterdir()):
        if not child.is_file():
            continue
        if child.name == "SKILL.md":
            continue
        target = output_dir / child.name
        shutil.copy2(child, target)
        copied.append(target)
    return copied


# ---------------------------------------------------------------------------
# 业务 skill 双端构建
# ---------------------------------------------------------------------------


def _validate_source_skill(
    post: frontmatter.Post, skill_name: str, src_path: Path
) -> None:
    """业务 skill 源 frontmatter 仅允许 name + description。"""
    extra = set(post.metadata.keys()) - ALLOWED_SOURCE_SKILL_FIELDS
    if extra:
        raise ValueError(
            f"src/skills/{skill_name}/SKILL.md 源 frontmatter 含非法字段 "
            f"{sorted(extra)}（仅允许 {sorted(ALLOWED_SOURCE_SKILL_FIELDS)}）"
            f"\n  路径: {src_path}"
        )
    missing = ALLOWED_SOURCE_SKILL_FIELDS - set(post.metadata.keys())
    if missing:
        raise ValueError(
            f"src/skills/{skill_name}/SKILL.md 源 frontmatter 缺少字段 "
            f"{sorted(missing)}（必须含 {sorted(ALLOWED_SOURCE_SKILL_FIELDS)}）"
            f"\n  路径: {src_path}"
        )
    name_field = post.metadata.get("name")
    if name_field != skill_name:
        raise ValueError(
            f"src/skills/{skill_name}/SKILL.md frontmatter.name='{name_field}' "
            f"与目录名 '{skill_name}' 不一致"
            f"\n  路径: {src_path}"
        )


def build_business_skills(
    src_root: Path,
    claude_root: Path,
    opencode_root: Path,
    config: dict[str, Any],
    verbose: bool = False,
) -> int:
    """构建所有业务 skill 的双端产物，返回处理的 skill 数量。

    fail-fast：任一 skill 校验失败立刻抛 ValueError，不会继续处理其余 skill。
    """
    src_skills_dir = src_root / "skills"
    if not src_skills_dir.exists():
        raise FileNotFoundError(f"src/skills/ 不存在: {src_skills_dir}")

    skill_to_owner = build_skill_to_owner_index(config)
    claude_inject = (
        config.get("runtimes", {}).get("claude", {}).get("business_skill_inject", {})
        or {}
    )
    opencode_inject = (
        config.get("runtimes", {}).get("opencode", {}).get("business_skill_inject", {})
        or {}
    )

    count = 0
    for skill_dir in sorted(src_skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_name = skill_dir.name
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            raise FileNotFoundError(
                f"src/skills/{skill_name}/ 缺少 SKILL.md（路径: {skill_md}）"
            )

        if skill_name not in skill_to_owner:
            raise ValueError(
                f"业务 skill '{skill_name}' 未在 runtime-config.yml 的 agents "
                f"mapping 中注册。\n"
                f"  源路径: {skill_md}\n"
                f"  请在 tools/runtime-config.yml 的 agents.<owner> 列表中添加 "
                f"'{skill_name}'，或删除该目录。"
            )
        owner = skill_to_owner[skill_name]

        src_post = parse_skill(skill_md)
        _validate_source_skill(src_post, skill_name, skill_md)
        raw_body = extract_raw_body(skill_md)

        claude_metadata = inject_frontmatter(
            src_post.metadata,
            runtime_inject=claude_inject,
            extra_fields={"agent": owner},
            field_order=CLAUDE_SKILL_FIELD_ORDER,
        )
        opencode_metadata = inject_frontmatter(
            src_post.metadata,
            runtime_inject=opencode_inject,
            extra_fields=None,
            field_order=OPENCODE_SKILL_FIELD_ORDER,
        )

        claude_skill_dir = claude_root / "skills" / skill_name
        opencode_skill_dir = opencode_root / "skills" / skill_name
        claude_out = claude_skill_dir / "SKILL.md"
        opencode_out = opencode_skill_dir / "SKILL.md"

        write_output(claude_metadata, raw_body, claude_out)
        write_output(opencode_metadata, raw_body, opencode_out)
        copy_attachments(skill_dir, claude_skill_dir)
        copy_attachments(skill_dir, opencode_skill_dir)

        if verbose:
            print(f"[skill:{owner}] {skill_md} → {claude_out}, {opencode_out}")

        count += 1

    return count


# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------


def clean_outputs(claude_root: Path, opencode_root: Path, verbose: bool = False) -> None:
    """清空双端 skills/ 产物目录（agents/commands 等由后续 task 负责）。"""
    for root in (claude_root, opencode_root):
        skills_dir = root / "skills"
        if skills_dir.exists():
            if verbose:
                print(f"[clean] rm -rf {skills_dir}")
            shutil.rmtree(skills_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build.py",
        description="构建 Claude Code + opencode 双端产物（TASK-005：仅业务 skill）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅校验源结构与 runtime-config.yml 一致性，不写产物（CI 用）",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="先清空已有双端产物（仅 skills/）再生成",
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

    config = load_runtime_config(DEFAULT_RUNTIME_CONFIG)

    if args.clean:
        clean_outputs(DEFAULT_CLAUDE_ROOT, DEFAULT_OPENCODE_ROOT, verbose=args.verbose)

    if args.check:
        # --check 仅做结构校验：跑 build_business_skills 但写到一次性 buffer 是
        # 杀鸡用牛刀；这里复用 fail-fast 校验链，写到临时目录由后续 task 决定。
        # 当前 stub：仅校验 config + 反查表。后续 TASK-008 会接管 --check。
        build_skill_to_owner_index(config)
        if args.verbose:
            print("[check] runtime-config.yml 结构 OK（agents mapping 解析成功）")
        return 0

    n_skills = build_business_skills(
        src_root=DEFAULT_SRC_ROOT,
        claude_root=DEFAULT_CLAUDE_ROOT,
        opencode_root=DEFAULT_OPENCODE_ROOT,
        config=config,
        verbose=args.verbose,
    )

    if args.verbose:
        print(f"[build] 业务 skill: {n_skills} 个 → 双端产物已生成")
        print("[build] TODO(TASK-006/007): workflow / agent 双端构建尚未实现")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(f"[build.py:error] {exc}", file=sys.stderr)
        sys.exit(1)
