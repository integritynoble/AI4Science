from ai4science.harness.agents.manager.monitor import registry_view, run_status, agent_lkg
from ai4science.harness.agents.spec import AgentSpec

SPECS = [AgentSpec(name="work", tier="open", category="core", title="General Work",
                   description="d", keywords=("coding",), supported_profiles=("I0", "I1", "I2"))]


def test_registry_view_shape():
    view = registry_view(SPECS)
    assert view == [{"name": "work", "title": "General Work", "tier": "open",
                     "category": "core", "profiles": ["I0", "I1", "I2"], "keywords": ["coding"]}]


def test_run_status_fail_safe_on_none_client():
    assert run_status(None, "r1") == {"active": False, "stop_reason": "no client"}


def test_run_status_reads_client():
    class C:
        def tripwire_triggered(self, run_id):
            return False   # not tripped -> active
    assert run_status(C(), "r1") == {"active": True, "stop_reason": None}


def test_run_status_fail_safe_on_raise():
    class C:
        def tripwire_triggered(self, run_id):
            raise RuntimeError("down")
    assert run_status(C(), "r1")["active"] is False


def test_agent_lkg_fail_safe():
    assert agent_lkg(None, "work") is None
    class C:
        def get_last_known_good(self, kind, name):
            return {"metadata": {"prompt_profile": "terse"}}
    assert agent_lkg(C(), "work")["metadata"]["prompt_profile"] == "terse"
