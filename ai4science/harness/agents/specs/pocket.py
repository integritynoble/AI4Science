from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="pocket",
    tier="open",
    category="core",
    title="Pocket Agent",
    description="On-device (Tier-D) fixed-tool agent: a closed, permission-gated tool registry run directly (no sandbox). Consequential actions route to a Host agent.",
    keywords=("pocket", "iphone", "device", "on-device", "fixed-tool", "notes", "reminder", "calendar"),
    supported_profiles=("I0", "I1", "I2"),
    default_profile="I1",
    approval_required_for=("spend", "publish", "deploy", "delete_external"),
)

from ai4science.harness.agents.pocket.agent import run_pocket

RUNNER = run_pocket
