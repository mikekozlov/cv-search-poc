from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict

import click

from cv_search.cli.context import CLIContext
from cv_search.ingestion.gdrive_sync import GDriveSyncer
from cv_search.ingestion.pipeline import CVIngestionPipeline


def _print_gdrive_report(report: Dict[str, Any]) -> None:
    """Helper to print the ingestion report to the console."""
    if report.get("status") == "no_files_found":
        return  # Message already printed by pipeline

    processed_count = report.get("processed_count", 0)
    skipped_roles = report.get("skipped_roles", {})
    skipped_ambiguous = report.get("skipped_ambiguous", [])
    failed_files = report.get("failed_files", [])
    unmapped_tags = report.get("unmapped_tags", [])
    json_output_dir = report.get("json_output_dir", "data/ingested_cvs_json")
    skipped_unchanged = report.get("skipped_unchanged", [])

    if skipped_roles:
        click.secho("\n--- Data Quality Gate: Skipped CVs ---", fg="yellow")
        click.secho(
            "The following CVs were skipped because their role folder could not be mapped to a known role in 'role_lexicon.json'.",
            fg="yellow",
        )
        for role_key, files in skipped_roles.items():
            click.echo(f"  - Unmapped Role Folder: '{role_key}' (Skipped {len(files)} CV(s))")
        click.secho("The LLM determined these are not valid role folders.", fg="yellow")

    if skipped_ambiguous:
        click.secho("\n--- Skipped Ambiguous CVs ---", fg="yellow")
        click.secho(
            "The following CVs were skipped because they were not in a role folder:", fg="yellow"
        )
        for file_path in skipped_ambiguous:
            click.echo(f"  - {file_path}")

    if skipped_unchanged:
        click.secho("\n--- Skipped Unchanged CVs ---", fg="yellow")
        for rel_path in skipped_unchanged:
            click.echo(f"  - {rel_path}")

    if failed_files:
        click.secho(f"\n{len(failed_files)} file(s) failed to parse. See errors above.", fg="red")

    if unmapped_tags:
        click.secho("\n--- Lexicon Review ---", fg="yellow")
        click.secho("The following tags were found but are not in your lexicons:", fg="yellow")
        click.echo(", ".join(unmapped_tags))

    click.echo(f"\nDebug JSON files saved in: {json_output_dir}")
    click.secho(f"\n? GDrive Ingestion Complete: {processed_count} CV(s) upserted.", fg="green")


def _print_json_report(report: Dict[str, Any]) -> None:
    status = report.get("status")
    processed_count = report.get("processed_count", 0)
    failed_files = report.get("failed_files", [])
    json_dir = report.get("json_dir", "data/ingested_cvs_json")

    if status == "no_json_dir":
        click.secho(f"\n? JSON directory not found: {json_dir}", fg="red")
        return

    if status in {"no_files", "no_valid_payloads"}:
        click.secho(f"\n? No JSON CVs to ingest from {json_dir}.", fg="yellow")

    if failed_files:
        click.secho("\n--- JSON Parse Failures ---", fg="red")
        for file_path in failed_files:
            click.echo(f"  - {file_path}")

    click.echo(f"\nJSON source: {json_dir}")
    click.secho(f"\n? JSON Ingestion Complete: {processed_count} CV(s) upserted.", fg="green")


def register(cli: click.Group) -> None:
    @cli.command("sync-gdrive")
    @click.pass_obj
    def sync_gdrive_cmd(ctx: CLIContext) -> None:
        """
        Syncs files from a Google Drive folder to a local directory using rclone.

        This command requires rclone to be installed. You must first run
        'rclone config' to set up a Google Drive remote.

        Configure settings in your .env file:
        - GDRIVE_RCLONE_CONFIG_PATH (optional)
        - GDRIVE_REMOTE_NAME
        - GDRIVE_SOURCE_DIR
        - GDRIVE_LOCAL_DEST_DIR
        """
        settings = ctx.settings
        db = ctx.db  # Get db to ensure we close it

        try:
            syncer = GDriveSyncer(settings)

            click.secho(
                f"Starting sync from GDrive remote '{settings.gdrive_remote_name}'...",
                fg="cyan",
            )

            syncer.sync_files()

            click.secho(
                "\n? Google Drive sync completed successfully.",
                fg="green",
            )
            click.echo(f"Files are available in: {settings.gdrive_local_dest_dir}")

        except FileNotFoundError as exc:
            click.secho(f"\n? Error: {exc}", fg="red")
            click.secho(
                "Please ensure 'rclone' is installed and in your system's PATH.",
                fg="red",
            )
            if settings.gdrive_rclone_config_path:
                click.secho(
                    f"Also check that your config file exists at: "
                    f"{settings.gdrive_rclone_config_path}",
                    fg="red",
                )
            click.get_current_context().exit(1)

        except subprocess.CalledProcessError as exc:
            click.secho(
                f"\n? rclone command failed with return code {exc.returncode}.",
                fg="red",
            )
            click.secho(
                "Check the rclone output above for error details.",
                fg="red",
            )
            click.get_current_context().exit(1)

        except Exception as exc:  # noqa: BLE001
            click.secho(f"\n? An unexpected error occurred: {exc}", fg="red")
            click.get_current_context().exit(1)

        finally:
            db.close()

    @cli.command("ingest-gdrive")
    @click.option(
        "--file",
        "single_file",
        type=str,
        required=False,
        help="Process only this file name (basename with extension) from the GDrive inbox.",
    )
    @click.pass_obj
    def ingest_gdrive_cmd(ctx: CLIContext, single_file: str | None) -> None:
        """
        Parses .pptx CVs from the GDrive inbox, saves to JSON for debug,
        and ingests them into the database and FAISS index.
        If --file is provided, only that file name (basename + extension) will be processed.
        """
        settings = ctx.settings
        client = ctx.client
        db = ctx.db

        try:
            pipeline = CVIngestionPipeline(db, settings)
            report = pipeline.run_gdrive_ingestion(client, target_filename=single_file)
            _print_gdrive_report(report)

        except Exception as exc:  # noqa: BLE001
            click.secho(f"? FAILED during database ingestion: {exc}", fg="red")
        finally:
            db.close()

    @cli.command("ingest-json")
    @click.option(
        "--json-dir",
        "json_dir",
        type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
        required=False,
        help="Directory containing parsed CV JSON files (default: data/ingested_cvs_json).",
    )
    @click.option(
        "--file",
        "single_file",
        type=str,
        required=False,
        help="Process only this JSON filename (basename with extension).",
    )
    @click.option(
        "--candidate-id",
        "candidate_id",
        type=str,
        required=False,
        help="Process only this candidate_id (defaults to filename stem).",
    )
    @click.pass_obj
    def ingest_json_cmd(
        ctx: CLIContext,
        json_dir: Path | None,
        single_file: str | None,
        candidate_id: str | None,
    ) -> None:
        """
        Ingest parsed CV JSON files into the database without re-parsing PPTX files.

        This command expects JSON payloads like those written to data/ingested_cvs_json
        by ingest-gdrive or the async ingestion pipeline.
        """
        settings = ctx.settings
        db = ctx.db

        try:
            pipeline = CVIngestionPipeline(db, settings)
            report = pipeline.run_json_ingestion(
                json_dir=json_dir,
                target_filename=single_file,
                candidate_id=candidate_id,
            )
            _print_json_report(report)

        except Exception as exc:  # noqa: BLE001
            click.secho(f"? FAILED during JSON ingestion: {exc}", fg="red")
        finally:
            db.close()
