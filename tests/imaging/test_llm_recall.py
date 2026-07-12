from ai4science.harness.agents.imaging.llm.recall import recall_cpu_cassi_solvers

def test_recall_returns_list_and_never_raises():
    solvers = recall_cpu_cassi_solvers()
    assert isinstance(solvers, list)

def test_recall_finds_cpu_cassi_solvers_when_available():
    solvers = recall_cpu_cassi_solvers()
    if not solvers:
        return  # algorithm_base not importable in this environment — best-effort by design
    by_key = {s["key"]: s for s in solvers}
    assert "best_quality" in by_key                       # a real CPU CASSI solver
    assert by_key["best_quality"]["cfg"]["lam"] == 0.01    # recalled config drives the reconstruction
    assert all(isinstance(s["cfg"]["iters"], int) for s in solvers)
