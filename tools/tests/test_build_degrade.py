"""tools/tests/test_build_degrade.py — opencode degrade 退役回归测试。

历史背景：auto-video 曾在 opencode 端走「降级模板」分支（CronCreate 不可用），
runtime-config.yml 的 `workflows.opencode_degrade` + `opencode_degrade_template`
负责注入降级文档。自 sleep-loop 改造后，auto-video 在两端原生支持，degrade
机制整体退役。

本文件确认：
- 真实仓库的 runtime-config.yml 已清空 opencode_degrade 并删除模板 key
- build_workflows 对 user_invocable workflow 一视同仁地展开 invoke 块（不再
  对 auto-video 走 degrade 模板分支），两端正文等价（仅 $ARGUMENTS 索引差异）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))

import build  # type: ignore[import-not-found]  # noqa: E402

REPO_ROOT = TOOLS_DIR.parent
RUNTIME_CONFIG_PATH = TOOLS_DIR / "runtime-config.yml"


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
        "opencode_degrade": [],
    },
}


def _strip_frontmatter(text: str) -> str:
    return re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)


def _parse_frontmatter(text: str) -> dict:
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


# ---------------------------------------------------------------------------
# 仓库配置回归
# ---------------------------------------------------------------------------


def test_runtime_config_opencode_degrade_retired() -> None:
    """真实 runtime-config.yml：opencode_degrade 必须为空 list 且无模板 key。"""
    cfg = yaml.safe_load(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(cfg, dict)

    workflows = cfg.get("workflows")
    assert isinstance(workflows, dict), "workflows 顶层须为 mapping"
    assert "opencode_degrade" in workflows, (
        "保留 opencode_degrade key（即使为空）以记录该机制已退役"
    )
    assert workflows["opencode_degrade"] == [], (
        f"opencode_degrade 必须为空 list（当前: {workflows['opencode_degrade']}）"
    )

    assert "opencode_degrade_template" not in cfg, (
        "顶层不得再出现 opencode_degrade_template key（已随 degrade 机制退役）"
    )


# ---------------------------------------------------------------------------
# build 行为：auto-video 在两端走同一展开路径
# ---------------------------------------------------------------------------


def test_auto_video_built_uniformly_on_both_runtimes(tmp_path: Path) -> None:
    """opencode 端的 auto-video 不再走 degrade 模板，走与 Claude 端同样的 invoke 展开路径。

    同一个 invoke 块在两端都被展开为各自平台的 sub-agent 调用句式，且原文中
    其他段落（如本测试的 "Sleep loop 等待" 标记）在两端都被保留。
    """
    src_root = tmp_path / "src"
    claude_root = tmp_path / ".claude"
    opencode_root = tmp_path / ".opencode"

    _write_skill(src_root, "foo-skill")
    body_with_invoke = (
        "## 流程\n\n"
        "1. 调用 foo-skill：\n\n"
        "```invoke\nskill: foo-skill\nargs: \"\"\n```\n\n"
        "Sleep loop 等待\n"
    )
    _write_workflow(
        src_root,
        "auto-video",
        "name: auto-video\ndescription: 自动监控\nuser-invocable: true\n"
        "argument-hint: \"[集数]\"\n",
        body_with_invoke,
    )

    build.build_workflows(
        src_root=src_root,
        claude_root=claude_root,
        opencode_root=opencode_root,
        config=CONFIG,
    )

    claude_out = claude_root / "skills" / "auto-video" / "SKILL.md"
    opencode_out = opencode_root / "commands" / "auto-video.md"
    assert claude_out.exists()
    assert opencode_out.exists()

    cl_body = _strip_frontmatter(claude_out.read_text(encoding="utf-8"))
    op_body = _strip_frontmatter(opencode_out.read_text(encoding="utf-8"))

    assert "```invoke" not in cl_body
    assert "```invoke" not in op_body
    assert "使用 Skill tool 调用 `foo-skill` skill" in cl_body
    assert "调用 task 工具，传入 agent: `director`" in op_body
    assert "Sleep loop 等待" in cl_body
    assert "Sleep loop 等待" in op_body


def test_opencode_auto_video_command_frontmatter(tmp_path: Path) -> None:
    """opencode 端 auto-video 仍写到 commands/，frontmatter 含 agent/subtask/description。"""
    src_root = tmp_path / "src"
    claude_root = tmp_path / ".claude"
    opencode_root = tmp_path / ".opencode"

    _write_skill(src_root, "foo-skill")
    _write_workflow(
        src_root,
        "auto-video",
        "name: auto-video\ndescription: 自动监控\nuser-invocable: true\n"
        "argument-hint: \"[集数]\"\n",
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
    assert "name" not in fm
