from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="social",
    tier="open",
    category="specific",
    title="Social Media",
    description="Dual-mode social-media agent (Mastodon timeline read + owner-gated post, A2).",
    keywords=("mastodon", "social", "post", "timeline"),
    supported_profiles=("I0", "I1", "I2"),
    default_profile="I2",
    approval_required_for=("external_post",),
)

from ai4science.harness.agents.social.agent import run_social_task

# Entry point the dispatcher uses to run this agent on the dual-mode runtime.
RUNNER = run_social_task
