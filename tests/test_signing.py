import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("build_app", Path(__file__).resolve().parents[1] / "scripts/build_app.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)

FIRST = "A" * 40
SECOND = "B" * 40


@pytest.mark.parametrize("source", ["configuration", "environment", "argument"])
def test_signing_reuses_selected_certificate(monkeypatch, source):
    listing = f'  1) {FIRST} "Apple Development: First"\n  2) {SECOND} "Apple Development: Second"\n'
    monkeypatch.setattr(build.subprocess, "check_output", lambda *args, **kwargs: listing)
    monkeypatch.delenv("ITUNESREMOTE_SIGN_IDENTITY", raising=False)
    configuration = {"identity": FIRST}
    argument = None
    expected = FIRST
    if source in {"environment", "argument"}:
        monkeypatch.setenv("ITUNESREMOTE_SIGN_IDENTITY", SECOND)
        expected = SECOND
    if source == "argument":
        argument, expected = FIRST, FIRST
    assert build.signing_identity(argument, configuration) == (expected, "Apple Development")


def test_signing_picks_sole_valid_certificate_on_first_build(monkeypatch):
    monkeypatch.delenv("ITUNESREMOTE_SIGN_IDENTITY", raising=False)
    monkeypatch.setattr(build.subprocess, "check_output", lambda *args, **kwargs: f'  1) {FIRST} "Apple Development: Test"')
    assert build.signing_identity(None, {}) == (FIRST, "Apple Development")


@pytest.mark.parametrize("listing", ["0 valid identities found", f'1) {SECOND} "Apple Development: Other"'])
def test_missing_pinned_identity_never_falls_back_to_another_certificate_or_ad_hoc(monkeypatch, listing):
    monkeypatch.delenv("ITUNESREMOTE_SIGN_IDENTITY", raising=False)
    monkeypatch.setattr(build.subprocess, "check_output", lambda *args, **kwargs: listing)
    with pytest.raises(ValueError, match="festgelegte Signaturidentität"):
        build.signing_identity(None, {"identity": FIRST})


def test_multiple_certificates_require_explicit_selection(monkeypatch):
    monkeypatch.delenv("ITUNESREMOTE_SIGN_IDENTITY", raising=False)
    listing = f'1) {FIRST} "Apple Development: First"\n2) {SECOND} "Apple Development: Second"'
    monkeypatch.setattr(build.subprocess, "check_output", lambda *args, **kwargs: listing)
    with pytest.raises(ValueError, match="--identity"):
        build.signing_identity(None, {})


def test_ad_hoc_signing_requires_explicit_choice(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Explicit ad-hoc test builds do not access the keychain")

    monkeypatch.setattr(build.subprocess, "check_output", unexpected)
    assert build.signing_identity("-", {"identity": FIRST}) == ("-", "ad-hoc")


def test_signing_continuity_checks_both_app_and_service():
    requirements = {"app": 'identifier "app" and anchor apple', "service": 'identifier "service" and anchor apple'}
    configuration = json.loads(json.dumps({"identity": FIRST, "requirements": requirements}))
    build.check_signing_continuity(configuration, FIRST, requirements)
    for component in requirements:
        changed = {**requirements, component: requirements[component] + ' and certificate leaf = H"different"'}
        with pytest.raises(ValueError, match="App-Identität hat sich geändert"):
            build.check_signing_continuity(configuration, FIRST, changed)
    with pytest.raises(ValueError, match="einzelnen Build"):
        build.check_signing_continuity({}, FIRST, {"app": 'cdhash H"1234"'})
