import pytest
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from gateway.run import GatewayRunner
from gateway.session import SessionSource, build_session_key
from gateway.config import Platform, GatewayConfig
from hermes_constants import get_hermes_home

@pytest.fixture
def clean_hermes_home(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    
    # Create profiles directory and files
    profiles_dir = hermes_home / "profiles"
    profiles_dir.mkdir()
    
    for name in ("profileA", "profileB"):
        pdir = profiles_dir / name
        pdir.mkdir()
        (pdir / "SOUL.md").write_text(f"I am {name}", encoding="utf-8")
        (pdir / "memories").mkdir()
        (pdir / "sessions").mkdir()
        (pdir / "config.yaml").write_text("agent:\n  system_prompt: overridden", encoding="utf-8")

    # Set up global SOUL.md
    (hermes_home / "SOUL.md").write_text("I am main agent", encoding="utf-8")
    
    # Write topic profiles config
    import json
    topic_profiles = {
        "telegram:dm:111:222": "profileA",
        "telegram:dm:111:333": "profileB",
    }
    with open(hermes_home / "topic_profiles.json", "w", encoding="utf-8") as f:
        json.dump(topic_profiles, f)

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    with patch("gateway.run._hermes_home", hermes_home):
        yield hermes_home

def test_session_key_routing_unconditional(clean_hermes_home):
    """Verify session key incorporates profile even when multiplex_profiles is False."""
    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(platforms={})
    runner.config.multiplex_profiles = False
    
    # We must mock _normalize_source_for_session_key
    runner._normalize_source_for_session_key = lambda src: src

    source_a = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="111",
        chat_type="dm",
        thread_id="222",
    )
    source_b = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="111",
        chat_type="dm",
        thread_id="333",
    )
    source_main = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="111",
        chat_type="dm",
        thread_id="444",
    )

    key_a = runner._session_key_for_source(source_a)
    key_b = runner._session_key_for_source(source_b)
    key_main = runner._session_key_for_source(source_main)

    assert source_a.profile == "profileA"
    assert source_b.profile == "profileB"
    assert source_main.profile is None

    assert "profileA" in key_a
    assert "profileB" in key_b
    assert "profileA" not in key_main and "profileB" not in key_main

def test_dynamic_session_db_and_store_scoping(clean_hermes_home):
    """Verify that session_store and _session_db are dynamically resolved per-profile."""
    runner = GatewayRunner(config=GatewayConfig(platforms={}))
    runner._normalize_source_for_session_key = lambda src: src
    
    source_a = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="111",
        chat_type="dm",
        thread_id="222",
    )
    
    # Initially global db path
    global_db_path = clean_hermes_home / "state.db"
    assert Path(runner._session_db.db_path).resolve() == global_db_path.resolve()
    
    # Simulate a routed run using _routed_profile_for_source helper
    routed = runner._routed_profile_for_source(source_a)
    assert routed == "profileA"
    
    profile_home = clean_hermes_home / "profiles" / "profileA"
    from gateway.run import _profile_runtime_scope
    with _profile_runtime_scope(profile_home):
        # Inside the scope, get_hermes_home() points to profileA
        assert get_hermes_home().resolve() == profile_home.resolve()
        # session_store and _session_db should resolve to profile-specific DB paths
        profile_db_path = profile_home / "state.db"
        assert Path(runner._session_db.db_path).resolve() == profile_db_path.resolve()
        assert Path(runner.session_store.sessions_dir).resolve() == (profile_home / "sessions").resolve()

    # Outside the scope, back to global
    assert Path(runner._session_db.db_path).resolve() == global_db_path.resolve()

def test_soul_cache_busting(clean_hermes_home):
    """Verify that updating SOUL.md busts the agent cache signature."""
    runner = GatewayRunner(config=GatewayConfig(platforms={}))
    
    # Check signature initially
    sig1 = runner._agent_config_signature(
        model="gpt-4",
        runtime={},
        enabled_toolsets=[],
        ephemeral_prompt="",
    )
    
    # Modify SOUL.md
    soul_file = clean_hermes_home / "SOUL.md"
    soul_file.write_text("updated identity content", encoding="utf-8")
    
    # Force different mtime/stat
    import os
    stat = soul_file.stat()
    os.utime(soul_file, (stat.st_atime, stat.st_mtime + 5.0))
    
    sig2 = runner._agent_config_signature(
        model="gpt-4",
        runtime={},
        enabled_toolsets=[],
        ephemeral_prompt="",
    )
    
    assert sig1 != sig2
