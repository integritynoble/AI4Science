from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.machine.harness_tools import machine_tools, MACHINE_SYSTEM_PROMPT

AGENT = AgentSpec(
    name="machine",
    tier="open",
    category="core",
    title="Machine Agent",
    description="Governed local-machine + Claude-Code bootstrap (work family): a closed registry of vetted, owner-gated operations — install/permission/login. Safer than an autonomous computer-use agent.",
    keywords=("machine", "install", "claude", "bootstrap", "permission", "login", "setup", "manage"),
    supported_profiles=("I0", "I1", "I2"),
    default_profile="I1",
    approval_required_for=("install", "login", "grant-permission", "deploy", "spend"),
    system_prompt=MACHINE_SYSTEM_PROMPT,      # steer it to the real tools, not file search
    extra_tools=machine_tools,                # find_claude_sessions / detect_machine as tools
)

from ai4science.harness.agents.machine.agent import run_machine

RUNNER = run_machine
