import time
import threading
import queue
from pathlib import Path
from typing import Any, Callable, Optional
from unittest.mock import MagicMock, patch
import sys

# Mock redis module before importing anything that uses it
# This is crucial because we might not have redis installed in the environment
sys.modules["redis"] = MagicMock()

# Import components (assuming they are in src path)
sys.path.append("src")

from cv_search.ingestion.async_pipeline import Watcher, ExtractorWorker, EnricherWorker
from cv_search.config.settings import Settings

# Mock Redis Client for testing without real Redis
class MockRedisClient:
    def __init__(self):
        self.queues = {
            "ingest:queue:extract": queue.Queue(),
            "ingest:queue:enrich": queue.Queue(),
            "ingest:queue:dlq": queue.Queue(),
        }
        print("[MockRedis] Initialized.")

    def push_to_queue(self, queue_name: str, message: dict[str, Any]):
        print(f"[MockRedis] Pushing to {queue_name}: {message}")
        self.queues[queue_name].put(message)

    def pop_from_queue(self, queue_name: str, timeout: int = 0) -> Optional[dict[str, Any]]:
        try:
            # Non-blocking for test speed, or short timeout
            return self.queues[queue_name].get(timeout=1)
        except queue.Empty:
            return None

def test_pipeline():
    print("--- Starting Pipeline Verification ---")
    
    # Mock Settings
    settings = MagicMock(spec=Settings)
    settings.gdrive_local_dest_dir = Path("./data/gdrive_inbox")
    settings.data_dir = Path("./data")
    settings.openai_api_key = "mock-key"
    settings.openai_model = "mock-model"
    settings.faiss_index_path = Path("./data/index.faiss")
    
    # Mock Redis
    redis_client = MockRedisClient()
    
    # Mock CVParser to avoid real file I/O and PPTX parsing
    with patch("cv_search.ingestion.async_pipeline.CVParser") as MockParser:
        mock_parser_instance = MockParser.return_value
        mock_parser_instance.extract_text.return_value = "Mock CV Text Content"
        
        # Mock OpenAIClient
        with patch("cv_search.ingestion.async_pipeline.OpenAIClient") as MockClient:
            mock_client_instance = MockClient.return_value
            mock_client_instance.get_structured_cv.return_value = {
                "candidate_id": "mock-id",
                "summary": "Mock Summary",
                "experience": []
            }
            
            # Mock Database
            with patch("cv_search.ingestion.async_pipeline.CVDatabase") as MockDB:
                
                # Mock CVIngestionPipeline (the synchronous part used by Enricher)
                with patch("cv_search.ingestion.async_pipeline.CVIngestionPipeline") as MockSyncPipeline:
                    mock_sync_pipeline = MockSyncPipeline.return_value
                    mock_sync_pipeline._ingest_single_cv.return_value = ("mock-id", "mock-vs-text")
                    mock_sync_pipeline.local_embedder.get_embeddings.return_value = [[0.1, 0.2]]
                    mock_sync_pipeline.load_or_create_index.return_value = MagicMock()
                    
                    # 1. Run Watcher (simulate finding a file)
                    # We'll manually push a file event to skip filesystem scanning setup
                    print("\n[Step 1] Simulating Watcher...")
                    file_event = {
                        "file_path": "data/gdrive_inbox/Sales/John_Doe.pptx",
                        "source_category": "Sales"
                    }
                    redis_client.push_to_queue("ingest:queue:extract", file_event)
                    
                    # 2. Run Extractor
                    print("\n[Step 2] Running Extractor...")
                    extractor = ExtractorWorker(settings, redis_client)
                    # Run one iteration
                    task = redis_client.pop_from_queue("ingest:queue:extract")
                    if task:
                        extractor._process_task(task)
                    
                    # 3. Run Enricher
                    print("\n[Step 3] Running Enricher...")
                    enricher = EnricherWorker(settings, redis_client)
                    # Run one iteration
                    task = redis_client.pop_from_queue("ingest:queue:enrich")
                    if task:
                        enricher._process_task(task)
                        
                    print("\n--- Verification Complete ---")
                    # Check if DLQ is empty
                    if not redis_client.queues["ingest:queue:dlq"].empty():
                        print("WARNING: DLQ is not empty!")
                        print(redis_client.queues["ingest:queue:dlq"].get())
                    else:
                        print("SUCCESS: DLQ is empty.")

if __name__ == "__main__":
    test_pipeline()
