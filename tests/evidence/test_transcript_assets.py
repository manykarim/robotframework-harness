"""evidence/pack_transcripts.py + evidence/verify_assets.py on a synthetic round (gzip format, no zstd needed)."""

from __future__ import annotations

import gzip
import io
import json
import tarfile
from pathlib import Path

import pytest

FAKE_OPENROUTER = "sk-or-v1-" + "fedcba9876543210" * 4


def _round(tmp_path: Path, transcript_text: str) -> tuple[Path, Path]:
    root = tmp_path / "evidence"
    rdir = root / "rounds" / "99-test"
    (rdir / "results").mkdir(parents=True)
    (rdir / "config.json").write_text(json.dumps({"transcript_dirs": ["transcripts_t"]}), encoding="utf-8")
    rows = [{"key": "claude|hookpkg|s|1", "status": "ok", "transcript": "transcripts_t/claude/s-1.jsonl.gz"},
            {"key": "codex|mcp|s|1", "status": "ok", "transcript": "transcripts_t/codex/s-1.jsonl.gz"}]
    (rdir / "results" / "results_t.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    tx = tmp_path / "tx"
    for agent in ("claude", "codex"):
        p = tx / "transcripts_t" / agent / "s-1.jsonl.gz"
        p.parent.mkdir(parents=True)
        p.write_bytes(gzip.compress(transcript_text.encode()))
    return root, tx


def _pack(pack_transcripts, scrub, root: Path, tx: Path, tmp_path: Path) -> dict | None:
    meta = json.loads((root / "rounds" / "99-test" / "config.json").read_text(encoding="utf-8"))
    return pack_transcripts.build_round("99-test", meta, tx, root, scrub.build_rules(), "gz", tmp_path / "assets",
                                        manifests=root / "transcripts")


def _write_index(root: Path, res: dict) -> None:
    (root / "transcripts" / "assets.json").write_text(json.dumps({"assets": [res]}), encoding="utf-8")


def test_pack_scrubs_and_verifies(pack_transcripts, verify_assets, scrub, no_env_secrets, tmp_path: Path) -> None:
    root, tx = _round(tmp_path, '{"cwd": "/home/alice/w", "msg": "ok"}\n')
    res = _pack(pack_transcripts, scrub, root, tx, tmp_path)
    assert res is not None and res["files"] == 2
    _write_index(root, res)
    manifest = json.loads((root / "transcripts" / "99-test.manifest.json").read_text(encoding="utf-8"))
    assert {e["key"] for e in manifest["entries"]} == {"claude|hookpkg|s|1", "codex|mcp|s|1"}
    assert manifest["scrub_substitutions"] == {"home_path": 2}
    status, problems = verify_assets.verify_round(res, tmp_path / "assets", root)
    assert problems == [] and status.startswith("2 transcripts verified, 2 mapped")
    with tarfile.open(tmp_path / "assets" / res["asset"]) as tar:
        member = tar.extractfile("99-test/transcripts_t/claude/s-1.jsonl")
        assert member is not None and b"/home/alice" not in member.read()


def test_tampered_asset_fails_verification(pack_transcripts, verify_assets, scrub, no_env_secrets,
                                           tmp_path: Path) -> None:
    root, tx = _round(tmp_path, '{"msg": "ok"}\n')
    res = _pack(pack_transcripts, scrub, root, tx, tmp_path)
    assert res is not None
    asset = tmp_path / "assets" / res["asset"]
    # rebuild the tar with one transcript changed, and record the new asset checksum so only the member check fails
    out = io.BytesIO()
    with tarfile.open(asset) as src, tarfile.open(fileobj=out, mode="w") as dst:
        for m in src.getmembers():
            data = src.extractfile(m).read()  # type: ignore[union-attr]
            if m.name.endswith("codex/s-1.jsonl"):
                data = b'{"msg": "edited"}\n'
                m.size = len(data)
            dst.addfile(m, io.BytesIO(data))
    asset.write_bytes(gzip.compress(out.getvalue(), mtime=0))
    res = {**res, "bytes": asset.stat().st_size, "sha256": verify_assets.file_sha256(asset)}
    _, problems = verify_assets.verify_round(res, tmp_path / "assets", root)
    assert problems == ["99-test: checksum mismatch 99-test/transcripts_t/codex/s-1.jsonl"]


def test_secret_in_transcript_blocks_the_asset(pack_transcripts, scrub, tmp_path: Path, monkeypatch,
                                               capsys) -> None:
    # The planted key is also the literal value of a "secret" env var: the scrub redacts it, so the asset builds
    # and the key is gone. A binary transcript with a key cannot be redacted and blocks the asset.
    monkeypatch.setenv("RFH_SCRUB_ENV", "RFH_TEST_FAKE_SECRET")
    monkeypatch.setenv("RFH_TEST_FAKE_SECRET", FAKE_OPENROUTER)
    monkeypatch.setenv("RFH_SCRUB_DOTENV", str(tmp_path / "absent.env"))
    root, tx = _round(tmp_path, f'{{"env": "{FAKE_OPENROUTER}"}}\n')
    assert _pack(pack_transcripts, scrub, root, tx, tmp_path) is not None
    binary = tx / "transcripts_t" / "codex" / "s-1.jsonl.gz"
    binary.write_bytes(gzip.compress(b"\x00\x01" + FAKE_OPENROUTER.encode()))
    assert _pack(pack_transcripts, scrub, root, tx, tmp_path) is None
    assert "asset NOT built" in capsys.readouterr().out


@pytest.mark.skipif(not (Path(__file__).resolve().parents[2] / "evidence" / "transcripts" / "assets.json").is_file(),
                    reason="no transcript manifests")
def test_committed_manifests_map_every_transcript(verify_assets) -> None:
    evidence = Path(__file__).resolve().parents[2] / "evidence"
    index = json.loads((evidence / "transcripts" / "assets.json").read_text(encoding="utf-8"))
    for entry in index["assets"]:
        manifest = json.loads((evidence / entry["manifest"]).read_text(encoding="utf-8"))
        problems, unreferenced = verify_assets.check_mapping(evidence / "rounds" / entry["round"],
                                                             manifest["entries"])
        assert problems == [] and unreferenced <= 1, (entry["round"], problems[:5])
