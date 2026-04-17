"""Credentials and profile management for Citeck ECOS plugin.

Stores credentials in ~/.citeck/credentials.json with restricted permissions (chmod 600).
Supports multiple profiles for different environments (local, staging, production).
"""
import json
import os
import stat

DEFAULT_CONFIG_DIR = os.path.expanduser("~/.citeck")
CREDENTIALS_FILE = "credentials.json"


def _config_path(config_dir=None):
    d = config_dir or DEFAULT_CONFIG_DIR
    return os.path.join(d, CREDENTIALS_FILE)


def _read_config(config_dir=None):
    path = _config_path(config_dir)
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {"active_profile": "default", "profiles": {}}
    except (json.JSONDecodeError, PermissionError, OSError) as e:
        raise ConfigError(f"Failed to read {path}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"Invalid config format in {path}: expected JSON object")
    data.setdefault("active_profile", "default")
    data.setdefault("profiles", {})
    if not isinstance(data["profiles"], dict):
        raise ConfigError(f"Invalid config format in {path}: 'profiles' must be an object")
    return data


def _write_config(data, config_dir=None):
    d = config_dir or DEFAULT_CONFIG_DIR
    path = _config_path(config_dir)
    os.makedirs(d, exist_ok=True)
    os.chmod(d, stat.S_IRWXU)  # 700
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)


class ConfigError(Exception):
    """Raised when config file is invalid or inaccessible."""


def _validate_profile_name(name):
    """Reject profile names that could cause path traversal."""
    if not name or "/" in name or "\\" in name or ".." in name:
        raise ConfigError(f"Invalid profile name: '{name}'")


def get_credentials(profile=None, config_dir=None):
    """Return credentials dict for the given profile (or active profile).

    Returns None if the profile does not exist.
    """
    data = _read_config(config_dir)
    name = profile or data.get("active_profile", "default")
    return data["profiles"].get(name)


def save_credentials(profile, url, username=None, password=None,
                     client_id=None, client_secret=None,
                     auth_method="oidc", realm=None, eis_id=None,
                     token_endpoint=None, authorization_endpoint=None,
                     config_dir=None):
    """Save credentials for a profile. Creates config file if needed."""
    _validate_profile_name(profile)
    data = _read_config(config_dir)
    entry = {
        "url": url,
        "auth_method": auth_method,
    }
    if username is not None:
        entry["username"] = username
    if password is not None:
        entry["password"] = password
    if client_id is not None:
        entry["client_id"] = client_id
    if client_secret is not None:
        entry["client_secret"] = client_secret
    if realm is not None:
        entry["realm"] = realm
    if eis_id is not None:
        entry["eis_id"] = eis_id
    if token_endpoint is not None:
        entry["token_endpoint"] = token_endpoint
    if authorization_endpoint is not None:
        entry["authorization_endpoint"] = authorization_endpoint
    data["profiles"][profile] = entry
    # If this is the first profile, make it active
    if len(data["profiles"]) == 1:
        data["active_profile"] = profile
    _write_config(data, config_dir)


def get_profiles(config_dir=None):
    """Return list of profile names."""
    data = _read_config(config_dir)
    return list(data["profiles"].keys())


def get_active_profile(config_dir=None):
    """Return the name of the active profile."""
    data = _read_config(config_dir)
    return data.get("active_profile", "default")


def set_active_profile(name, config_dir=None):
    """Set the active profile. Raises ConfigError if profile doesn't exist."""
    _validate_profile_name(name)
    data = _read_config(config_dir)
    if name not in data["profiles"]:
        raise ConfigError(f"Profile '{name}' does not exist. Available: {list(data['profiles'].keys())}")
    data["active_profile"] = name
    _write_config(data, config_dir)


def get_docs_profile(config_dir=None):
    """Return the profile name used for citeck-docs RAG search, or None if unset.

    Separate from active_profile because users often work against a local Citeck
    while documentation is indexed on a different (e.g. production) server.
    """
    data = _read_config(config_dir)
    value = data.get("docs_profile")
    return value if isinstance(value, str) and value else None


def set_docs_profile(name, config_dir=None):
    """Set the profile to use for citeck-docs RAG search.

    Raises ConfigError if profile doesn't exist.
    """
    _validate_profile_name(name)
    data = _read_config(config_dir)
    if name not in data["profiles"]:
        raise ConfigError(f"Profile '{name}' does not exist. Available: {list(data['profiles'].keys())}")
    data["docs_profile"] = name
    _write_config(data, config_dir)


def clear_docs_profile(config_dir=None):
    """Remove the docs_profile setting so search_docs falls back to the active profile."""
    data = _read_config(config_dir)
    if "docs_profile" in data:
        del data["docs_profile"]
        _write_config(data, config_dir)


def _get_profile_data(profile=None, config_dir=None):
    """Return (data, profile_name, profile_dict) for the given or active profile."""
    data = _read_config(config_dir)
    name = profile or data.get("active_profile", "default")
    prof = data["profiles"].get(name)
    if prof is None:
        raise ConfigError(f"Profile '{name}' does not exist.")
    return data, name, prof


def get_projects(profile=None, config_dir=None):
    """Return list of saved project keys for the profile."""
    _, _, prof = _get_profile_data(profile, config_dir)
    return prof.get("projects", [])


def get_default_project(profile=None, config_dir=None):
    """Return default project key for the profile, or None."""
    _, _, prof = _get_profile_data(profile, config_dir)
    return prof.get("default_project")


def set_default_project(project_key, profile=None, config_dir=None):
    """Set default project and auto-add to projects list if missing."""
    data, name, prof = _get_profile_data(profile, config_dir)
    projects = prof.setdefault("projects", [])
    if project_key not in projects:
        projects.append(project_key)
    prof["default_project"] = project_key
    _write_config(data, config_dir)


def add_project(project_key, profile=None, config_dir=None):
    """Add a project key to the saved projects list."""
    data, name, prof = _get_profile_data(profile, config_dir)
    projects = prof.setdefault("projects", [])
    if project_key not in projects:
        projects.append(project_key)
        _write_config(data, config_dir)


def remove_project(project_key, profile=None, config_dir=None):
    """Remove a project key from the saved projects list."""
    data, name, prof = _get_profile_data(profile, config_dir)
    projects = prof.get("projects", [])
    if project_key in projects:
        projects.remove(project_key)
        if prof.get("default_project") == project_key:
            prof["default_project"] = projects[0] if projects else None
        _write_config(data, config_dir)
