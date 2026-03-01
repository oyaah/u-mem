from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _ensure_json_server(path: Path, command: str, args: list[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except Exception:
            data = {}
    mcp = data.get("mcpServers") or {}
    mcp["u-mem"] = {"command": command, "args": args}
    data["mcpServers"] = mcp
    path.write_text(json.dumps(data, indent=2) + "\n")
    return str(path)


def _ensure_codex_server(path: Path, command: str, args: list[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    block = (
        "[mcp_servers.u-mem]\n"
        + f'command = "{command}"\n'
        + "args = [" + ", ".join(f'"{a}"' for a in args) + "]\n"
    )
    text = path.read_text() if path.exists() else ""
    if "[mcp_servers.u-mem]" in text:
        text = re.sub(
            r"\[mcp_servers\.u-mem\][\s\S]*?(?=\n\[[^\]]+\]|\Z)",
            block.rstrip("\n"), text, flags=re.MULTILINE,
        ).rstrip() + "\n"
    else:
        text = (text.rstrip() + "\n\n" + block) if text else block
    path.write_text(text)
    return str(path)


def _is_umem_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    return any(
        isinstance(h, dict) and str(h.get("command") or "").startswith("umem-")
        for h in entry.get("hooks", [])
    )


def _install_hooks(settings_path: Path) -> str:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text())
        except Exception:
            data = {}

    hooks = data.get("hooks") or {}

    pre = [h for h in (hooks.get("PreCompact") or []) if not _is_umem_entry(h)]
    pre.insert(0, {"hooks": [{"type": "command", "command": "umem-pre-compact", "timeout": 30}]})
    hooks["PreCompact"] = pre

    ss = [h for h in (hooks.get("SessionStart") or []) if not _is_umem_entry(h)]
    ss.insert(0, {"matcher": "compact", "hooks": [{"type": "command", "command": "umem-session-start", "timeout": 10}]})
    hooks["SessionStart"] = ss

    data["hooks"] = hooks
    settings_path.write_text(json.dumps(data, indent=2) + "\n")
    return str(settings_path)


def main() -> None:
    p = argparse.ArgumentParser(description="Configure u-mem MCP + Claude Code hooks")
    p.add_argument("--command", default="uvx", help="MCP launcher command")
    p.add_argument("--arg", action="append", dest="args")
    p.add_argument("--target", choices=["all", "codex", "claude", "gemini"], default="all")
    p.add_argument("--hooks", action="store_true")
    p.add_argument("--hooks-only", action="store_true")
    ns = p.parse_args()
    args = [a for a in (ns.args or ["u-mem"]) if a]

    outputs: list[str] = []

    if not ns.hooks_only:
        if ns.target in ("all", "codex"):
            outputs.append(_ensure_codex_server(Path.home() / ".codex" / "config.toml", ns.command, args))
        if ns.target in ("all", "claude"):
            outputs.append(_ensure_json_server(Path.home() / ".claude" / "mcp.json", ns.command, args))
        if ns.target in ("all", "gemini"):
            outputs.append(_ensure_json_server(Path.home() / ".gemini" / "settings.json", ns.command, args))

    if ns.hooks or ns.hooks_only:
        hook_path = _install_hooks(Path.home() / ".claude" / "settings.json")
        outputs.append(
            f"{hook_path}\n"
            "    hooks: PreCompact → umem-pre-compact\n"
            "           SessionStart → umem-session-start"
        )

    if outputs:
        print("Configured u-mem in:")
        for out in outputs:
            print(f"  {out}")
        print("\nRestart Claude Code to activate.")
    else:
        print("Nothing configured. Use --hooks-only to install hooks.")


if __name__ == "__main__":
    main()
