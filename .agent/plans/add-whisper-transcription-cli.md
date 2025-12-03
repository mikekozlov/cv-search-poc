# Add Whisper transcription CLI command

This ExecPlan is a living document maintained in accordance with .agent/PLANS.md. Keep it self-contained so a novice can implement and validate the Whisper transcription command without prior context.

## Purpose / Big Picture

Add a simple Click command that takes an audio file path, sends it to OpenAI Whisper (or Azure deployment), and saves the transcript to an output file. This lets users convert recorded calls or voice memos into text from the existing CLI without touching the rest of the search pipeline. Acceptance is a saved transcript file and passing integration tests.

## Progress

- [x] (2025-12-03 05:41Z) Reviewed CLI/package layout and drafted this plan for the new Whisper transcription command.
- [x] (2025-12-03 05:46Z) Implemented OpenAI client support for audio transcription with env-flagged stub fallback and configurable audio model.
- [x] (2025-12-03 05:47Z) Added a Click command module to write transcripts to disk with default .txt output and error handling.
- [x] (2025-12-03 05:48Z) Documented the command/config in README and env examples; added stub toggle guidance.
- [x] (2025-12-03 05:49Z) Added integration coverage using the stub backend and temporary audio/output files.
- [x] (2025-12-03 05:58Z) Ran integration suite with stubbed OpenAI + deterministic embeddings; all tests passed with existing warnings only.

## Surprises & Discoveries

- Observation: cv_search.cli.__init__ referenced presale_search without importing it, which would raise at CLI import time; fixed while registering the new transcription module.
  Evidence: _register_commands tuple included presale_search without binding; adding explicit import prevented NameError during CLI wiring.
- Observation: CV ingestion defaulted to LocalEmbedder and attempted HuggingFace downloads despite offline env flags; added deterministic embedder fallback keyed off USE_DETERMINISTIC_EMBEDDER/HF_HUB_OFFLINE.
  Evidence: ingest-mock CLI tried hitting huggingface.co until the pipeline respected the env flag.
- Observation: CLI exposed the multi-seat search only as multiseat-search while docs/tests used project-search; added an alias to keep both names working.
  Evidence: integration test for project-search failed with "No such command" before alias registration.
- Observation: docker compose and uv cache paths were blocked in this environment; reused an already-running Postgres instance and ran tests via .venv python instead of uv.
  Evidence: docker compose reported pipe access denied; uv run failed to open cache; direct python -m pytest succeeded.

## Decision Log

- Decision: Use env flag USE_OPENAI_STUB to opt into StubOpenAIBackend across the client, covering audio transcription to keep tests/networkless runs stable. Rationale: avoids real OpenAI calls with test keys and supports offline integration tests. Date/Author: 2025-12-03 / assistant.
- Decision: Default transcript output path is the input file with a .txt suffix, allowing --output override; only the saved path is echoed to keep CLI noise minimal. Rationale: predictable location without dumping long transcripts to stdout. Date/Author: 2025-12-03 / assistant.
- Decision: Stub transcription returns fixture text when available or a deterministic "Stub transcript for <filename>" string to keep tests simple without extra assets. Rationale: deterministic content without adding binary audio fixtures. Date/Author: 2025-12-03 / assistant.
- Decision: Honor USE_DETERMINISTIC_EMBEDDER/HF_HUB_OFFLINE inside CVIngestionPipeline to swap in DeterministicEmbedder for offline runs. Rationale: avoid HuggingFace traffic during mock ingestion/tests in restricted environments. Date/Author: 2025-12-03 / assistant.
- Decision: Register project-search as the primary multi-seat command while aliasing multiseat-search for backward compatibility. Rationale: align with docs/tests without breaking older invocations. Date/Author: 2025-12-03 / assistant.

## Outcomes & Retrospective

Whisper transcription is available via transcribe-audio with configurable audio model and stubbed output when requested. OpenAIClient now supports audio and honors USE_OPENAI_STUB globally; ingestion respects deterministic embedder flags to stay offline. CLI command parity restored for project-search and multiseat-search. Integration suite passes locally using .venv python with test env vars set inline. Remaining warnings are pre-existing (pytest return-not-none and Redis fallback).

## Context and Orientation

The CLI entrypoint lives in main.py and delegates to src/cv_search/cli, where commands are grouped under src/cv_search/cli/commands with a register(cli) pattern. CLIContext in src/cv_search/cli/context.py builds Settings, OpenAIClient, and CVDatabase; Settings draws from .env with defaults in src/cv_search/config/settings.py. OpenAIClient in src/cv_search/clients/openai_client.py currently wraps chat completion use cases and has a Stub backend for fixtures under data/test/llm_stubs, though it is not yet used automatically. Integration tests invoke the CLI via click.testing (tests/integration/helpers.py) and rely on PowerShell-style env vars; tests run against Postgres/pgvector using docker-compose.pg.yml. No audio/transcription support exists yet.

## Plan of Work

Extend OpenAIClient and its backends to support audio transcription, including a stub path toggled by an env flag so tests do not require network access. Add a configurable audio model name (default whisper-1) to Settings and env examples. Create a new CLI command module (e.g., transcription.py) that accepts an input audio path, optional output path, and optional prompt, then writes the transcript text to a file (default alongside the source with .txt). Register the command in cv_search.cli.__init__ alongside existing modules. Update README and .env.example with PowerShell instructions for the new command and config. Add an integration test that uses the stub backend and temporary files to assert the transcript file is created with expected contents. Keep error handling user-friendly (ClickException) and ensure the command returns a useful message/path.

## Concrete Steps

Work from repo root: C:\Users\mykha\Projects\cv-search-poc.

1) Update src/cv_search/clients/openai_client.py: add an env-flagged stub toggle (e.g., USE_OPENAI_STUB), a transcribe_audio method on the protocol, live backend implementation using client.audio.transcriptions.create, and a stub implementation returning fixture text. Add Settings.openai_audio_model defaulting to whisper-1 and expose env override. Keep Azure/OpenAI compatibility.  
2) Add src/cv_search/cli/commands/transcription.py with a Click command transcribe-audio that takes --input (required file), --output (optional), and --prompt (optional), uses the CLIContext.client transcribe method, writes UTF-8 text to disk, and echoes the saved path. Register the module in src/cv_search/cli/__init__.py.  
3) Document usage and config: update README.md CLI section with a PowerShell example, and add OPENAI_AUDIO_MODEL/USE_OPENAI_STUB to .env.example (and test env helpers if needed).  
4) Testing: add an integration test under tests/integration that sets USE_OPENAI_STUB, creates a temp audio file, runs the command via run_cli, and asserts the transcript file exists with stub content.  
5) Run required tests per AGENTS.md from repo root:  
    PS C:\Users\mykha\Projects\cv-search-poc> docker compose -f docker-compose.pg.yml up -d  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DB_URL = "postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:RUNS_DIR = "data/test/tmp/runs"  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DATA_DIR = "data/test"  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:GDRIVE_LOCAL_DEST_DIR = "data/test/gdrive_inbox"  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:OPENAI_API_KEY = "test-key"  
    PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest tests\integration -q

## Validation and Acceptance

Behavioral acceptance: running `python main.py transcribe-audio --input <audio_file>` writes a transcript text file (default <audio_file>.txt) and reports the saved path; with USE_OPENAI_STUB=1 it uses stubbed output. Integration tests pass in the local environment using the mandated command sequence. Documentation shows the PowerShell invocation and new env variables.

## Idempotence and Recovery

The command is additive and writing to user-specified paths; rerunning overwrites the transcript file safely. Stub mode avoids external calls. If OpenAI/Azure calls fail, the CLI should raise a clear ClickException so reruns are straightforward after fixing credentials or connectivity. Tests clean up temp files via pytest tmp_path.

## Artifacts and Notes

Capture any error transcripts or snippets proving success (e.g., CLI output, sample transcript text) once available.

## Interfaces and Dependencies

Add Settings.openai_audio_model: str = "whisper-1" (env OPENAI_AUDIO_MODEL). Extend OpenAIBackendProtocol with transcribe_audio(audio_path: Path, model: str, prompt: str | None = None) -> str. Implement LiveOpenAIBackend.transcribe_audio using client.audio.transcriptions.create(..., response_format="text"). Implement StubOpenAIBackend.transcribe_audio returning fixture text (audio_transcription.txt if present) or a deterministic stub string. OpenAIClient picks Stub backend automatically when USE_OPENAI_STUB env flag is truthy unless an explicit backend is provided. The new Click command lives in src/cv_search/cli/commands/transcription.py and is registered in src/cv_search/cli/__init__.py under the name transcribe-audio.

---

Revision note: initial version of this plan created to introduce Whisper transcription CLI support; updated 2025-12-03 with completed steps, stub flag decisions, ingestion embedder fallback, CLI alias fix, and test execution details.
