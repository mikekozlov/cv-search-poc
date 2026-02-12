from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import click

from cv_search.clients.openai_client import OpenAIClient
from cv_search.config.settings import Settings
from cv_search.db.database import CVDatabase
from cv_search.ingestion.data_loader import load_ingested_cvs_json, load_mock_cvs
from cv_search.ingestion.cv_parser import CVParser
from cv_search.lexicon.loader import load_tech_synonym_map, build_tech_reverse_index
from cv_search.ingestion.redaction import sanitize_cv_payload
from cv_search.ingestion.file_selection import select_latest_candidate_files
from cv_search.ingestion.source_identity import (
    candidate_id_from_source_gdrive_path,
    candidate_name_from_source_gdrive_path,
    is_probably_full_name,
)


class CVIngestionPipeline:
    def __init__(
        self,
        db: CVDatabase,
        settings: Settings,
        client: OpenAIClient | None = None,
        parser: CVParser | None = None,
    ):
        self.db = db
        self.settings = settings
        self.client = client or OpenAIClient(settings)
        self.parser = parser or CVParser()
        self.tech_syn_map = load_tech_synonym_map(settings.lexicon_dir)
        self.tech_reverse_index = build_tech_reverse_index(self.tech_syn_map)
        self.unmapped_dir = Path(self.settings.data_dir) / "ingest_unmapped_techs"

    def close(self) -> None:
        """Release DB handle held by this pipeline."""
        try:
            if self.db:
                self.db.close()
        finally:
            self.db = None

    def _canon_tags(self, seq: Iterable[str]) -> List[str]:
        return self._uniq([(s or "").strip().lower() for s in (seq or [])])

    def _uniq(self, seq: Iterable[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for x in seq:
            xl = (x or "").strip()
            if not xl:
                continue
            k = xl.lower()
            if k not in seen:
                seen.add(k)
                out.append(xl)
        return out

    def _map_tech_tags(self, tags: Iterable[str]) -> tuple[List[str], List[str]]:
        mapped: List[str] = []
        unmapped: List[str] = []
        for raw in tags or []:
            val = (raw or "").strip().lower()
            if not val:
                continue
            canon = self.tech_reverse_index.get(val)
            if canon:
                if canon not in mapped:
                    mapped.append(canon)
            else:
                if val not in unmapped:
                    unmapped.append(val)
        return mapped, unmapped

    def _log_unmapped_techs(
        self, source_filename: str, candidate_id: str, unmapped: List[str], ingestion_ts: str
    ) -> None:
        if not unmapped:
            return
        self.unmapped_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "source_filename": source_filename,
            "candidate_id": candidate_id,
            "ingestion_timestamp": ingestion_ts,
            "unmapped_techs": unmapped,
        }
        path = self.unmapped_dir / f"{candidate_id}_unmapped_techs.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

    def _mk_experience_line(self, exp: Dict[str, Any]) -> str:
        """Format a single experience block for search text."""
        title = exp.get("title", "")
        company = exp.get("company", "")
        domains = ", ".join(self._canon_tags(exp.get("domain_tags", []) or []))
        techs = ", ".join(self._canon_tags(exp.get("tech_tags", []) or []))
        project_description = (
            exp.get("project_description") or exp.get("description") or ""
        ).strip()
        responsibilities_raw = exp.get("responsibilities") or []
        if isinstance(responsibilities_raw, str):
            responsibilities = [responsibilities_raw]
        else:
            responsibilities = [r.strip() for r in responsibilities_raw if r]

        header_parts = [p for p in [title.strip(), company] if p]
        header = " @ ".join(header_parts) if header_parts else ""

        meta_bits = []
        if domains:
            meta_bits.append(f"domains: {domains}")
        if techs:
            meta_bits.append(f"tech: {techs}")

        lines = []
        if header:
            lines.append(header)
        if meta_bits:
            lines.append(" | ".join(meta_bits))
        if project_description:
            lines.append(f"Project: {project_description}")
        if responsibilities:
            lines.append("Responsibilities: " + " ; ".join(responsibilities))
        return "\n".join([ln for ln in lines if ln]).strip()

    def _select_recent_experiences(
        self, experiences: List[Dict[str, Any]], limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Pick the most recent experiences (assumes input is already ordered newest-first)."""
        if not experiences:
            return []
        return list(experiences[: max(0, limit)])

    def _build_candidate_doc_texts(
        self,
        cv: Dict[str, Any],
        domain_rollup: List[str],
        experiences_for_text: List[Dict[str, Any]],
        qualification_tokens: List[str],
    ) -> Tuple[str, str, str]:
        summary_text = cv.get("summary", "") or ""
        exp_lines = [self._mk_experience_line(e) for e in experiences_for_text]
        experience_text = " \n".join([ln for ln in exp_lines if ln])
        roles = self._canon_tags(cv.get("role_tags", []) or [])
        expertise = self._canon_tags(cv.get("expertise_tags", []) or [])
        techs = self._canon_tags(cv.get("tech_tags", []) or [])
        senior = self._canon_tags([cv.get("seniority", "")]) if cv.get("seniority") else []
        domains = self._canon_tags(domain_rollup)
        distinct = self._uniq(roles + expertise + techs + domains + senior + qualification_tokens)
        tags_text = " ".join(distinct)
        return summary_text, experience_text, tags_text

    def _ingest_single_cv(self, cv: Dict[str, Any]) -> Tuple[str, str, Dict[str, str]]:
        candidate_id = cv.get("candidate_id")
        if not candidate_id:
            raise ValueError("candidate_id is required for ingestion")
        cv = sanitize_cv_payload(
            cv,
            candidate_id=candidate_id,
            name_hint=cv.get("name"),
            filename_hint=cv.get("source_gdrive_path") or cv.get("source_filename"),
            salt=self.settings.candidate_name_salt,
            prefix=self.settings.candidate_name_prefix,
        )
        candidate_id = cv["candidate_id"]

        self.db.upsert_candidate(cv)

        self.db.remove_candidate_derived(candidate_id)

        role_tags_top = self._canon_tags(cv.get("role_tags", []) or [])
        expertise_tags_top = self._canon_tags(cv.get("expertise_tags", []) or [])
        tech_tags_top = self._canon_tags(cv.get("tech_tags", []) or [])
        seniority = (cv.get("seniority", "") or "").strip().lower()

        experiences = cv.get("experience", []) or []
        domain_tags_list = [
            self._canon_tags(exp.get("domain_tags", []) or []) for exp in experiences
        ]
        tech_tags_list = [self._canon_tags(exp.get("tech_tags", []) or []) for exp in experiences]
        domain_rollup = self._canon_tags([tag for sublist in domain_tags_list for tag in sublist])
        qualifications_raw = cv.get("qualifications") or {}
        qualification_tokens: List[str] = []
        for cat, items in qualifications_raw.items():
            cat_clean = (cat or "").strip().lower()
            for item in items or []:
                item_clean = (item or "").strip().lower()
                if item_clean:
                    qualification_tokens.append(item_clean)
                    if cat_clean:
                        qualification_tokens.append(f"{cat_clean}:{item_clean}")

        experiences_for_text = self._select_recent_experiences(experiences, limit=3)

        self.db.insert_experiences_and_tags(
            candidate_id, experiences, domain_tags_list, tech_tags_list
        )

        if qualifications_raw:
            self.db.insert_candidate_qualifications(candidate_id, qualifications_raw)

        self.db.upsert_candidate_tags(
            candidate_id,
            role_tags=role_tags_top,
            expertise_tags=expertise_tags_top,
            tech_tags_top=tech_tags_top,
            seniority=seniority,
            domain_rollup=domain_rollup,
        )

        summary_text, experience_text, tags_text = self._build_candidate_doc_texts(
            cv,
            domain_rollup,
            experiences_for_text,
            qualification_tokens,
        )
        doc_payload = {
            "summary_text": summary_text,
            "experience_text": experience_text,
            "tags_text": tags_text,
            "last_updated": cv.get("last_updated", "") or "",
            "seniority": seniority,
        }

        vs_attributes = {
            "candidate_id": candidate_id,
            "role": role_tags_top[0] if role_tags_top else "",
            "seniority": seniority,
            "domains": domain_rollup,
            "expertise": expertise_tags_top,
            "tech": tech_tags_top,
        }

        role = (
            (vs_attributes.get("role") or "")
            if isinstance(vs_attributes.get("role"), str)
            else (vs_attributes.get("role") or "")
        )
        header = (
            f"candidate_id={candidate_id}"
            f" | role={role}"
            f" | seniority={vs_attributes.get('seniority') or ''}"
            f" | domains=[{', '.join(vs_attributes.get('domains') or [])}]"
            f" | expertise=[{', '.join(vs_attributes.get('expertise') or [])}]"
            f" | tech=[{', '.join(vs_attributes.get('tech') or [])}]"
        )
        parts = [
            header.strip(),
            "",
            (tags_text or "").strip(),
            "---",
            (summary_text or "").strip(),
            "---",
            (experience_text or "").strip(),
        ]
        vs_text = "\n".join(parts).strip() + "\n"

        return candidate_id, vs_text, doc_payload

    def upsert_cvs(self, cvs: List[Dict[str, Any]]) -> int:
        if not cvs:
            return 0

        try:
            for cv in cvs:
                candidate_id, vs_text, doc_payload = self._ingest_single_cv(cv)
                self.db.upsert_candidate_doc(
                    candidate_id=candidate_id,
                    summary_text=doc_payload["summary_text"],
                    experience_text=doc_payload["experience_text"],
                    tags_text=doc_payload["tags_text"],
                    last_updated=doc_payload["last_updated"],
                    seniority=doc_payload["seniority"],
                )

            self.db.commit()
            return len(cvs)
        except Exception:
            self.db.rollback()
            raise

    def reset_state(self, clear_runs_dir: bool = True) -> None:
        """Remove database artifacts so tests and mock ingestion start clean."""
        try:
            if self.db:
                self.db.reset_state()
        finally:
            if clear_runs_dir:
                runs_dir = Path(self.settings.runs_dir)
                if runs_dir.exists():
                    shutil.rmtree(runs_dir)

    def run_mock_ingestion(self) -> int:
        self.reset_state()
        try:
            self.db.close()
        except Exception:
            pass
        self.db = CVDatabase(self.settings)
        self.db.initialize_schema()

        cvs = load_mock_cvs(self.settings.test_data_dir)

        count = self.upsert_cvs(cvs)

        return count

    def run_json_ingestion(
        self,
        json_dir: Path | None = None,
        target_filename: str | None = None,
        candidate_id: str | None = None,
    ) -> Dict[str, Any]:
        json_dir = json_dir or (Path(self.settings.data_dir) / "ingested_cvs_json")

        if not json_dir.exists():
            click.echo(f"No JSON directory found at {json_dir}")
            return {
                "processed_count": 0,
                "status": "no_json_dir",
                "failed_files": [],
                "json_dir": str(json_dir),
            }

        cvs, failed_files = load_ingested_cvs_json(
            json_dir,
            target_filename=target_filename,
            candidate_id=candidate_id,
        )

        if not cvs:
            if failed_files:
                click.echo("No valid JSON payloads to ingest.")
                status = "no_valid_payloads"
            else:
                click.echo(f"No JSON files found in {json_dir}")
                status = "no_files"
            return {
                "processed_count": 0,
                "status": status,
                "failed_files": failed_files,
                "json_dir": str(json_dir),
            }

        click.echo(f"Found {len(cvs)} JSON CV(s) to ingest...")
        ingested_count = self.upsert_cvs(cvs)
        click.secho(
            f"Successfully upserted {ingested_count} CV(s) from JSON.",
            fg="green",
        )

        return {
            "processed_count": ingested_count,
            "status": "ok",
            "failed_files": failed_files,
            "json_dir": str(json_dir),
        }

    def _normalize_folder_name(self, name: str) -> str:
        s = name.lower().strip()
        s = re.sub(r"\s+", "_", s)
        s = re.sub(r"[^a-z0-9_]", "", s)
        return s

    def _process_single_cv_file(
        self,
        file_path: Path,
        parser: CVParser,
        client: OpenAIClient,
        json_output_dir: Path,
        inbox_dir: Path,
    ) -> tuple[str, dict | tuple[Path, str] | Path]:
        try:
            relative_path = file_path.relative_to(inbox_dir)
            source_gdrive_path_str = str(relative_path.as_posix())

            path_parts = relative_path.parent.parts
            source_category = path_parts[0] if path_parts else None

            role_key = ""
            if len(path_parts) >= 2:
                role_key = self._normalize_folder_name(path_parts[1])

            hint_display = role_key if role_key else "n/a"
            click.echo(f"  -> Processing {file_path.name} (Hint: {hint_display})...")

            raw_text = parser.extract_text(file_path)

            cv_data_dict = client.get_structured_cv(
                raw_text, role_key, self.settings.openai_model, self.settings
            )

            ingestion_time = datetime.now()

            candidate_id = candidate_id_from_source_gdrive_path(source_gdrive_path_str)
            cv_data_dict["candidate_id"] = candidate_id

            file_stat = file_path.stat()
            mod_time = datetime.fromtimestamp(file_stat.st_mtime)
            cv_data_dict["last_updated"] = mod_time.isoformat()

            cv_data_dict["source_filename"] = file_path.name
            cv_data_dict["ingestion_timestamp"] = ingestion_time.isoformat()
            cv_data_dict["source_gdrive_path"] = source_gdrive_path_str
            cv_data_dict["source_category"] = source_category

            unmapped: List[str] = []
            tech_tags, miss_top = self._map_tech_tags(cv_data_dict.get("tech_tags", []))
            cv_data_dict["tech_tags"] = tech_tags
            unmapped.extend(miss_top)
            experiences = cv_data_dict.get("experience", []) or []
            for exp in experiences:
                mapped_exp, miss_exp = self._map_tech_tags(exp.get("tech_tags", []))
                exp["tech_tags"] = mapped_exp
                unmapped.extend(miss_exp)
            unmapped = self._uniq(unmapped)
            self._log_unmapped_techs(
                file_path.name, candidate_id, unmapped, cv_data_dict["ingestion_timestamp"]
            )

            name_hint = cv_data_dict.get("name")
            if not is_probably_full_name(name_hint):
                fallback_name = candidate_name_from_source_gdrive_path(source_gdrive_path_str)
                if fallback_name:
                    cv_data_dict["name"] = fallback_name
                    name_hint = fallback_name
            cv_data_dict = sanitize_cv_payload(
                cv_data_dict,
                candidate_id=candidate_id,
                name_hint=name_hint,
                filename_hint=source_gdrive_path_str,
                salt=self.settings.candidate_name_salt,
                prefix=self.settings.candidate_name_prefix,
            )

            json_filename = f"{cv_data_dict['candidate_id']}.json"
            json_save_path = json_output_dir / json_filename
            with open(json_save_path, "w", encoding="utf-8") as f:
                json.dump(cv_data_dict, f, indent=2, ensure_ascii=False)

            return "processed", (file_path, cv_data_dict)

        except Exception as e:
            click.secho(f"  -> FAILED to parse {file_path.name}: {e}", fg="red")
            return "failed_parsing", file_path

    def _partition_gdrive_files(
        self, files: List[Path], inbox_dir: Path
    ) -> tuple[List[Path], Dict[str, List[str]]]:
        skipped: Dict[str, List[str]] = defaultdict(list)
        if not files:
            return [], skipped
        resolved_inbox = inbox_dir.resolve(strict=False)
        inside: list[tuple[Path, str]] = []
        selected: List[Path] = []
        for file_path in files:
            resolved_path = file_path.resolve(strict=False)
            try:
                relative_path = resolved_path.relative_to(resolved_inbox)
            except ValueError:
                display_path = str(resolved_path)
                click.secho(
                    f"Skipping {display_path}: outside Google Drive sync directory.", fg="yellow"
                )
                skipped["outside_gdrive"].append(display_path)
                continue
            inside.append((file_path, relative_path.as_posix()))

        last_updated_map = self.db.get_last_updated_for_gdrive_paths([rel for _, rel in inside])

        for file_path, relative_path_str in inside:
            mtime_iso = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
            last_upd = last_updated_map.get(relative_path_str)
            if last_upd and last_upd == mtime_iso:
                click.echo(f"Skipping {relative_path_str}: not modified since last ingestion.")
                skipped["unchanged"].append(relative_path_str)
                continue
            selected.append(file_path)
        return selected, skipped

    def run_gdrive_ingestion(
        self, client: OpenAIClient | None = None, target_filename: str | None = None
    ) -> Dict[str, Any]:
        parser = self.parser
        client = client or self.client

        inbox_dir = self.settings.gdrive_local_dest_dir
        base_data_dir = self.settings.data_dir
        json_output_dir = base_data_dir / "ingested_cvs_json"
        json_output_dir.mkdir(exist_ok=True)

        pptx_files = list(inbox_dir.rglob("*.pptx"))
        pptx_files += list(inbox_dir.rglob("*.txt"))

        if pptx_files:
            selected = select_latest_candidate_files(pptx_files, inbox_dir)
            pptx_files = list(selected.values())

        if target_filename:
            pptx_files = [p for p in pptx_files if p.name == target_filename]

        if not pptx_files:
            click.echo(f"No .pptx files found in {inbox_dir}")
            return {"processed_count": 0, "status": "no_files_found"}

        filtered, skip_reasons = self._partition_gdrive_files(pptx_files, inbox_dir)
        skipped_unchanged = skip_reasons.get("unchanged", [])
        skipped_outside = skip_reasons.get("outside_gdrive", [])

        if not filtered and skipped_unchanged:
            click.echo("No new or modified .pptx files to process.")
            return {
                "processed_count": 0,
                "status": "no_changes",
                "skipped_unchanged": skipped_unchanged,
                "skipped_outside_gdrive": skipped_outside,
                "skipped_roles": {},
                "skipped_ambiguous": [],
                "failed_files": [],
                "unmapped_tags": [],
                "json_output_dir": str(json_output_dir),
            }

        if not filtered:
            click.echo("No eligible .pptx files to process from Google Drive sync directory.")
            return {
                "processed_count": 0,
                "status": "no_eligible_files",
                "skipped_unchanged": skipped_unchanged,
                "skipped_outside_gdrive": skipped_outside,
                "skipped_roles": {},
                "skipped_ambiguous": [],
                "failed_files": [],
                "unmapped_tags": [],
                "json_output_dir": str(json_output_dir),
            }

        click.echo(f"Found {len(filtered)} .pptx CV(s) to process...")

        cvs_to_ingest = []
        processed_files = []
        failed_files = []
        skipped_ambiguous = []

        max_workers = min(10, len(filtered))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {
                executor.submit(
                    self._process_single_cv_file,
                    file_path,
                    parser,
                    client,
                    json_output_dir,
                    inbox_dir,
                ): file_path
                for file_path in filtered
            }

            for future in as_completed(future_to_path):
                status, data = future.result()

                if status == "processed":
                    file_path, cv_data = data
                    cvs_to_ingest.append(cv_data)
                    processed_files.append(file_path)
                elif status == "failed_parsing":
                    failed_files.append(str(data))
                elif status == "skipped_ambiguous":
                    skipped_ambiguous.append(str(data.relative_to(inbox_dir)))

        ingested_count = 0
        if cvs_to_ingest:
            click.echo(f"\nIngesting {len(cvs_to_ingest)} processed CV(s) into database...")
            ingested_count = self.upsert_cvs(cvs_to_ingest)
            click.secho(
                f"Successfully upserted {ingested_count} new CV(s). Index is updated.",
                fg="green",
            )
        else:
            click.echo("\nNo new CVs to ingest.")

        unmapped = [cv.get("unmapped_tags") for cv in cvs_to_ingest if cv.get("unmapped_tags")]
        all_unmapped_tags = []
        if unmapped:
            all_unmapped_tags = sorted(
                list(set(t.strip() for tags in unmapped for t in tags.split(",") if t.strip()))
            )

        return {
            "processed_count": ingested_count,
            "skipped_roles": {},
            "skipped_ambiguous": skipped_ambiguous,
            "failed_files": failed_files,
            "unmapped_tags": all_unmapped_tags,
            "json_output_dir": str(json_output_dir),
            "skipped_unchanged": skipped_unchanged,
            "skipped_outside_gdrive": skipped_outside,
        }

    def run_ingestion_from_list(self, cvs: List[Dict[str, Any]]) -> int:
        return self.upsert_cvs(cvs)
