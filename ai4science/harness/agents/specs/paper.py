from ai4science.harness.agents.spec import AgentSpec

PAPER_PROMPT = (
    "You are AI4Science in PAPER-REVIEW mode. When the user names a paper file "
    "(PDF/Markdown/LaTeX) in the workspace, call the `paper_review` tool with that "
    "path and the requested depth, then summarize the decision and the key points "
    "of the reviews. Default depth is 'shallow' (one reviewer, free); use 'deep' "
    "(three reviewers + area chair) only when the user asks. After the review is "
    "written you can read and discuss the bundle in .ai4science/reviews/."
)

AGENT = AgentSpec(
    name="paper",
    tier="science",
    category="core",
    title="Paper review",
    description="Simulated peer review of a paper file → reviews + decision.",
    keywords=("paper", "review", "peer review", "referee", "manuscript"),
    system_prompt=PAPER_PROMPT,
    capabilities=("pwm-actions", "pwm-data", "paper-review", "compute-providers",
                  "ci-algorithms"),
    order=3,
)
