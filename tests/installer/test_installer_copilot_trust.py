"""Copilot CLI runs repository hooks (.github/hooks) only in trusted folders: the trust reader and doctor check."""

import json

from rf_harness.installer import homes


def test_trusted_folder_and_parent(tmp_path, monkeypatch):
    home = tmp_path / "copilot"
    home.mkdir()
    project = tmp_path / "work" / "proj"
    project.mkdir(parents=True)
    monkeypatch.setenv("COPILOT_HOME", str(home))
    assert homes.copilot_folder_trusted(project) is None              # no config yet
    (home / "config.json").write_text(json.dumps({"trusted_folders": [str(tmp_path / "work")]}))
    assert homes.copilot_folder_trusted(project) is True              # a parent folder is trusted
    (home / "config.json").write_text(json.dumps({"trusted_folders": [str(tmp_path / "other")]}))
    assert homes.copilot_folder_trusted(project) is False


def test_config_with_comments_is_read(tmp_path, monkeypatch):
    home = tmp_path / "copilot"
    home.mkdir()
    monkeypatch.setenv("COPILOT_HOME", str(home))
    folder = json.dumps(str(tmp_path))
    (home / "config.json").write_text('// user settings\n{\n  "model": "auto",\n  "trusted_folders": [' + folder
                                      + ']\n}\n')
    assert homes.copilot_folder_trusted(tmp_path) is True
