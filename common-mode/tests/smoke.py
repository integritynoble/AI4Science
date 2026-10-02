#!/usr/bin/env python3
"""Exercise an installed prefix, with real network/file tracing on Linux."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
from fake_openai import serve


def digest_tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prefix", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace", action="store_true", help="Require Linux strace and verify every network destination")
    parser.add_argument("--model-id", default="local", help="Model identifier sent to the fixture server")
    args = parser.parse_args()
    prefix = args.prefix.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    fixture = out / "fixture"
    fixture.mkdir()
    home = fixture / "home"
    project = fixture / "project"
    project.mkdir()
    conflict = {"username": "MUST_NOT_LOAD", "plugin": ["file:///must-not-load.mjs"], "mcp": {"pwm": {"type": "remote", "url": "http://127.0.0.1:9/must-not-call", "enabled": True}}, "model": "opencode/must-not-load"}
    for relative in [".config/opencode/opencode.json", ".opencode/opencode.json", ".claude/settings.json"]:
        p = home / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(conflict))
    for relative in ["opencode.json", ".opencode/opencode.json"]:
        p = project / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(conflict))
    auth = home / ".local/share/opencode/auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text('{"openai":{"type":"oauth","refresh":"TEST_ONLY_SENTINEL","access":"TEST_ONLY_SENTINEL","expires":0}}')
    before = digest_tree(fixture)
    server = serve(log=out / "requests.jsonl")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    # A PATH with only the wrapper's shell utilities: prove no Node/npm/git needed.
    path = out / "path"
    path.mkdir()
    for command in ["sh", "dirname", "uname", "mkdir", "id"]:
        source = shutil.which(command)
        if source:
            (path / command).symlink_to(source)
    env = {"PATH": str(path), "HOME": str(home), "USER": "test", "LANG": "C.UTF-8", "TERM": "dumb", "NO_COLOR": "1",
           "AI4SCIENCE_BASE_URL": f"http://127.0.0.1:{port}/v1", "AI4SCIENCE_API_KEY": "TEST_ONLY_KEY",
           "AI4SCIENCE_MODEL": args.model_id,
           "XDG_CONFIG_HOME": str(home / ".config"), "XDG_DATA_HOME": str(home / ".local/share"),
           "OPENCODE_CONFIG_CONTENT": json.dumps(conflict), "OPENCODE_CONFIG_DIR": str(home / ".config/opencode"),
           "OPENCODE_DB": str(home / "must-not-use.db"), "OPENCODE_MODELS_URL": "http://127.0.0.1:9/must-not-call",
           "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9"}
    wrapper = prefix / "bin/ai4science"

    def run(label, argv):
        command = [str(wrapper), *argv]
        if args.trace:
            tracer = shutil.which("strace")
            if not tracer:
                raise RuntimeError("strace is required for --trace")
            command = [tracer, "-f", "-s", "0", "-e", "trace=network,openat", "-o", str(out / f"{label}.trace"), *command]
        result = subprocess.run(command, env=env, cwd=project, text=True, capture_output=True, timeout=120)
        (out / f"{label}.stdout").write_text(result.stdout)
        (out / f"{label}.stderr").write_text(result.stderr)
        assert result.returncode == 0, f"{label} failed with {result.returncode}; inspect private output"
        return result.stdout

    try:
        version = run("version", ["--version"]).strip()
        pinned_version = (prefix / "share/opencode.version").read_text().strip()
        assert version == f"AI4Science common mode (OpenCode {pinned_version})", version
        config = json.loads(run("config", ["debug", "config"]))
        assert config["username"] == "AI4Science"
        assert config["enabled_providers"] == ["own-llm"]
        assert config["plugin"] == []
        assert config["mcp"] == {"pwm": {"enabled": False}}
        assert config["share"] == "disabled" and config["autoupdate"] is False
        assert run("models", ["models"]).strip() == "own-llm/local"
        session = run("session", ["run", "--format", "json", "Reply with exactly AI4SCIENCE_LOCAL_OK. Do not use tools."])
        events = [json.loads(line) for line in session.splitlines() if line.startswith("{")]
        assert any(e.get("type") == "text" and "AI4SCIENCE_LOCAL_OK" in e["part"]["text"] for e in events)
        assert not any(e.get("type") == "error" for e in events)
        assert digest_tree(fixture) == before, "External OpenCode config/auth/project was changed"
        requests = [json.loads(line) for line in (out / "requests.jsonl").read_text().splitlines()]
        assert requests and all(r["path"] == "/v1/chat/completions" and r["model"] == args.model_id for r in requests)
        destinations = set()
        if args.trace:
            for trace in out.glob("*.trace"):
                text = trace.read_text()
                # Reject remote connects AND UDP DNS/datagrams, even unsuccessful attempts.
                for line in text.splitlines():
                    if re.search(r"\b(connect|sendto|sendmsg|sendmmsg)\(", line) and re.search(r"sa_family=AF_INET6?", line):
                        match = re.search(r'sin_port=htons\((\d+)\), sin_addr=inet_addr\("([^"]+)"\)', line)
                        assert match and (match[2], int(match[1])) == ("127.0.0.1", port), "Unexpected network destination: " + line
                        destinations.add(f"{match[2]}:{match[1]}")
                # The traced process must not even open any of the conflicting config/auth fixtures.
                # Project source files can be indexed as ordinary workspace data;
                # the guarantee here concerns global settings and stored auth.
                for p in home.rglob("*"):
                    if p.is_file():
                        assert f'"{p}"' not in text, f"Read external file: {p}"
            assert destinations, "No traced request reached the fixture"
        billing = [str(p.relative_to(prefix)) for p in prefix.rglob("*") if p.is_file() and re.search(r"pwm|ledger", p.name, re.I)]
        assert not billing, billing
        summary = {"version": version, "session": "AI4SCIENCE_LOCAL_OK", "requests": len(requests),
                   "model_id": args.model_id,
                   "network_destinations": sorted(destinations), "network_trace_verified": args.trace,
                   "external_config_and_auth_unchanged": True, "external_config_and_auth_not_read": args.trace,
                   "node_npm_git_on_path": False, "pwm_or_ledger_files": billing}
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
