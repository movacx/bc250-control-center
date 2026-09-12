from pathlib import Path

from bc250cc.infrastructure.external_tools.catalog import (
    EXTERNAL_TOOL_LIFECYCLES,
    EXTERNAL_TOOLS,
    ExternalToolAdapter,
    ExternalToolSpec,
    GitCheckoutReader,
    LifecycleAction,
    validate_external_tool_manifest,
)


class GitReader:
    def __init__(self, *, origin="", revision="", dirty=False):
        self._origin = origin
        self._revision = revision
        self._dirty = dirty

    def origin(self, _path):
        return self._origin

    def revision(self, _path):
        return self._revision

    def dirty(self, _path):
        return self._dirty


def test_integrated_manifest_passes_executable_policy_gate():
    assert validate_external_tool_manifest() == {}
    assert all(spec.adoption_ready for spec in EXTERNAL_TOOLS.values())


def test_undeclared_upstream_license_is_an_explicit_release_gate():
    for key in ("cu_manager_standard", "cu_manager_steamos"):
        spec = EXTERNAL_TOOLS[key]
        assert spec.adoption_ready is True
        assert spec.redistribution_ready is False
        assert "do not bundle" in spec.release_gates[0]
        assert spec.payload_distribution == "runtime-fetch-reviewed-revision"
        assert spec.bundled_payload is False
        payload = spec.to_dict()
        assert payload["redistribution_ready"] is False
        assert payload["release_gates"] == list(spec.release_gates)
    assert EXTERNAL_TOOLS["cyan_smu"].redistribution_ready is True
    assert EXTERNAL_TOOLS["cyan_smu"].release_gates == ()
    assert EXTERNAL_TOOLS["cpu_smu_oc"].bundled_payload is True
    assert EXTERNAL_TOOLS["cpu_smu_oc"].redistribution_ready is True
    assert EXTERNAL_TOOLS["gfx1013_direct"].payload_distribution == "runtime-fetch-reviewed-revision"
    assert EXTERNAL_TOOLS["gfx1013_direct"].update_strategy == "reviewed-commit"


def test_privileged_automation_requires_immutable_revision_and_rollback():
    spec = ExternalToolSpec(
        "bad", "http://example.test/tool", "", "main", "live-hardware", True, True, "", "none"
    )
    issues = spec.validation_issues()
    assert len(issues) == 4


def test_unlicensed_payload_can_only_remain_runtime_fetch_or_reference_only():
    bundled = ExternalToolSpec(
        "bad-bundle", "https://example.test/tool", "not-declared-upstream",
        "a" * 40, "live-hardware", True, True, "restore it", "mocked",
        payload_distribution="bundled-reviewed-snapshot",
    )
    invalid_mode = ExternalToolSpec(
        "bad-mode", "https://example.test/tool", "MIT", "a" * 40,
        "live-hardware", True, True, "restore it", "mocked",
        payload_distribution="copy-whatever-is-current",
    )

    assert "bundled payload requires a declared upstream license" in bundled.validation_issues()
    assert "payload distribution mode is invalid" in invalid_mode.validation_issues()


def test_adapter_verifies_exact_clean_checkout(tmp_path):
    destination = tmp_path / "tool"
    (destination / ".git").mkdir(parents=True)
    spec = EXTERNAL_TOOLS["cpu_smu_oc"]
    evidence = ExternalToolAdapter(
        spec,
        destination,
        GitReader(origin=spec.upstream, revision=spec.reviewed_revision, dirty=False),
    ).inspect()
    assert evidence.verified


def test_adapter_rejects_wrong_origin_revision_or_dirty_tree(tmp_path):
    destination = tmp_path / "tool"
    (destination / ".git").mkdir(parents=True)
    spec = EXTERNAL_TOOLS["core_unlock"]
    evidence = ExternalToolAdapter(
        spec,
        destination,
        GitReader(origin="https://example.test/fork", revision="0" * 40, dirty=True),
    ).inspect()
    assert not evidence.verified
    assert not evidence.origin_matches
    assert not evidence.revision_matches
    assert evidence.dirty


def test_missing_checkout_never_calls_git_reader(tmp_path):
    class ExplodingReader:
        def __getattr__(self, _name):
            raise AssertionError("Git reader must not run for a missing checkout")

    evidence = ExternalToolAdapter(
        EXTERNAL_TOOLS["nct6687"], Path(tmp_path / "missing"), ExplodingReader()
    ).inspect()
    assert not evidence.verified
    assert evidence.dirty is None


def test_every_tool_has_a_complete_lifecycle_contract():
    assert EXTERNAL_TOOL_LIFECYCLES.keys() == EXTERNAL_TOOLS.keys()
    for lifecycle in EXTERNAL_TOOL_LIFECYCLES.values():
        assert lifecycle.validation_issues() == ()
        assert LifecycleAction.CHECK in lifecycle.actions


def test_reviewed_gfx1013_manifest_exposes_confirmed_install_lifecycle(tmp_path):
    adapter = ExternalToolAdapter(
        EXTERNAL_TOOLS["gfx1013_direct"], tmp_path / "missing", GitReader()
    )
    plan = adapter.plan(LifecycleAction.INSTALL)
    assert plan.available
    assert not plan.hardware_writes
    assert plan.requires_confirmation
    assert plan.reasons == ()


def test_standard_cu_manifest_does_not_expose_generic_hardware_apply(tmp_path):
    spec = EXTERNAL_TOOLS["cu_manager_standard"]
    destination = tmp_path / "cu"
    (destination / ".git").mkdir(parents=True)
    adapter = ExternalToolAdapter(
        spec,
        destination,
        GitReader(origin=spec.upstream, revision=spec.reviewed_revision, dirty=False),
    )

    assert "CPU core unlock" in EXTERNAL_TOOL_LIFECYCLES["cu_manager_standard"].user_vocabulary
    assert not adapter.plan(LifecycleAction.APPLY).available


def test_verified_hardware_apply_plan_is_explicitly_high_risk(tmp_path):
    destination = tmp_path / "tool"
    (destination / ".git").mkdir(parents=True)
    spec = EXTERNAL_TOOLS["core_unlock"]
    adapter = ExternalToolAdapter(
        spec,
        destination,
        GitReader(origin=spec.upstream, revision=spec.reviewed_revision, dirty=False),
    )
    plan = adapter.plan("apply")
    assert plan.available
    assert plan.hardware_writes
    assert plan.requires_confirmation
    assert plan.privilege_class == "live-hardware-reboot"


def test_apply_plan_fails_closed_for_unverified_checkout(tmp_path):
    adapter = ExternalToolAdapter(
        EXTERNAL_TOOLS["cpu_smu_oc"], tmp_path / "missing", GitReader()
    )
    plan = adapter.plan("apply")
    assert not plan.available
    assert "exact clean reviewed checkout" in plan.reasons[0]


def test_read_only_probe_produces_typed_health_report(tmp_path):
    destination = tmp_path / "tool"
    (destination / ".git").mkdir(parents=True)
    spec = EXTERNAL_TOOLS["cyan_smu"]
    adapter = ExternalToolAdapter(
        spec,
        destination,
        GitReader(origin=spec.upstream, revision=spec.reviewed_revision, dirty=False),
        read_only_probe=lambda: {"healthy": True, "service": "active"},
    )
    report = adapter.report()
    assert report.healthy
    assert report.health["service"] == "active"


def test_probe_failure_is_data_not_a_global_exception(tmp_path):
    def broken_probe():
        raise RuntimeError("backend unavailable")

    adapter = ExternalToolAdapter(
        EXTERNAL_TOOLS["nct6687"],
        tmp_path / "missing",
        GitReader(),
        read_only_probe=broken_probe,
    )
    report = adapter.report()
    assert not report.healthy
    assert report.health_error == "backend unavailable"


def test_production_git_reader_uses_fixed_argv_and_fails_closed(tmp_path):
    calls = []

    def runner(command, timeout):
        calls.append((command, timeout))
        operation = tuple(command[3:])
        if operation == ("remote", "get-url", "origin"):
            return 0, "https://example.test/tool.git\n", ""
        if operation == ("rev-parse", "--verify", "HEAD"):
            return 0, "a" * 40 + "\n", ""
        if operation == ("status", "--porcelain", "--untracked-files=all"):
            return 0, "", ""
        raise AssertionError(operation)

    reader = GitCheckoutReader(runner)
    assert reader.origin(tmp_path) == "https://example.test/tool.git"
    assert reader.revision(tmp_path) == "a" * 40
    assert reader.dirty(tmp_path) is False
    assert reader.status_details(tmp_path) == {
        "available": True,
        "tracked_dirty": False,
        "untracked_count": 0,
    }
    assert all(call[0][:3] == ["git", "-C", str(tmp_path)] for call in calls)
    assert all(call[1] == 2 for call in calls)

    failed = GitCheckoutReader(lambda *_args, **_kwargs: (1, "partial", "error"))
    assert failed.origin(tmp_path) == ""
    assert failed.revision(tmp_path) == ""
    assert failed.dirty(tmp_path) is None
    assert failed.status_details(tmp_path)["tracked_dirty"] is None


def test_git_reader_separates_untracked_artifacts_from_source_edits(tmp_path):
    status = "?? overclock.conf\n M tracked.py\n?? build/object.o\n"
    reader = GitCheckoutReader(
        lambda command, timeout: (
            (0, status, "")
            if command[3] == "status"
            else (1, "", "unavailable")
        )
    )

    assert reader.dirty(tmp_path) is True
    assert reader.status_details(tmp_path) == {
        "available": True,
        "tracked_dirty": True,
        "untracked_count": 2,
    }
