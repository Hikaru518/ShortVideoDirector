"""tools/tests/test_build_degrade.py — TASK-006 auto-video opencode 降级。

覆盖：
- opencode 端 auto-video 正文 = degrade_template（不展开 invoke 块）
- Claude 端 auto-video 正文展开 invoke 块（保持完整流程）
- opencode 端 auto-video 输出到 .opencode/commands/auto-video.md，含 agent: build + subtask: true
- Claude 端 auto-video 输出到 .claude/skills/auto-video/SKILL.md，含 user-invocable: true
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))

import build  # type: ignore[import-not-found]  # noqa: E402


DEGRADE_TEXT = (
    "`/auto-video` 在 opencode 端不支持自动定时监控（依赖 Cron 工具组）。\n"
    "请使用操作系统调度调用 `/check-video <ep>`：\n"
)

CONFIG = {
    "agents": {"director": ["foo-skill"]},
    "runtimes": {
        "claude": {
            "business_skill_inject": {"user-invocable": False, "context": "fork"},
            "workflow_user_invocable_inject": {
                "user-invocable": True,
                "allowed-tools": "Read, Write, Edit, Glob, Bash, Skill, Agent",
            },
            "workflow_internal_inject": {
                "user-invocable": False,
                "allowed-tools": "Read, Write, Edit, Glob, Bash, Skill",
            },
            "invoke_template": "使用 Skill tool 调用 `{skill}` skill{args_phrase}\n",
            "invoke_no_args_phrase": "（无参数）",
            "invoke_with_args_phrase": "，传递参数：`{args}`",
        },
        "opencode": {
            "business_skill_inject": {},
            "workflow_user_invocable_inject": {"agent": "build", "subtask": True},
            "workflow_internal_inject": {"agent": "build", "subtask": True},
            "invoke_template": (
                "调用 task 工具，传入 agent: `{owner}`，"
                'prompt: "执行 {skill} skill 描述的任务{args_phrase}"\n'
            ),
            "invoke_no_args_phrase": "，无额外参数",
            "invoke_with_args_phrase": "，参数：{args}",
            "arguments_index_offset": 1,
        },
    },
    "workflows": {
        "user_invocable": ["auto-video"],
        "internal": [],
        "opencode_degrade": ["auto-video"],
    },
    "opencode_degrade_template": {"auto-video": DEGRADE_TEXT},
}


def _strip_frontmatter(text: str) -> str:
    return re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)


def _parse_frontmatter(text: str) -> dict:
    import yaml

    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m is not None
    return yaml.safe_load(m.group(1))


def _write_workflow(src_root: Path, name: str, frontmatter: str, body: str) -> None:
    wf_dir = src_root / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{name}.md").write_text(
        f"---\n{frontmatter}---\n{body}", encoding="utf-8"
    )


def _write_skill(src_root: Path, name: str) -> None:
    skill_dir = src_root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: stub\n---\nbody\n",
        encoding="utf-8",
    )


def test_opencode_auto_video_body_replaced_by_degrade_template(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    claude_root = tmp_path / ".claude"
    opencode_root = tmp_path / ".opencode"

    _write_skill(src_root, "foo-skill")
    body_with_invoke = (
        "## 流程\n\n"
        "1. 调用 foo-skill：\n\n"
        "```invoke\nskill: foo-skill\nargs: \"\"\n```\n\n"
        "Cron 工具说明 etc.\n"
    )
    _write_workflow(
        src_root,
        "auto-video",
        "name: auto-video\ndescription: 自动监控\nuser-invocable: true\nargument-hint: \"[集数]\"\n",
        body_with_invoke,
    )

    build.build_workflows(
        src_root=src_root,
        claude_root=claude_root,
        opencode_root=opencode_root,
        config=CONFIG,
    )

    opencode_out = opencode_root / "commands" / "auto-video.md"
    assert opencode_out.exists()
    op_body = _strip_frontmatter(opencode_out.read_text(encoding="utf-8"))
    assert op_body == DEGRADE_TEXT, f"opencode auto-video 正文未替换为降级模板: {op_body!r}"
    assert "```invoke" not in op_body
    assert "foo-skill" not in op_body  # 降级模板不含原 invoke 内容


def test_claude_auto_video_body_expanded_normally(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    claude_root = tmp_path / ".claude"
    opencode_root = tmp_path / ".opencode"

    _write_skill(src_root, "foo-skill")
    body_with_invoke = (
        "## 流程\n\n"
        "```invoke\nskill: foo-skill\nargs: \"\"\n```\n\n"
        "Cron 工具说明\n"
    )
    _write_workflow(
        src_root,
        "auto-video",
        "name: auto-video\ndescription: 自动监控\nuser-invocable: true\nargument-hint: \"[集数]\"\n",
        body_with_invoke,
    )

    build.build_workflows(
        src_root=src_root,
        claude_root=claude_root,
        opencode_root=opencode_root,
        config=CONFIG,
    )

    claude_out = claude_root / "skills" / "auto-video" / "SKILL.md"
    assert claude_out.exists()
    cl_body = _strip_frontmatter(claude_out.read_text(encoding="utf-8"))
    assert "```invoke" not in cl_body
    assert "使用 Skill tool 调用 `foo-skill` skill" in cl_body
    assert "Cron 工具说明" in cl_body  # 正常展开正文，保留其他段落


def test_opencode_auto_video_frontmatter_includes_command_fields(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    claude_root = tmp_path / ".claude"
    opencode_root = tmp_path / ".opencode"

    _write_skill(src_root, "foo-skill")
    _write_workflow(
        src_root,
        "auto-video",
        "name: auto-video\ndescription: 自动监控\nuser-invocable: true\nargument-hint: \"[集数]\"\n",
        "正文\n",
    )

    build.build_workflows(
        src_root=src_root,
        claude_root=claude_root,
        opencode_root=opencode_root,
        config=CONFIG,
    )

    op_text = (opencode_root / "commands" / "auto-video.md").read_text(
        encoding="utf-8"
    )
    fm = _parse_frontmatter(op_text)
    assert fm.get("agent") == "build"
    assert fm.get("subtask") is True
    assert fm.get("description") == "自动监控"
    # opencode commands 不含 name 字段（以文件名为准）
    assert "name" not in fm
