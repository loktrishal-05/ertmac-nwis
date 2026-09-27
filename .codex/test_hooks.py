"""Windows hook smoke check: python .codex/test_hooks.py."""
import json
import subprocess
import tempfile
from pathlib import Path


hooks = json.loads(Path(__file__).with_name("hooks.json").read_text())["hooks"]
with tempfile.TemporaryDirectory(prefix="impeccable-hook-check-") as folder:
    target = Path(folder) / "sample.jsx"
    target.write_text('export default () => <img src="missing.png" />;\n')
    for shell in ("cmd", "powershell"):
        for event in ("PostToolUse", "Stop"):
            command = hooks[event][0]["hooks"][0]["commandWindows"]
            args = (
                'cmd.exe /d /s /c "' + command + '"'
                if shell == "cmd"
                else ["powershell.exe", "-NoProfile", "-Command", command]
            )
            payload = {
                "hook_event_name": event,
                "session_id": "hook-check-" + shell,
                "cwd": folder,
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
                "stop_hook_active": False,
            }
            result = subprocess.run(
                args, input=json.dumps(payload), capture_output=True,
                text=True, cwd=folder, timeout=40,
            )
            assert result.returncode == 0, (shell, event, result.stderr)
            if event == "PostToolUse":
                assert result.stdout.strip(), "Hook exited without running the detector"
            print(f"PASS {shell}: {event}")
