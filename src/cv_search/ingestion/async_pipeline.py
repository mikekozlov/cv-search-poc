import json
from pathlib import Path
from datetime import datetime
import click

from cv_search.config.settings import Settings
from cv_search.ingestion.redis_client import RedisClient
from cv_search.ingestion.events import TextExtractedEvent
from cv_search.ingestion.file_watch_service import FileWatchService
from cv_search.ingestion.source_identity import candidate_id_from_source_gdrive_path
from cv_search.clients.openai_client import OpenAIClient
from cv_search.db.database import CVDatabase
from cv_search.ingestion.cv_parser import CVParser
from cv_search.retrieval.embedder_stub import EmbedderProtocol
from cv_search.retrieval.local_embedder import LocalEmbedder

# Constants for Redis Channels/Queues
CHANNEL_FILE_DETECTED = "ingest:file_detected"
QUEUE_EXTRACT_TASK = "ingest:queue:extract"
QUEUE_ENRICH_TASK = "ingest:queue:enrich"
QUEUE_DLQ = "ingest:queue:dlq"


class Watcher:
    def __init__(self, settings: Settings, redis_client: RedisClient):
        self.settings = settings
        self.redis = redis_client
        self.inbox_dir = self.settings.gdrive_local_dest_dir
        self.db = CVDatabase(settings)
        self._service: FileWatchService | None = None

    def close(self):
        if self._service:
            try:
                self._service.stop()
            except Exception:
                pass
            self._service = None
        if self.db:
            self.db.close()
            self.db = None

    def run(self):
        click.echo(f"Watcher started. Monitoring {self.inbox_dir}...")
        try:
            self._service = FileWatchService(
                inbox_dir=self.inbox_dir,
                redis=self.redis,
                db=self.db,
                queue_name=QUEUE_EXTRACT_TASK,
                debounce_ms=self.settings.ingest_watch_debounce_ms,
                stable_ms=self.settings.ingest_watch_stable_ms,
                dedupe_ttl_s=self.settings.ingest_watch_dedupe_ttl_s,
                reconcile=True,
                reconcile_interval_s=self.settings.ingest_watch_reconcile_interval_s or None,
            )
            self._service.run_forever()
        except KeyboardInterrupt:
            click.echo("Watcher stopping...")
        finally:
            self.close()

    def _scan_and_publish(self):
        svc = FileWatchService(
            inbox_dir=self.inbox_dir,
            redis=self.redis,
            db=self.db,
            queue_name=QUEUE_EXTRACT_TASK,
            debounce_ms=self.settings.ingest_watch_debounce_ms,
            stable_ms=self.settings.ingest_watch_stable_ms,
            dedupe_ttl_s=self.settings.ingest_watch_dedupe_ttl_s,
            reconcile=False,
            reconcile_interval_s=None,
        )
        svc.reconcile_once()


class ExtractorWorker:
    def __init__(
        self, settings: Settings, redis_client: RedisClient, parser: CVParser | None = None
    ):
        self.settings = settings
        self.redis = redis_client
        self.parser = parser or CVParser()

    def run(self):
        click.echo("Extractor Worker started. Waiting for tasks...")
        while True:
            try:
                # Blocking pop
                task_data = self.redis.pop_from_queue(QUEUE_EXTRACT_TASK, timeout=5)
                if not task_data:
                    continue

                source = (
                    task_data.get("source_gdrive_path")
                    or task_data.get("source_rel_path")
                    or task_data.get("file_path")
                    or "<unknown>"
                )
                click.echo(f"Extractor dequeued: {source}")
                self._process_task(task_data)

            except KeyboardInterrupt:
                click.echo("Extractor Worker stopping...")
                break
            except Exception as e:
                click.secho(f"Extractor Worker error: {e}", fg="red")
                # In a real system, we might want to re-queue or DLQ here if it wasn't a data error
                # For now, let's log and continue

    def _process_task(self, data: dict):
        file_path_str = data.get("file_path")
        if not file_path_str:
            return

        file_path = Path(file_path_str)
        click.echo(f"Extracting text from: {file_path.name}")

        try:
            raw_text = self.parser.extract_text(file_path)

            source_gdrive_path = data.get("source_gdrive_path") or data.get("source_rel_path")
            if not source_gdrive_path:
                try:
                    source_gdrive_path = file_path.relative_to(
                        self.settings.gdrive_local_dest_dir
                    ).as_posix()
                except ValueError:
                    source_gdrive_path = file_path.name

            candidate_id = candidate_id_from_source_gdrive_path(source_gdrive_path)

            event = TextExtractedEvent(
                file_path=str(file_path),
                text=raw_text,
                candidate_id=candidate_id,
                source_category=data.get("source_category"),
                source_rel_path=data.get("source_rel_path") or source_gdrive_path,
                source_gdrive_path=source_gdrive_path,
                mtime_ns=data.get("mtime_ns"),
                size_bytes=data.get("size_bytes"),
                detected_at=data.get("detected_at"),
                event_id=data.get("event_id"),
            )

            self.redis.push_to_queue(QUEUE_ENRICH_TASK, event.to_dict())
            click.echo("-> Text extracted. Pushed to Enrich Queue.")

        except Exception as e:
            click.secho(f"Failed to extract {file_path.name}: {e}", fg="red")
            self.redis.push_to_queue(
                QUEUE_DLQ, {"stage": "extractor", "error": str(e), "original_task": data}
            )


class EnricherWorker:
    def __init__(
        self,
        settings: Settings,
        redis_client: RedisClient,
        db: CVDatabase | None = None,
        client: OpenAIClient | None = None,
        embedder: EmbedderProtocol | None = None,
        parser: CVParser | None = None,
    ):
        self.settings = settings
        self.redis = redis_client
        self.db = db or CVDatabase(settings)
        self.embedder = embedder or LocalEmbedder()
        self.client = client or OpenAIClient(settings)
        self.parser = parser or CVParser()

    def close(self):
        if self.db:
            self.db.close()
            self.db = None

    def run(self):
        click.echo("Enricher Worker started. Waiting for tasks...")
        try:
            while True:
                try:
                    task_data = self.redis.pop_from_queue(QUEUE_ENRICH_TASK, timeout=5)
                    if not task_data:
                        continue

                    source = (
                        task_data.get("source_gdrive_path")
                        or task_data.get("source_rel_path")
                        or task_data.get("file_path")
                        or "<unknown>"
                    )
                    click.echo(f"Enricher dequeued: {source}")
                    self._process_task(task_data)

                except KeyboardInterrupt:
                    click.echo("Enricher Worker stopping...")
                    break
                except Exception as e:
                    click.secho(f"Enricher Worker error: {e}", fg="red")
        finally:
            self.close()

    def _process_task(self, data: dict):
        candidate_id = data.get("candidate_id")
        file_path_str = data.get("file_path")
        text = data.get("text")
        source_category = data.get("source_category")

        if not candidate_id or not text:
            return

        click.echo(f"Enriching candidate: {candidate_id}")

        try:
            # Determine role_key from path if possible, similar to original pipeline
            # The original pipeline used folder structure.
            # We can try to infer it or pass it.
            # In the original code: role_key = self._normalize_folder_name(path_parts[1])
            # We passed source_category, but maybe not the role subfolder.
            # Let's re-derive it from file_path for simplicity or just pass "n/a"

            file_path = Path(file_path_str)
            # We need to know the inbox dir to get relative path for role
            # But we don't have it easily here unless we pass it or config.
            # Let's try to use source_category as a hint if it's not None

            role_key = ""
            # Basic heuristic: if source_category is set, maybe that's it?
            # Or we just let the LLM figure it out without a hint.
            # The original code passed role_key to get_structured_cv.

            cv_data_dict = self.client.get_structured_cv(
                text,
                role_key,  # We might need to improve this
                self.settings.openai_model,
                self.settings,
            )

            # Add metadata
            ingestion_time = datetime.now()
            file_stat = file_path.stat()
            mod_time = datetime.fromtimestamp(file_stat.st_mtime)

            source_gdrive_path = data.get("source_gdrive_path") or data.get("source_rel_path")
            if not source_gdrive_path:
                try:
                    source_gdrive_path = file_path.relative_to(
                        self.settings.gdrive_local_dest_dir
                    ).as_posix()
                except ValueError:
                    source_gdrive_path = file_path.name

            cv_data_dict["candidate_id"] = candidate_id
            cv_data_dict["last_updated"] = mod_time.isoformat()
            cv_data_dict["source_filename"] = file_path.name
            cv_data_dict["ingestion_timestamp"] = ingestion_time.isoformat()
            cv_data_dict["source_gdrive_path"] = source_gdrive_path
            cv_data_dict["source_category"] = source_category

            from cv_search.ingestion.pipeline import CVIngestionPipeline

            pipeline = CVIngestionPipeline(
                self.db,
                self.settings,
                embedder=self.embedder,
                client=self.client,
                parser=self.parser,
            )

            unmapped: list[str] = []
            tech_tags, miss_top = pipeline._map_tech_tags(cv_data_dict.get("tech_tags", []))
            cv_data_dict["tech_tags"] = tech_tags
            unmapped.extend(miss_top)
            experiences = cv_data_dict.get("experience", []) or []
            for exp in experiences:
                mapped_exp, miss_exp = pipeline._map_tech_tags(exp.get("tech_tags", []))
                exp["tech_tags"] = mapped_exp
                unmapped.extend(miss_exp)
            unmapped = pipeline._uniq(unmapped)
            pipeline._log_unmapped_techs(
                file_path.name, candidate_id, unmapped, cv_data_dict["ingestion_timestamp"]
            )

            # Save JSON (optional, but good for debug)
            base_data_dir = self.settings.data_dir
            json_output_dir = base_data_dir / "ingested_cvs_json"
            json_output_dir.mkdir(exist_ok=True)
            json_filename = f"{candidate_id}.json"
            with open(json_output_dir / json_filename, "w", encoding="utf-8") as f:
                json.dump(cv_data_dict, f, indent=2, ensure_ascii=False)

            # Write to DB
            # We need to use the pipeline logic for DB upsert.
            # We can duplicate the logic or import CVIngestionPipeline.
            # Importing CVIngestionPipeline might be cleaner to reuse _ingest_single_cv
            cid, vs_text, doc_payload = pipeline._ingest_single_cv(cv_data_dict)
            embedding = pipeline.embedder.get_embeddings([vs_text])[0]

            self.db.upsert_candidate_doc(
                candidate_id=cid,
                summary_text=doc_payload["summary_text"],
                experience_text=doc_payload["experience_text"],
                tags_text=doc_payload["tags_text"],
                last_updated=doc_payload["last_updated"],
                location=doc_payload["location"],
                seniority=doc_payload["seniority"],
                embedding=embedding,
            )

            self.db.commit()

            click.echo(f"-> Enriched and saved: {candidate_id}")

        except Exception as e:
            click.secho(f"Failed to enrich {candidate_id}: {e}", fg="red")
            self.db.rollback()
            self.redis.push_to_queue(
                QUEUE_DLQ, {"stage": "enricher", "error": str(e), "original_task": data}
            )
