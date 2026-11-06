# AI4Science test flake and slow-test inventory

Base: `e22e98663f35109f9a9f0a843c4a689658230e25` (public origin/main). Measured 2026-11-06. Report only; tests and source were unchanged for all three runs.

## Environment and method

- Machine class: x86-64 laptop-class CPU, AMD Ryzen 7 2700U, 8 logical CPUs, approximately 15.2 GiB RAM. Four CPUs were allowed by affinity; the runner and descendants used nice 19. Each BLAS/OpenMP thread limit was 1; pytest ran serially.
- Python 3.12.3; Ubuntu 24.04.4 LTS; Linux kernel 7.0.0-31-generic, x86_64.
- Editable installation: `.[dev,research-agents]`, plus `uvicorn` as authorized for collection. Installed through uv into the job virtual environment; no system package changes.
- A preliminary collection attempt before the approved setup adjustment stopped with missing imports; it is not counted as one of these three runs.
- Three consecutive fresh pytest processes, same environment and exclusions. Command: `.venv/bin/python -m pytest -q -rA --durations=40 --junitxml=run<N>.xml`, plus the module exclusions listed below and an observation-only plugin that logged original test IDs and phase timings.
- Filesystem namespace mapped its temporary directory to job-local storage, including hard-coded temporary paths. An isolated HOME and a minimal environment prevented use of existing login state or API keys. External networking was disabled; local sockets remained available. No model calls, credentials, dataset downloads, paid APIs or cloud compute were used.
- JUnit XML, logs, observer and analysis files remain untracked in job-local temporary storage. Only this report is committed. All three runs reached normal pytest completion; exit 1 denotes failed tests, not a crashed run.
- Flaky means a test ID has different outcomes across the three runs. Slow means combined setup, call and teardown exceeds 10 s in any run; timings below are JUnit seconds. Causes are source-based inferences unless marked unknown. Serial runs preserve default collection order, so this is not a shuffled-order experiment.

Selected package versions: pytest 9.2.0, numpy 2.5.4, scipy 1.18.1, uvicorn 0.54.0, rdkit 2026.9.1, pydicom 3.0.2, pillow 13.0.0, httpx 0.28.1, pydantic 2.14.3, optiland 0.6.3, rayoptics 0.9.10.

## Per-run outcomes

JUnit includes skipped modules as collection-skip entries. Expected failures are shown separately from ordinary skips. Wall time includes process startup/exit; pytest time is the XML suite time.

| Run | Passed | Failed | Skipped | Xfailed | Errors | Pytest time (s) | Wall time (s) | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4344 | 95 | 69 | 3 | 0 | 1058.973 | 1089.393 | 1 |
| 2 | 4345 | 94 | 69 | 3 | 0 | 904.440 | 933.858 | 1 |
| 3 | 4344 | 95 | 69 | 3 | 0 | 1278.196 | 1316.679 | 1 |

Compared 4,511 identical test/collection IDs across all runs: **2 flaky**, **20 slow**, and **94 consistently failing**. The checkout contains 429 test files; 13 modules were explicitly excluded as authorized because their external control-plane dependency is unavailable.

## Flaky tests

Failure excerpts preserve the assertion or exception text while removing machine-specific information.

| File | Full test ID | R1 | R2 | R3 | Likely cause | Failure message |
| --- | --- | --- | --- | --- | --- | --- |
| `tests/dli/test_delegation_agent.py` | `tests/dli/test_delegation_agent.py::test_an_executor_that_cannot_succeed_is_never_reported_as_done[1-t3.search_latency]` | failed | passed | passed | Clock: speedup thresholds compare timed CPU workloads; load drift can make an unchanged solver appear faster. | R1: AssertionError: assert not True; the verifier returned Verdict(passed=True) for an unchanged candidate (speedup_fraction=0.368018; result_fidelity=1.0). |
| `tests/dli/test_level_agents.py` | `tests/dli/test_level_agents.py::test_certification_requires_both_halves[DL3]` | passed | passed | failed | Likely clock/deadline: DL3 certifies timed search; seed 0 was not accepted. Acceptance checks have a 120 s deadline. The failing subcheck and exact cause are unknown. | R3: AssertionError: assert False + where False = Certification(level='DL3', band='T3', in_band=[('t3.search_latency', 0, False), ('t3.search_latency', 1, True)], refus... Refusing rather than attempting it and reporting a level it did not reach.')], executor='scripted (offline)', note='').passed |

## Slow tests

All tests exceeding 10 s in any run are listed, including a test that is slow in only one run.

| Full test ID | R1 (s) | R2 (s) | R3 (s) | Likely cause |
| --- | ---: | ---: | ---: | --- |
| `tests/dli/test_level_agents.py::test_certification_requires_both_halves[DL3]` | 54.215 | 41.924 | 195.916 | CPU work: local DL3 certification runs multiple search tasks, criteria and verifiers; no model calls. |
| `tests/dli/test_delegation_agent.py::test_an_executor_that_cannot_succeed_is_never_reported_as_done[0-t3.search_latency]` | 41.910 | 37.388 | 157.909 | Clock/CPU benchmark: repeated search-result equivalence and speed checks, including repeated original/candidate timings. |
| `tests/dli/test_delegation_agent.py::test_an_executor_that_cannot_succeed_is_never_reported_as_done[2-t3.search_latency]` | 37.535 | 40.396 | 144.648 | Clock/CPU benchmark: repeated search-result equivalence and speed checks, including repeated original/candidate timings. |
| `tests/dli/test_dli_bench.py::test_the_regime_switch_family_is_harder_than_the_single_forms` | 134.122 | 65.760 | 76.315 | CPU work: fit three candidate hidden-law families and verify across 14 seeds. |
| `tests/dli/test_level_agents.py::test_each_level_holds_its_own_band[DL3]` | 112.295 | 41.413 | 67.401 | CPU work: local DL3 certification runs multiple search tasks, criteria and verifiers; no model calls. |
| `tests/dli/test_delegation_agent.py::test_the_harness_turns_a_careless_solver_into_an_accepted_result[2-t3.search_latency]` | 64.747 | 44.903 | 94.130 | Clock/CPU benchmark: repeated search-result equivalence and speed checks, including repeated original/candidate timings. |
| `tests/learning/test_quiz_check.py::test_source_tamper_fails` | 58.089 | 0.002 | 0.003 | Unknown: delay is in fixture setup, not the test body; CPU scheduling, filesystem work or fixture state may contribute. |
| `tests/dli/test_dli_bench.py::test_a_slow_solver_is_named_slow_rather_than_timing_out_the_runner` | 56.160 | 57.164 | 55.885 | Fixed sleep/deadline: generated solver sleeps 11 s; verifier checks the 10 s per-instance limit and stops remaining instances. |
| `tests/dli/test_delegation_agent.py::test_an_executor_that_cannot_succeed_is_never_reported_as_done[1-t3.search_latency]` | 52.704 | 31.535 | 39.199 | Clock/CPU benchmark: repeated search-result equivalence and speed checks, including repeated original/candidate timings. |
| `tests/dli/test_level_agents.py::test_each_level_refuses_the_band_above[DL3]` | 48.260 | 22.372 | 31.845 | CPU work: local DL3 certification runs multiple search tasks, criteria and verifiers; no model calls. |
| `tests/dli/test_delegation_agent.py::test_the_harness_turns_a_careless_solver_into_an_accepted_result[0-t3.search_latency]` | 44.999 | 33.203 | 28.705 | Clock/CPU benchmark: repeated search-result equivalence and speed checks, including repeated original/candidate timings. |
| `tests/dli/test_delegation_agent.py::test_the_harness_turns_a_careless_solver_into_an_accepted_result[1-t3.search_latency]` | 44.624 | 36.283 | 31.039 | Clock/CPU benchmark: repeated search-result equivalence and speed checks, including repeated original/candidate timings. |
| `tests/dli/test_delegation_agent.py::test_routing_recovers_when_the_first_executor_cannot_do_it[t3.search_latency]` | 25.878 | 38.647 | 30.071 | Clock/CPU benchmark: repeated search-result equivalence and speed checks, including repeated original/candidate timings. |
| `tests/dli/test_dli_bench.py::test_plausible_wrong_answer_fails[t3.search_latency]` | 18.957 | 32.163 | 26.101 | Clock/CPU benchmark: search verifier checks fidelity and compares original/candidate wall-clock speed. |
| `tests/dli/test_dli_bench.py::test_every_verifier_says_what_it_misses[t3.search_latency]` | 17.770 | 18.533 | 28.917 | Clock/CPU benchmark: search verifier checks fidelity and compares original/candidate wall-clock speed. |
| `tests/dli/test_dli_bench.py::test_doing_nothing_fails[t3.search_latency]` | 17.541 | 27.672 | 22.925 | Clock/CPU benchmark: search verifier checks fidelity and compares original/candidate wall-clock speed. |
| `tests/dli/test_dli_bench.py::test_correct_solution_passes[t3.search_latency]` | 9.137 | 18.988 | 12.024 | Clock/CPU benchmark: search verifier checks fidelity and compares original/candidate wall-clock speed. |
| `tests/sarsi/test_acp_backend.py::test_a_real_peer_that_goes_quiet_is_silent_and_the_deadline_holds` | 18.070 | 18.059 | 18.040 | Fixed sleep/deadline: real local fake peer goes silent; test waits for protocol deadlines and process cleanup. |
| `tests/test_optics_phase0.py::test_optics_phase0` | 14.650 | 5.554 | 3.692 | Network/import setup: optics checks attempt external resource access; external networking is disabled. Exact time attribution unknown. |
| `tests/dli/test_dli_bench.py::test_the_t4_search_class_separates_feasible_from_optimal` | 4.588 | 4.822 | 13.658 | CPU work: build and verify exact and greedy shift-schedule solvers, checking optimality as well as feasibility. |

## Environment skips by reason

Counts below are entries per run, not pooled totals. Collection skips count one entry per module; ignored modules are not included in these counts.

| Reason | R1 | R2 | R3 |
| --- | ---: | ---: | ---: |
| claude CLI not available: 'claude' is not on PATH | 2 | 2 | 2 |
| could not import 'claude_agent_sdk': No module named 'claude_agent_sdk' | 5 | 5 | 5 |
| could not import 'pwm_control_plane': No module named 'pwm_control_plane' | 11 | 11 | 11 |
| could not import 'pyte': No module named 'pyte' | 2 | 2 | 2 |
| dude not fetched on this machine (python3 -m ai4science.harness.agents.research_agents.runners.fetch dude) | 9 | 9 | 9 |
| kvasir-capsule not fetched on this machine (python3 -m ai4science.harness.agents.research_agents.runners.fetch kvasir-capsule) | 4 | 4 | 4 |
| ldct not fetched on this machine (python3 -m ai4science.harness.agents.research_agents.runners.fetch ldct) | 5 | 5 | 5 |
| library v0.2 not present on this machine | 1 | 1 | 1 |
| methylation-age not fetched on this machine (python3 -m ai4science.harness.agents.research_agents.runners.fetch methylation-age) | 6 | 6 | 6 |
| external framework checkout unavailable | 4 | 4 | 4 |
| no tmux on this machine | 1 | 1 | 1 |
| open-kbp not fetched on this machine (python3 -m ai4science.harness.agents.research_agents.runners.fetch open-kbp) | 1 | 1 | 1 |
| requires external PWM checkout (set PWM_REPO_ROOT) | 4 | 4 | 4 |
| set SARSI_LIVE_TEST=1 to run | 3 | 3 | 3 |
| tcga-survival not fetched on this machine (python3 -m ai4science.harness.agents.research_agents.runners.fetch tcga-survival) | 7 | 7 | 7 |
| v0.2 dataset not present on this machine | 4 | 4 | 4 |

Expected failures (one entry for each reason per run):

- Core-menu composition is pending an upstream product decision.
- Local research-spec ownership is pending an upstream package-contract decision.
- Full-screen input handling swallows SIGINT; the test marks the cause as unresolved.

No corpora were fetched. Dataset references remain links; see the [repository corpus/fetch implementation](../../ai4science/harness/agents/research_agents/runners/fetch/__init__.py) and the [CAVE multispectral dataset](https://cave.cs.columbia.edu/repository/Multispectral). Missing CAVE data produced failures rather than skips in nine imaging tests.

## Not collectable: external control-plane package

`pwm_control_plane` is unavailable and is not provided by this checkout. Under the operator-approved scope adjustment, the following 13 modules were ignored identically in all runs. They are not counted as skips or completed tests. Modules that already use `pytest.importorskip` remained included and skipped themselves.

- `tests/imaging/test_agent_e2e.py` — not collectable: `pwm_control_plane` unavailable.
- `tests/imaging/test_foundry_agent_e2e.py` — not collectable: `pwm_control_plane` unavailable.
- `tests/imaging/test_imaging_external_eval_integration.py` — not collectable: `pwm_control_plane` unavailable.
- `tests/imaging/test_llm_e2e.py` — not collectable: `pwm_control_plane` unavailable.
- `tests/imaging/test_rsi_round_integration.py` — not collectable: `pwm_control_plane` unavailable.
- `tests/imaging/test_rsi_search_integration.py` — not collectable: `pwm_control_plane` unavailable.
- `tests/learning/test_learning_foundry_e2e.py` — not collectable: `pwm_control_plane` unavailable.
- `tests/process_learning/test_process_learning_foundry_e2e.py` — not collectable: `pwm_control_plane` unavailable.
- `tests/research/test_research_foundry_e2e.py` — not collectable: `pwm_control_plane` unavailable.
- `tests/runtime/test_pev_e2e.py` — not collectable: `pwm_control_plane` unavailable.
- `tests/social/test_social_foundry_e2e.py` — not collectable: `pwm_control_plane` unavailable.
- `tests/social/test_social_integration.py` — not collectable: `pwm_control_plane` unavailable.
- `tests/work/test_work_foundry_e2e.py` — not collectable: `pwm_control_plane` unavailable.

## Consistently failing tests and limitations

Identical failure outcomes are not flakes. Common environment causes include absent separately distributed agent packages and SDKs, missing CAVE corpus, unavailable external checkouts/interpreter locations, and blocked optics resource access. Temporary directories live under a checkout, which can affect tests that assume no enclosing project marker. Other assertions may be base-commit defects; a repeated failure alone does not establish a root cause.

| Full test ID | Representative failure message (R1) |
| --- | --- |
| `tests/docs/test_design_docs_consistent.py::test_the_scope_objects_still_validate_where_they_now_live` | FileNotFoundError: documentation validator selects an unavailable hard-coded external interpreter. |
| `tests/imaging/test_agent_hostsim.py::test_i0_pauses_at_reconstruction_fork` | ai4science.harness.agents.research_agents.runners.corpus.CorpusMissing: CAVE multispectral — real 512x512x31 hyperspectral scenes is not on this machine. |
| `tests/imaging/test_agent_hostsim.py::test_i2_delivers_physics_verified_reconstruction` | ai4science.harness.agents.research_agents.runners.corpus.CorpusMissing: CAVE multispectral — real 512x512x31 hyperspectral scenes is not on this machine. |
| `tests/imaging/test_agent_planner_injection.py::test_injected_planner_is_used` | ai4science.harness.agents.research_agents.runners.corpus.CorpusMissing: CAVE multispectral — real 512x512x31 hyperspectral scenes is not on this machine. |
| `tests/imaging/test_benchmark.py::test_seed_populates_workspace` | ai4science.harness.agents.research_agents.runners.corpus.CorpusMissing: CAVE multispectral — real 512x512x31 hyperspectral scenes is not on this machine. |
| `tests/imaging/test_benchmark.py::test_seeded_benchmark_is_solvable_ground_truth_passes_judge` | ai4science.harness.agents.research_agents.runners.corpus.CorpusMissing: CAVE multispectral — real 512x512x31 hyperspectral scenes is not on this machine. |
| `tests/imaging/test_loop_closure.py::test_run_imaging_task_uses_promoted_config` | ai4science.harness.agents.research_agents.runners.corpus.CorpusMissing: CAVE multispectral — real 512x512x31 hyperspectral scenes is not on this machine. |
| `tests/imaging/test_payload_accurate.py::test_regenerated_docs_still_judge_valid` | ai4science.harness.agents.research_agents.runners.corpus.CorpusMissing: CAVE multispectral — real 512x512x31 hyperspectral scenes is not on this machine. |
| `tests/imaging/test_rsi_round.py::test_round_ranks_by_cp_scores` | ai4science.harness.agents.research_agents.runners.corpus.CorpusMissing: CAVE multispectral — real 512x512x31 hyperspectral scenes is not on this machine. |
| `tests/imaging/test_rsi_round.py::test_run_rsi_round_threads_domain` | ai4science.harness.agents.research_agents.runners.corpus.CorpusMissing: CAVE multispectral — real 512x512x31 hyperspectral scenes is not on this machine. |
| `tests/machine/test_claude_driver.py::test_ensure_governance_hook_also_wires_the_stop_check` | KeyError: 'Stop' |
| `tests/sarsi/test_backends.py::test_both_backends_exist_and_name_a_real_spec` | AssertionError: ('sarsi-claude', 'claude-code') |
| `tests/sarsi/test_imaging_agent_in_the_roster.py::test_it_is_built_on_the_field_spec_that_actually_exists` | AssertionError: the roster names a spec nobody ships |
| `tests/sarsi/test_memory_loop_examples.py::test_but_two_different_failures_stay_apart` | AssertionError: assert not [{'schema_version': 1, 'memory_id': 'sem_588668c760', 'op': 'assert', 'supersedes': None, ...}] |
| `tests/sarsi/test_writable_in_tool_description.py::test_the_spec_built_registry_carries_them_too` | KeyError: 'unified-LLM' |
| `tests/test_chat.py::test_chat_mode_resolves_known_agent` | AssertionError: assert 'general-purpose' == 'computational-imaging' |
| `tests/test_chat.py::test_chat_research_uses_harness` | AssertionError: assert 'general-purpose' == 'research' |
| `tests/test_chat.py::test_chat_unknown_mode_falls_back_to_common` | AssertionError: assert 'general-purpose' == 'unified-LLM' |
| `tests/test_chat.py::test_list_sessions_handles_empty` | ModuleNotFoundError: No module named 'claude_agent_sdk' |
| `tests/test_chat.py::test_list_sessions_prints_past_sessions` | ModuleNotFoundError: No module named 'claude_agent_sdk' |
| `tests/test_claude_codex_via_packages.py::test_passthrough_agent_sourced_from_package[claude-code-claude_code.py-anthropic]` | assert (None is not None) |
| `tests/test_claude_codex_via_packages.py::test_passthrough_agent_sourced_from_package[codex-codex.py-openai]` | assert (None is not None) |
| `tests/test_commands_plugins_test.py::test_agent_into_open_main_warns` | assert 1 == 0 |
| `tests/test_commands_plugins_test.py::test_agent_plugin_dispatchable_from_research` | AssertionError: target agent is not a known agent; CLI exited 1. |
| `tests/test_commands_plugins_test.py::test_free_skips_login_and_gate` | assert 1 == 0 |
| `tests/test_commands_plugins_test.py::test_into_other_agent` | assert (1 == 0) |
| `tests/test_commands_plugins_test.py::test_launch_receives_model_and_workspace` | IndexError: list index out of range |
| `tests/test_commands_plugins_test.py::test_logged_in_turns_gate_on` | AssertionError: target agent is not a known agent; CLI exited 1. |
| `tests/test_commands_plugins_test.py::test_tool_embeds_into_research` | AssertionError: target agent is not a known agent; CLI exited 1. |
| `tests/test_compute_tools.py::test_compute_capability_in_all_modes` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_cross_call.py::test_research_is_dispatch_target_when_installed` | AssertionError: assert None is not None |
| `tests/test_dispatch_hint.py::test_task_tool_returns_install_hint_for_known_uninstalled_agent` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_dispatch_hint.py::test_task_tool_still_reports_unknown_for_unrecognized_name` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_drug_cancer_agents.py::test_cancer_agent_in_registry` | assert None is not None |
| `tests/test_drug_cancer_agents.py::test_cancer_aliases` | AssertionError: alias 'oncology' not found |
| `tests/test_drug_cancer_agents.py::test_drug_design_agent_in_registry` | assert None is not None |
| `tests/test_drug_cancer_agents.py::test_drug_design_aliases` | AssertionError: alias 'drug' not found |
| `tests/test_drug_cancer_agents.py::test_new_agents_are_science_tier` | AttributeError: 'NoneType' object has no attribute 'tier' |
| `tests/test_forward_model_tools.py::test_ci_and_research_specs_have_forward_model_capability` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_agent_plugins.py::test_agent_plugin_name_collision_skipped` | AssertionError: assert 'plugin' == 'builtin' |
| `tests/test_harness_agent_plugins.py::test_agent_plugin_registered_and_dispatchable` | AttributeError: 'NoneType' object has no attribute 'tier' |
| `tests/test_harness_agent_plugins.py::test_tool_plugin_bundle_and_attach_to` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_agent_plugins.py::test_tool_plugin_no_factory_is_graceful` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_agents_dispatch.py::test_common_dispatch_excludes_science` | AttributeError: 'NoneType' object has no attribute 'tier' |
| `tests/test_harness_agents_dispatch.py::test_main_has_task_tool_subagent_does_not` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_agents_dispatch.py::test_research_dispatch_includes_science` | AttributeError: 'NoneType' object has no attribute 'tier' |
| `tests/test_harness_agents_dispatch.py::test_task_tool_exposes_enum` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_agents_dispatch.py::test_task_tool_rejects_out_of_tier` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_agents_dispatch.py::test_task_tool_runs_child` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_agents_moat.py::test_common_is_walled_off` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_agents_moat.py::test_science_agents_hold_the_moat` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_agents_registry.py::test_agent_picker_lists_core_and_specific` | AssertionError: assert {'cancer', 'c...'drug-design'} <= {'imaging', '...physics', ...} |
| `tests/test_harness_agents_registry.py::test_menu_partitions_core_vs_specific` | AssertionError: assert 'unified-LLM' in {'learning', 'machine', 'manager', 'openclaw', 'opencode', 'pocket', ...} |
| `tests/test_harness_agents_registry.py::test_search_finds_by_keyword` | AssertionError: assert 'computational-imaging' in ['imaging'] |
| `tests/test_harness_agents_registry.py::test_ships_expected_agents` | AssertionError: assert {'computation...'unified-LLM'} <= {'general-pur...manager', ...} |
| `tests/test_harness_algorithm_tools.py::test_open_agents_have_no_ci_tools` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_algorithm_tools.py::test_science_agents_have_ci_tools` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_cassi_integration.py::test_ci_agent_has_cassi_tools_common_does_not` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_onboard_integration.py::test_bundle_registered` | AssertionError: assert 'onboarding' in {'pwm-actions': <function _pwm_actions at <address>>, 'pwm-data': <function _pwm_data at <address>>, 'paper-...on _paper_review at <address>>, 'computational-imaging': <function _computational_imaging at <address>>, ...} |
| `tests/test_harness_onboard_integration.py::test_research_has_onboarding_common_does_not` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_paper_integration.py::test_paper_agent_has_review_tool_common_does_not` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_paper_integration.py::test_paper_in_core_menu` | AssertionError: assert 'paper' in {'learning', 'machine', 'manager', 'openclaw', 'opencode', 'pocket', ...} |
| `tests/test_harness_paper_integration.py::test_paper_spec_discovered` | assert (None is not None) |
| `tests/test_harness_recap.py::test_repl_prints_recap_line` | AttributeError: 'NoneType' object has no attribute 'name' |
| `tests/test_harness_recap.py::test_repl_skips_recap_on_quick_turns` | AttributeError: 'NoneType' object has no attribute 'name' |
| `tests/test_harness_repl.py::test_repl_exit_slash_stops_loop` | AttributeError: 'NoneType' object has no attribute 'name' |
| `tests/test_harness_repl.py::test_repl_model_switch` | AttributeError: 'NoneType' object has no attribute 'name' |
| `tests/test_harness_repl.py::test_repl_runs_turn_and_streams_text` | AttributeError: 'NoneType' object has no attribute 'name' |
| `tests/test_harness_repl.py::test_run_common_repl_wires_per_edit_confirm` | AttributeError: 'NoneType' object has no attribute 'name' |
| `tests/test_harness_repl_mentions.py::test_repl_expands_mentions_on_turn` | AttributeError: 'NoneType' object has no attribute 'name' |
| `tests/test_harness_repl_modes.py::test_build_main_registry_for_spec` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_harness_repl_modes.py::test_mode_menu_text_lists_core_and_specific` | assert ('unified-LLM' in '[agents]\n learning Governed tutor: grounded study guide + quiz over staged material (A1).\n machine ...— /agent specific <query> to search\n switch with: /agent <name> (e.g. /agent Claude, /agent "Computational Imaging")') |
| `tests/test_harness_repl_modes.py::test_mode_specific_search_text` | AssertionError: assert 'computational-imaging' in ' imaging Computational Imaging' |
| `tests/test_harness_repl_slash.py::test_mode_toggle_preserves_history` | AttributeError: 'NoneType' object has no attribute 'name' |
| `tests/test_harness_resume.py::test_run_common_repl_seeds_resume_history` | AttributeError: 'NoneType' object has no attribute 'name' |
| `tests/test_harness_tool_display.py::test_repl_prints_tool_lines_and_footer` | AttributeError: 'NoneType' object has no attribute 'name' |
| `tests/test_modes_claude_codex.py::test_aliases_resolve` | AttributeError: 'NoneType' object has no attribute 'name' |
| `tests/test_modes_claude_codex.py::test_claude_code_and_codex_registered` | assert (None is not None) |
| `tests/test_modes_claude_codex.py::test_codex_binds_codex_backend_claude_binds_anthropic` | AttributeError: 'NoneType' object has no attribute 'default_backend' |
| `tests/test_optics_phase0.py::test_optics_phase0` | AssertionError: phase0 optics checks failed; external resource access has temporary name-resolution failures in the network-isolated environment. |
| `tests/test_phase3_agents_via_packages.py::test_agent_sourced_from_package[cancer-cancer.py]` | assert (None is not None) |
| `tests/test_phase3_agents_via_packages.py::test_agent_sourced_from_package[computational-imaging-computational_imaging.py]` | assert (None is not None) |
| `tests/test_phase3_agents_via_packages.py::test_agent_sourced_from_package[drug-design-drug_design.py]` | assert (None is not None) |
| `tests/test_phase3_agents_via_packages.py::test_agent_sourced_from_package[paper-paper.py]` | assert (None is not None) |
| `tests/test_phase3_agents_via_packages.py::test_agent_sourced_from_package[unified-LLM-unified_llm.py]` | assert (None is not None) |
| `tests/test_phase3_agents_via_packages.py::test_unified_is_default_and_open_tier` | AttributeError: 'NoneType' object has no attribute 'tier' |
| `tests/test_registry_router_tools.py::test_ci_and_research_specs_have_science_router` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_registry_standard_enforced.py::test_both_have_science_router_capability` | AttributeError: 'NoneType' object has no attribute 'capabilities' |
| `tests/test_registry_standard_enforced.py::test_ci_agent_enforces_standard` | AssertionError: could not find the agent's prompt text field |
| `tests/test_registry_standard_enforced.py::test_research_agent_enforces_standard` | AssertionError: could not find the agent's prompt text field |
| `tests/test_sdk_repl.py::test_sdk_available_requires_cli` | AssertionError: assert (False is False and 'claude CLI' in 'claude-agent-sdk not installed — pip install claude-agent-sdk') |
| `tests/test_sdk_repl.py::test_sdk_available_true_when_sdk_and_cli_present` | assert (False is True) |
| `tests/test_unknown_slash.py::test_a_chat_spec_resolves_to_the_chat_agent` | AssertionError: assert 'unknown' == 'spec' |
| `tests/test_workspace_resolve.py::test_nearest_project_root_none_when_no_marker` | AssertionError: nearest_project_root returned the enclosing checkout rather than None. |

Three runs can reveal observed instability but cannot establish its full frequency or prove other tests deterministic. Results apply to the stated base, dependency versions, isolated environment and collection scope. No fixes or extra targeted reruns were performed.
