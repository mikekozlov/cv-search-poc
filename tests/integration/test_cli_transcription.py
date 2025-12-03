from __future__ import annotations

from tests.integration.helpers import run_cli, test_env


def test_cli_transcribe_audio_writes_file(tmp_path) -> None:
    env = test_env()

    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"fake audio bytes")
    output_path = tmp_path / "transcript.txt"

    output = run_cli(
        [
            "transcribe-audio",
            "--input",
            str(audio_path),
            "--output",
            str(output_path),
            "--prompt",
            "demo context",
        ],
        env,
    )

    assert output_path.exists(), "Transcript file should be created."
    content = output_path.read_text(encoding="utf-8").strip()
    assert "Stub transcript" in content
    assert audio_path.name in content
    assert str(output_path) in output
