"""evidence/scrub.py: planted secrets fail --check, clean trees pass, --apply redacts and normalizes."""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).resolve().parents[2] / "evidence"

# Fake credentials are assembled at runtime so that no key-shaped literal sits in the repository.
FAKE_OPENROUTER = "sk-or-v1-" + "0123456789abcdef" * 4
FAKE_ANTHROPIC = "sk-ant-" + "api03-" + "Ab1" * 12
FAKE_GITHUB = "gh" + "p_" + "A1b2C3d4E5" * 4
FAKE_AWS = "AK" + "IA" + "ABCDEFGHIJ123456"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_planted_openrouter_key_fails_check(scrub, no_env_secrets, tmp_path: Path, capsys) -> None:
    _write(tmp_path / "ok.md", "nothing to see\n")
    _write(tmp_path / "run" / "transcript.jsonl", '{"a": 1}\n{"env": "OPENROUTER_API_KEY=' + FAKE_OPENROUTER + '"}\n')
    rc = scrub.main(["--check", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "run/transcript.jsonl:2: openrouter_key" in out
    assert FAKE_OPENROUTER not in out


def test_key_inside_gzip_transcript_is_found(scrub, no_env_secrets, tmp_path: Path) -> None:
    gz = tmp_path / "t.jsonl.gz"
    gz.write_bytes(gzip.compress(("line\n" * 3 + "token " + FAKE_OPENROUTER + "\n").encode()))
    report = scrub.check_tree(tmp_path)
    assert report.rule_counts["openrouter_key"] == 1
    assert report.locations == [{"file": "t.jsonl.gz", "line": 4, "rule": "openrouter_key"}]


@pytest.mark.parametrize("secret,rule", [(FAKE_ANTHROPIC, "anthropic_key"), (FAKE_GITHUB, "github_token"),
                                         (FAKE_AWS, "aws_access_key")])
def test_provider_patterns(scrub, no_env_secrets, tmp_path: Path, secret: str, rule: str) -> None:
    _write(tmp_path / "f.txt", f"value: {secret}\n")
    assert scrub.check_tree(tmp_path).rule_counts[rule] == 1


def test_clean_tree_passes_with_empty_report(scrub, no_env_secrets, tmp_path: Path) -> None:
    _write(tmp_path / "a.md", "# Findings\nPass rate 0.83 vs 0.69, see ~/workspace/x and many.kasiriha@gmail.com\n")
    _write(tmp_path / "b.json", json.dumps({"path": "~/.cache/ab-eval/work", "user": "erika@example.com"}))
    report_file = tmp_path.parent / "report.json"
    assert scrub.main(["--check", str(tmp_path), "--report", str(report_file)]) == 0
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["findings"] == 0 and report["rule_counts"] == {} and report["files"] == {}


def test_apply_normalizes_home_paths(scrub, no_env_secrets, tmp_path: Path) -> None:
    src = _write(tmp_path / "src" / "row.jsonl",
                 '{"cwd": "/home/alice/work/x", "w": "C:\\\\Users\\\\bob\\\\proj", "mac": "/Users/carol/a",'
                 ' "slug": "/tmp/claude-1000/-home-alice-workspace-rf/notes"}\n')
    dst = tmp_path / "dst"
    report = scrub.apply_tree(src.parent, dst)
    out = (dst / "row.jsonl").read_text(encoding="utf-8")
    assert json.loads(out) == {"cwd": "~/work/x", "w": "~\\proj", "mac": "~/a",
                               "slug": "/tmp/claude-1000/-home-~-workspace-rf/notes"}
    assert report.rule_counts["home_path"] == 3 and report.rule_counts["home_slug"] == 1
    assert scrub.check_tree(dst).findings == 0


def test_allowlisted_emails_are_kept(scrub, no_env_secrets, tmp_path: Path) -> None:
    text = ("author many.kasiriha@gmail.com, noreply manykarim@users.noreply.github.com, fixture erika@example.com,"
            " demo jamie@flowlinesupply.com, placeholder max@beispiel.de, private john.doe@corp-mail.net,"
            " asset logo@2x.png, decorator fn@wrapt.decorator\n")
    _write(tmp_path / "src" / "notes.md", text)
    scrub.apply_tree(tmp_path / "src", tmp_path / "dst")
    out = (tmp_path / "dst" / "notes.md").read_text(encoding="utf-8")
    for kept in ("many.kasiriha@gmail.com", "manykarim@users.noreply.github.com", "erika@example.com",
                 "jamie@flowlinesupply.com", "max@beispiel.de", "logo@2x.png", "fn@wrapt.decorator"):
        assert kept in out
    assert "john.doe@corp-mail.net" not in out and "[REDACTED:email]" in out


def test_oauth_fields_and_env_values_are_redacted(scrub, tmp_path: Path, monkeypatch, capsys) -> None:
    secret = "lit3ral-s3cret-value-" + "x" * 12
    monkeypatch.setenv("RFH_SCRUB_ENV", "RFH_TEST_FAKE_SECRET")
    monkeypatch.setenv("RFH_TEST_FAKE_SECRET", secret)
    monkeypatch.setenv("RFH_SCRUB_DOTENV", str(tmp_path / "absent.env"))
    escaped = '{"content": "{\\n  \\"access_token\\": \\"' + "t0k3n" * 8 + '\\"\\n}"}'
    _write(tmp_path / "src" / "a.jsonl", escaped + "\n" + json.dumps({"refresh_token": "r" * 40}) + "\n"
           + f"echo {secret}\n")
    report = scrub.apply_tree(tmp_path / "src", tmp_path / "dst")
    out = (tmp_path / "dst" / "a.jsonl").read_text(encoding="utf-8")
    assert "t0k3n" not in out and "r" * 40 not in out and secret not in out
    assert "[REDACTED:env:RFH_TEST_FAKE_SECRET]" in out
    assert report.rule_counts["oauth_field"] == 2 and report.rule_counts["env_secret:RFH_TEST_FAKE_SECRET"] == 1
    json.loads(out.splitlines()[0])  # still valid JSON after redaction
    scrub.print_report(report)
    assert secret not in capsys.readouterr().out


def test_dotenv_values_are_used(scrub, tmp_path: Path, monkeypatch) -> None:
    dotenv = _write(tmp_path / ".env", 'export OPENROUTER_API_KEY="dotenv-value-123456"\nOTHER_TOKEN=abcdefgh1234\n')
    monkeypatch.setenv("RFH_SCRUB_DOTENV", str(dotenv))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("RFH_SCRUB_ENV", raising=False)
    values = scrub.secret_env_values()
    assert values["OPENROUTER_API_KEY"] == "dotenv-value-123456"
    assert values["OTHER_TOKEN"] == "abcdefgh1234"


def test_auth_files_and_agent_homes_are_skipped(scrub, no_env_secrets, tmp_path: Path) -> None:
    _write(tmp_path / "src" / "cell" / "agent_home" / "settings.json", "{}")
    _write(tmp_path / "src" / "codex" / "auth.json", '{"x": 1}')
    _write(tmp_path / "src" / "keep.txt", "fine\n")
    check = scrub.check_tree(tmp_path / "src")
    assert {s["rule"] for s in check.files_skipped} == {"agent_home", "auth_file"}
    report = scrub.apply_tree(tmp_path / "src", tmp_path / "dst")
    assert len(report.files_skipped) == 2
    assert sorted(p.name for p in (tmp_path / "dst").rglob("*") if p.is_file()) == ["keep.txt"]


def test_gzip_roundtrip(scrub, no_env_secrets, tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    clean = gzip.compress(b'{"ok": true}\n', mtime=0)
    (src / "clean.jsonl.gz").write_bytes(clean)
    (src / "dirty.jsonl.gz").write_bytes(gzip.compress(b'{"cwd": "/home/alice/x"}\n'))
    scrub.apply_tree(src, tmp_path / "dst")
    assert (tmp_path / "dst" / "clean.jsonl.gz").read_bytes() == clean  # untouched files stay byte-identical
    assert gzip.decompress((tmp_path / "dst" / "dirty.jsonl.gz").read_bytes()) == b'{"cwd": "~/x"}\n'


def test_binary_with_secret_is_not_copied(scrub, no_env_secrets, tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "img.bin").write_bytes(b"\x89PNG\x00\x00" + FAKE_OPENROUTER.encode() + b"\x00")
    (src / "ok.bin").write_bytes(b"\x89PNG\x00\x00plain\x00")
    report = scrub.apply_tree(src, tmp_path / "dst")
    assert [s["rule"] for s in report.files_skipped] == ["binary_with_secret"]
    assert not (tmp_path / "dst" / "img.bin").exists() and (tmp_path / "dst" / "ok.bin").exists()


def test_cli_exit_codes(no_env_secrets, tmp_path: Path) -> None:
    _write(tmp_path / "dirty" / "x.txt", FAKE_OPENROUTER)
    _write(tmp_path / "clean" / "x.txt", "ok")
    script = str(EVIDENCE / "scrub.py")
    dirty = subprocess.run([sys.executable, script, "--check", str(tmp_path / "dirty")], capture_output=True, text=True)
    clean = subprocess.run([sys.executable, script, "--check", str(tmp_path / "clean")], capture_output=True, text=True)
    assert dirty.returncode == 1 and FAKE_OPENROUTER not in dirty.stdout + dirty.stderr
    assert clean.returncode == 0, clean.stdout + clean.stderr


def test_archive_is_clean(scrub, no_env_secrets) -> None:
    """The committed archive passes the same check CI runs (release-asset build dirs are not committed)."""
    if not (EVIDENCE / "rounds").is_dir():
        pytest.skip("evidence archive not imported")
    report = scrub.check_tree(EVIDENCE, exclude=["_release_assets"])
    assert report.findings == 0, report.to_json()["locations"][:20]
