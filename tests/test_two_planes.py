"""Two planes: the ai4science PLATFORM (all agents, released frequently) vs the
singularity PRODUCT (mature agents only, kept stable). Every agent is built and
recursively self-improved in ai4science; only agents whose AgentSpec.matured is True
ship in singularity. The active plane is chosen by PWM_PLANE (default "ai4science").
Manager + Machine mature first, so they are the two agents that ship in singularity
today; the Manager is the login entry point in both planes."""
from ai4science.harness.agents import registry as R
from ai4science.harness.agents.manager.agent import builtin_specs, login_entry, run_manager
from ai4science.harness.agents.specs.manager import AGENT as MANAGER_SPEC
from ai4science.harness.agents.specs.machine import AGENT as MACHINE_SPEC
from ai4science.harness.agents.specs.work import AGENT as WORK_SPEC


def test_spec_has_matured_flag_defaulting_false():
    # additive field; specialists are NOT matured by default
    assert WORK_SPEC.matured is False


def test_manager_and_machine_are_matured():
    # the console and the host-governor mature first
    assert MANAGER_SPEC.matured is True
    assert MACHINE_SPEC.matured is True


def test_current_plane_defaults_to_ai4science(monkeypatch):
    monkeypatch.delenv("PWM_PLANE", raising=False)
    assert R.current_plane() == "ai4science"


def test_current_plane_reads_env(monkeypatch):
    monkeypatch.setenv("PWM_PLANE", "singularity")
    assert R.current_plane() == "singularity"
    monkeypatch.setenv("PWM_PLANE", "AI4SCIENCE")   # case-insensitive; unknown -> platform
    assert R.current_plane() == "ai4science"


def test_platform_view_is_superset_of_mature(monkeypatch):
    monkeypatch.delenv("PWM_PLANE", raising=False)
    R.reload()
    platform = {s.name for s in R.platform_agents()}
    mature = {s.name for s in R.mature_agents()}
    assert mature <= platform
    assert "manager" in mature and "machine" in mature
    # a sandboxed specialist is on the platform but not (yet) in the product
    assert "imaging" in platform and "imaging" not in mature


def test_agents_for_plane_switches_on_env(monkeypatch):
    R.reload()
    monkeypatch.setenv("PWM_PLANE", "singularity")
    assert {s.name for s in R.agents_for_plane()} == {s.name for s in R.mature_agents()}
    monkeypatch.setenv("PWM_PLANE", "ai4science")
    assert {s.name for s in R.agents_for_plane()} == {s.name for s in R.platform_agents()}
    # explicit plane arg overrides the env
    assert {s.name for s in R.agents_for_plane("singularity")} == {s.name for s in R.mature_agents()}


def test_builtin_specs_narrow_to_mature_on_singularity():
    on_platform = {s.name for s in builtin_specs("ai4science")}
    on_product = {s.name for s in builtin_specs("singularity")}
    assert on_product <= on_platform
    # every routable target exposed in the product must be matured
    assert all(s.matured for s in builtin_specs("singularity"))
    # the platform routes to strictly more (the sandboxed specialists)
    assert on_platform - on_product


def test_login_entry_is_the_manager():
    entry = login_entry()
    assert entry.name == "manager"
    assert entry.matured is True


def test_run_manager_respects_plane(monkeypatch):
    # on the product plane the manager only routes to matured agents; a demand that
    # only a sandboxed specialist could serve finds no product-plane target.
    monkeypatch.delenv("PWM_PLANE", raising=False)
    res_platform = run_manager(demand={"intent": "reconstruct a CASSI scene"}, plane="ai4science")
    res_product = run_manager(demand={"intent": "reconstruct a CASSI scene"}, plane="singularity")
    platform_names = {r[0] for r in res_platform["ranked"]}   # ranked = [(name, score), ...]
    product_names = {r[0] for r in res_product["ranked"]}
    assert product_names <= platform_names
    assert "imaging" in platform_names and "imaging" not in product_names
