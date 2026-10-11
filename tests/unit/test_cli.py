from rf_harness import __version__
from rf_harness.installer.cli import main


def test_version_command(capsys):
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out
