"""The Manager on login (ai4science console): greet on the active plane, route a
demand to an owner-gated proposal, and honour the plane gate (product = mature only).
Deterministic — scope routing, no LLM / network."""
from ai4science.harness.agents.manager.login_console import (
    greet, handle_demand, render_greeting, render_proposal, Greeting,
)


def test_greet_platform_is_the_manager_over_the_whole_fleet(monkeypatch):
    monkeypatch.delenv("PWM_PLANE", raising=False)
    g = greet(plane="ai4science")
    assert isinstance(g, Greeting)
    assert g.plane == "ai4science"
    assert g.manager == "Manager"
    assert g.profile == "I0"                       # propose-first console
    assert "run-agent" in g.approvals              # no self-authorised execution
    names = {a["name"] for a in g.fleet}
    assert {"work", "imaging", "learning", "machine"} <= names   # full platform fleet


def test_greet_product_plane_is_mature_only():
    g = greet(plane="singularity")
    names = {a["name"] for a in g.fleet}
    assert "machine" in names                      # matured -> ships in the product
    assert "imaging" not in names                  # specialist still improving in ai4science
    assert names <= {a["name"] for a in greet(plane="ai4science").fleet}


def test_greet_defaults_to_current_plane(monkeypatch):
    monkeypatch.setenv("PWM_PLANE", "singularity")
    assert greet().plane == "singularity"
    monkeypatch.delenv("PWM_PLANE", raising=False)
    assert greet().plane == "ai4science"


def test_handle_demand_routes_to_accountable_agent():
    p = handle_demand("reconstruct my CASSI computational imaging scene", plane="ai4science")
    assert p["recommended_agent"] == "imaging"
    assert p["draft_demand"] == {"agent": "imaging",
                                 "objective": "reconstruct my CASSI computational imaging scene"}
    assert p["gap"] is None


def test_handle_demand_prefer_biases_the_route():
    # without prefer this routes to 'machine'; prefer forces the tie the owner asked for
    p = handle_demand("install Claude and grant permission during setup",
                      plane="ai4science", prefer="pocket")
    assert p["recommended_agent"] == "pocket"


def test_plane_gate_holds_a_specialist_demand_on_the_product_plane():
    intent = "reconstruct my CASSI computational imaging scene"
    assert handle_demand(intent, plane="ai4science")["recommended_agent"] == "imaging"
    product = handle_demand(intent, plane="singularity")
    assert product["recommended_agent"] is None    # imaging not matured -> not routable
    assert product["gap"]                           # documented capability gap, not attempted


def test_matured_demand_routes_on_both_planes():
    intent = "install Claude and grant permission during setup"
    assert handle_demand(intent, plane="ai4science")["recommended_agent"] == "machine"
    assert handle_demand(intent, plane="singularity")["recommended_agent"] == "machine"


def test_renderers_surface_the_key_facts():
    g = greet(plane="ai4science")
    text = render_greeting(g)
    assert "Manager" in text and "imaging" in text and "run nothing without your say-so" in text

    proposal = handle_demand("reconstruct my CASSI computational imaging scene", plane="ai4science")
    pr = render_proposal("reconstruct my CASSI computational imaging scene", proposal)
    assert "PROPOSAL" in pr and "imaging" in pr and "owner confirmation required" in pr

    gap = handle_demand("reconstruct my CASSI computational imaging scene", plane="singularity")
    gr = render_proposal("reconstruct my CASSI computational imaging scene", gap)
    assert "CAPABILITY GAP" in gr
