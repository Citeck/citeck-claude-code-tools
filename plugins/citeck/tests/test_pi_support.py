"""Pi package contracts and token-only reauthentication; no real credentials."""
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
sys.path.insert(0, str(PLUGIN))


def load_setup():
    path = PLUGIN / "skills/citeck-auth/scripts/setup_pkce.py"
    spec = importlib.util.spec_from_file_location("pi_setup_pkce", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pi_package_resources():
    package = json.loads((PLUGIN / "package.json").read_text())
    bridge = json.loads((REPO / "package.json").read_text())
    assert "pi-package" in package["keywords"]
    assert set(bridge) == {"private", "pi"}
    assert bridge["private"] is True
    for resource_type in ("extensions", "skills"):
        nested_paths = [(PLUGIN / value).resolve() for value in package["pi"][resource_type]]
        bridge_paths = [(REPO / value).resolve() for value in bridge["pi"][resource_type]]
        assert nested_paths == bridge_paths
        assert all(path.exists() for path in nested_paths)
    assert len(package["pi"]["extensions"]) == 1
    assert len(list((PLUGIN / package["pi"]["skills"][0]).glob("*/SKILL.md"))) == 5
    assert "@earendil-works/pi-coding-agent" not in package.get("dependencies", {})


def test_terminal_reauth_preserves_profile(tmp_path, monkeypatch, capsys):
    module = load_setup()
    directory = str(tmp_path / "isolated")
    monkeypatch.setenv("CITECK_CONFIG_DIR", directory)
    module.config.save_credentials(
        "fixture", "https://fixture.invalid", auth_method="oidc-pkce",
        client_id="fixture-client", token_endpoint="https://id.invalid/token",
        authorization_endpoint="https://id.invalid/auth", config_dir=directory,
    )
    path = Path(directory) / "credentials.json"
    original = path.read_bytes()
    monkeypatch.setattr(sys, "argv", ["setup_pkce.py", "--profile", "fixture", "--reauth"])
    tokens = {"access_token": "synthetic-secret", "refresh_token": "synthetic-refresh"}
    with patch.object(module.pkce, "authorize", return_value=tokens) as authorize, \
            patch.object(module.auth, "_save_cache") as save:
        module.main()
    assert path.read_bytes() == original
    save.assert_called_once_with(tokens, "fixture", directory)
    assert authorize.call_args.args == (
        "https://id.invalid/token", "https://id.invalid/auth", "fixture-client")
    output = capsys.readouterr()
    assert "synthetic-secret" not in output.out + output.err
    assert json.loads(output.out)["status"] == "ok"


def test_reauth_rejects_profile_reconfiguration(monkeypatch):
    module = load_setup()
    monkeypatch.setattr(sys, "argv", ["setup_pkce.py", "--reauth", "--url", "https://other.invalid"])
    with pytest.raises(SystemExit):
        module.main()
