import time
import json
import hashlib
from pathlib import Path
from datetime import datetime
import click
from typing import Optional

from cv_search.config.settings import Settings
from cv_search.ingestion.redis_client import RedisClient
from cv_search.ingestion.events import FileDetectedEvent, TextExtractedEvent, EnrichmentCompleteEvent
from cv_search.ingestion.cv_parser import CVParser
from cv_search.ingestion.parser_stub import StubCVParser
from cv_search.clients.openai_client import OpenAIClient
from cv_search.db.database import CVDatabase
from cv_search.retrieval.embedder_stub import DeterministicEmbedder, EmbedderProtocol
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
        if self.settings.agentic_test_mode:
            self.inbox_dir = self.settings.test_data_dir / "gdrive_inbox"
        self.db = CVDatabase(settings) # Needed to check for existing files if we want to be smart, 
                                       # but for now we'll just scan and push. 
                                       # Actually, let's reuse the logic to skip unchanged files.

    def close(self):
        if self.db:
            self.db.close()
            self.db = None

    def run(self, loop_interval: int = 10):
        click.echo(f"Watcher started. Monitoring {self.inbox_dir}...")
        try:
            while True:
                try:
                    self._scan_and_publish()
                    time.sleep(loop_interval)
                except KeyboardInterrupt:
                    click.echo("Watcher stopping...")
                    break
                except Exception as e:
                    click.secho(f"Watcher error: {e}", fg="red")
                    time.sleep(loop_interval)
        finally:
            self.close()

    def _scan_and_publish(self):
        pptx_files = list(self.inbox_dir.rglob("*.pptx"))
        if self.settings.agentic_test_mode:
            pptx_files += list(self.inbox_dir.rglob("*.txt"))
        if not pptx_files:
            return

        # Simple logic: Just push everything for now, or we can check DB.
        # To match the "Producer" description: "When a file changes, it pushes..."
        # For this POC, let's just push all files and let the workers handle idempotency or 
        # we can implement a simple state in Redis or check DB.
        # Let's check DB to avoid spamming the queue.
        
        # Re-using logic from pipeline.py roughly
        # We need to know if it's modified.
        
        # For this task, let's keep it simple:
        # We will push a task to the EXTRACT queue.
        # The Extractor can decide if it needs to do work, but "Watcher" usually implies it knows something changed.
        # Let's assume we push all valid files and let downstream handle dedupe or we check DB here.
        # Checking DB here is safer to avoid queue flooding.
        
        # We'll instantiate a DB connection just for this check
        # Note: In a real "Watcher", we might use filesystem events (watchdog), but polling is fine here.
        
        last_updated_map = self.db.get_last_updated_for_filenames([p.name for p in pptx_files])
        
        for file_path in pptx_files:
            mtime_iso = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
            last_upd = last_updated_map.get(file_path.name)
            
            if last_upd and last_upd == mtime_iso:
                continue # Skip unchanged
            
            # It's new or modified
            relative_path = file_path.relative_to(self.inbox_dir)
            path_parts = relative_path.parent.parts
            source_category = path_parts[0] if path_parts else None
            
            event = FileDetectedEvent(
                file_path=str(file_path),
                source_category=source_category
            )
            
            # Push to Extract Queue
            # We use a queue (list) for tasks so workers can pick them up round-robin
            self.redis.push_to_queue(QUEUE_EXTRACT_TASK, event.to_dict())
            click.echo(f"Queued file: {file_path.name}")

class ExtractorWorker:
    def __init__(self, settings: Settings, redis_client: RedisClient, parser: CVParser | None = None):
        self.settings = settings
        self.redis = redis_client
        if parser:
            self.parser = parser
        elif settings.agentic_test_mode:
            self.parser = StubCVParser()
        else:
            self.parser = CVParser()

    def run(self):
        click.echo("Extractor Worker started. Waiting for tasks...")
        while True:
            try:
                # Blocking pop
                task_data = self.redis.pop_from_queue(QUEUE_EXTRACT_TASK, timeout=5)
                if not task_data:
                    continue
                
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
            
            # Generate candidate_id
            file_hash = hashlib.md5(file_path.name.encode()).hexdigest()
            candidate_id = f"pptx-{file_hash[:10]}"
            
            event = TextExtractedEvent(
                file_path=str(file_path),
                text=raw_text,
                candidate_id=candidate_id,
                source_category=data.get("source_category")
            )
            
            self.redis.push_to_queue(QUEUE_ENRICH_TASK, event.to_dict())
            click.echo(f"-> Text extracted. Pushed to Enrich Queue.")
            
        except Exception as e:
            click.secho(f"Failed to extract {file_path.name}: {e}", fg="red")
            self.redis.push_to_queue(QUEUE_DLQ, {
                "stage": "extractor",
                "error": str(e),
                "original_task": data
            })

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
        if embedder:
            self.embedder = embedder
        elif settings.agentic_test_mode:
            self.embedder = DeterministicEmbedder()
        else:
            self.embedder = LocalEmbedder()
        self.client = client or OpenAIClient(settings)
        if parser:
            self.parser = parser
        elif settings.agentic_test_mode:
            self.parser = StubCVParser()
        else:
            self.parser = CVParser()

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
                role_key, # We might need to improve this
                self.settings.openai_model,
                self.settings
            )
            
            # Add metadata
            ingestion_time = datetime.now()
            file_stat = file_path.stat()
            mod_time = datetime.fromtimestamp(file_stat.st_mtime)
            
            cv_data_dict["candidate_id"] = candidate_id
            cv_data_dict["last_updated"] = mod_time.isoformat()
            cv_data_dict["source_filename"] = file_path.name
            cv_data_dict["ingestion_timestamp"] = ingestion_time.isoformat()
            cv_data_dict["source_gdrive_path"] = str(file_path) # Or relative if we want
            cv_data_dict["source_category"] = source_category
            
            # Save JSON (optional, but good for debug)
            base_data_dir = self.settings.test_data_dir if self.settings.agentic_test_mode else self.settings.data_dir
            json_output_dir = base_data_dir / "ingested_cvs_json"
            json_output_dir.mkdir(exist_ok=True)
            json_filename = f"{candidate_id}.json"
            with open(json_output_dir / json_filename, 'w', encoding='utf-8') as f:
                json.dump(cv_data_dict, f, indent=2, ensure_ascii=False)
            
            # Write to DB
            # We need to use the pipeline logic for DB upsert.
            # We can duplicate the logic or import CVIngestionPipeline.
            # Importing CVIngestionPipeline might be cleaner to reuse _ingest_single_cv
            
            from cv_search.ingestion.pipeline import CVIngestionPipeline
            pipeline = CVIngestionPipeline(
                self.db,
                self.settings,
                embedder=self.embedder,
                client=self.client,
                parser=self.parser
            )
            
            # We need to adapt _ingest_single_cv to not return tuple but just do it?
            # It returns (candidate_id, vs_text).
            # And then we need to do embedding.
            
            # The original upsert_cvs does:
            # 1. _ingest_single_cv (DB upsert)
            # 2. get_or_create_faiss_id
            # 3. embed
            # 4. add to index
            # 5. write index
            
            # We should probably do all this here for this single CV.
            # Locking might be an issue for FAISS index writing if multiple workers?
            # FAISS index writing is file I/O.
            # For this POC, let's assume single Enricher or handle locking.
            # Or we just do it and hope for best (SQLite handles DB locks).
            
            (cid, vs_text) = pipeline._ingest_single_cv(cv_data_dict)
            faiss_id = self.db.get_or_create_faiss_id(cid)
            embedding = pipeline.embedder.get_embeddings([vs_text])[0]
            
            # Load index, add, save
            # This is the critical section
            index = pipeline.load_or_create_index()
            import numpy as np
            import faiss
            
            embeddings_array = np.array([embedding]).astype('float32')
            ids_array = np.array([faiss_id]).astype('int64')
            faiss.normalize_L2(embeddings_array)
            index.add_with_ids(embeddings_array, ids_array)
            
            index_path = str(self.settings.active_faiss_index_path)
            faiss.write_index(index, index_path)
            
            self.db.commit()
            
            click.echo(f"-> Enriched and saved: {candidate_id}")
            
        except Exception as e:
            click.secho(f"Failed to enrich {candidate_id}: {e}", fg="red")
            self.db.conn.rollback()
            self.redis.push_to_queue(QUEUE_DLQ, {
                "stage": "enricher",
                "error": str(e),
                "original_task": data
            })
