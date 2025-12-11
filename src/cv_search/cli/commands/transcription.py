from __future__ import annotations

from pathlib import Path

import click

from cv_search.cli.context import CLIContext


def _resolve_output_path(audio_path: Path, output_path: Path | None) -> Path:
    if output_path:
        return output_path
    return audio_path.with_suffix(".txt")


def register(cli: click.Group) -> None:
    @cli.command("transcribe-audio")
    @click.option(
        "--input",
        "input_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        required=True,
        help="Path to an audio file supported by Whisper (e.g., .mp3, .wav, .m4a).",
    )
    @click.option(
        "--output",
        "output_path",
        type=click.Path(dir_okay=False, resolve_path=True, path_type=Path),
        required=False,
        help="Where to save the transcript (default: alongside the input with .txt).",
    )
    @click.option(
        "--prompt",
        type=str,
        required=False,
        help="The transcript is in Russian language. Provide structured text, only important notes.",
    )
    @click.pass_obj
    def transcribe_audio_cmd(
        ctx: CLIContext, input_path: Path, output_path: Path | None, prompt: str | None
    ) -> None:
        """
        Transcribe an audio file with Whisper and write the transcript to disk.
        """
        target_path = _resolve_output_path(input_path, output_path).resolve()
        try:
            transcript = ctx.client.transcribe_audio(
                input_path.resolve(),
                model=ctx.settings.openai_audio_model,
                prompt=prompt,
            )
        except Exception as exc:  # noqa: BLE001
            raise click.ClickException(f"Transcription failed: {exc}") from exc

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(transcript, encoding="utf-8")
        click.echo(f"Transcript saved to: {target_path}")
