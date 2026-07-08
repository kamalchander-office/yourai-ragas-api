"""Bootstrap a full PWA QA session: chat + vault attach + intents."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yourai_pwa.client import YourAIPWAClient
from yourai_pwa.config import PWAConfig, load_pwa_config
from yourai_pwa.intents import intent_by_key
from yourai_pwa.vault import document_is_ready

log = logging.getLogger(__name__)


def _session_shell(
    *,
    config: PWAConfig,
    me: dict[str, Any],
    conversation_id: str,
    new_chat: bool,
    intents: list[dict[str, Any]],
    default_intent_key: str,
) -> dict[str, Any]:
    default_intent = intent_by_key(intents, default_intent_key) or (intents[0] if intents else None)
    return {
        "spec_version": "1.1",
        "environment": "qa",
        "base_url": config.base_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user_id": str(me.get("id") or me.get("userId") or me.get("sub") or ""),
        "org_id": str(me.get("orgId") or me.get("org") or me.get("organizationId") or ""),
        "role": me.get("role"),
        "conversation_id": conversation_id,
        "new_chat": new_chat,
        "intents": intents,
        "default_intent_key": default_intent_key,
        "default_intent_id": (default_intent or {}).get("id", ""),
    }


def bootstrap_qa_session(
    document_path: Path,
    *,
    config: PWAConfig | None = None,
    new_chat: bool = True,
    document_name: str | None = None,
    default_intent_key: str = "GENERAL_CHAT",
) -> dict[str, Any]:
    """
    Legacy upload bootstrap:
      auth/me → conversations/start → intents → upload → poll → scope (single doc)
    """
    config = config or load_pwa_config()
    client = YourAIPWAClient(config)
    doc_path = Path(document_path).expanduser().resolve()

    log.info("Phase 1: auth + conversation bootstrap")
    me = client.auth_me()
    conversation_id = client.start_conversation(reuse=not new_chat)
    intents = client.get_intents()
    if not intents:
        log.warning("No intents returned from /knowledge-base/intents")

    log.info("Phase 2: vault upload + poll")
    upload = client.upload_document(doc_path, name=document_name)
    document_id = upload["id"]
    ready = client.poll_document_ready(document_id)

    log.info("Phase 3: attach document to conversation scope")
    client.set_conversation_scope(conversation_id, document_id)

    session = _session_shell(
        config=config,
        me=me,
        conversation_id=conversation_id,
        new_chat=new_chat,
        intents=intents,
        default_intent_key=default_intent_key,
    )
    session["bootstrap_mode"] = "upload"
    session["document"] = {
        "id": document_id,
        "name": upload.get("name") or doc_path.stem,
        "local_path": str(doc_path),
        "status": ready.get("status"),
        "processing_status": ready.get("processingStatus") or ready.get("processing_status"),
    }
    session["attachment"] = {
        "document_ids": [document_id],
        "folder_id": None,
        "folder_name": None,
        "documents": [
            {
                "id": document_id,
                "name": upload.get("name") or doc_path.stem,
                "file_url": None,
                "corpus_cache_path": None,
                "status": ready.get("status"),
            }
        ],
    }
    return session


def bootstrap_vault_session(
    *,
    config: PWAConfig | None = None,
    new_chat: bool = True,
    default_intent_key: str = "GENERAL_CHAT",
    document_ids: list[str] | None = None,
    document_names: list[str] | None = None,
    file_urls: list[str] | None = None,
    folder_id: str | None = None,
    folder_name: str | None = None,
    download_corpus: bool = True,
) -> dict[str, Any]:
    """
    Pick existing YourVault document(s) and/or folder — no upload.

    Downloads fileUrl for each resolved document (for case generation corpus),
    attaches scope with document_ids + optional folderId, saves session.json.
    """
    from qa.vault_corpus import (
        build_combined_document_context,
        download_vault_document_text,
    )

    config = config or load_pwa_config()
    client = YourAIPWAClient(config)

    log.info("Phase 1: auth + conversation bootstrap")
    me = client.auth_me()
    conversation_id = client.start_conversation(reuse=not new_chat)
    intents = client.get_intents()
    if not intents:
        log.warning("No intents returned from /knowledge-base/intents")

    log.info("Phase 2: resolve vault attachment")
    vault_docs = client.resolve_vault_documents(
        document_ids=document_ids,
        document_names=document_names,
        file_urls=file_urls,
    )
    folder = client.resolve_vault_folder(folder_id=folder_id, folder_name=folder_name)
    folder_id_resolved = str(folder.get("id")) if folder else None
    folder_name_resolved = (folder or {}).get("name")

    if folder_id_resolved and not vault_docs:
        log.info("No explicit documents — loading READY docs from folder %s", folder_id_resolved)
        folder_docs = client.list_vault_documents(folder_id=folder_id_resolved, limit=100)
        vault_docs = [d for d in folder_docs if document_is_ready(d)]

    if not vault_docs and not folder_id_resolved:
        raise ValueError(
            "bootstrap_vault_session requires at least one vault document or folder "
            "(set VAULT_DOCUMENT_IDS / VAULT_FOLDER_NAME in run_full_pipeline.py)"
        )

    for doc in vault_docs:
        if not document_is_ready(doc):
            raise ValueError(
                f"Vault document {doc.get('id')} is not READY — wait for processing "
                f"(status={doc.get('status')}, processing={doc.get('processingStatus')})"
            )

    doc_ids = [str(d["id"]) for d in vault_docs if d.get("id")]

    log.info("Phase 3: attach vault scope (docs=%s folder=%s)", len(doc_ids), folder_id_resolved or "—")
    client.set_conversation_scope_vault(
        conversation_id,
        document_ids=doc_ids,
        folder_id=folder_id_resolved,
    )

    attachment_docs: list[dict[str, Any]] = []
    corpus_contexts = []
    if download_corpus and vault_docs:
        log.info("Phase 4: download vault corpus for case generation")
        for doc in vault_docs:
            ctx = download_vault_document_text(client, doc)
            corpus_contexts.append(ctx)
            attachment_docs.append(
                {
                    "id": str(doc.get("id")),
                    "name": doc.get("name") or ctx.filename,
                    "file_url": doc.get("fileUrl") or doc.get("file_url"),
                    "corpus_cache_path": ctx.local_path,
                    "status": doc.get("status"),
                }
            )
    else:
        for doc in vault_docs:
            attachment_docs.append(
                {
                    "id": str(doc.get("id")),
                    "name": doc.get("name"),
                    "file_url": doc.get("fileUrl") or doc.get("file_url"),
                    "corpus_cache_path": None,
                    "status": doc.get("status"),
                }
            )

    combined_cache_path = None
    primary_id = doc_ids[0] if doc_ids else None
    if corpus_contexts:
        combined = (
            build_combined_document_context(corpus_contexts)
            if len(corpus_contexts) > 1
            else corpus_contexts[0]
        )
        combined_cache_path = combined.local_path

    session = _session_shell(
        config=config,
        me=me,
        conversation_id=conversation_id,
        new_chat=new_chat,
        intents=intents,
        default_intent_key=default_intent_key,
    )
    session["bootstrap_mode"] = "vault"
    session["attachment"] = {
        "document_ids": doc_ids,
        "folder_id": folder_id_resolved,
        "folder_name": folder_name_resolved,
        "documents": attachment_docs,
    }
    if primary_id:
        primary_meta = vault_docs[0] if vault_docs else {}
        session["document"] = {
            "id": primary_id,
            "name": primary_meta.get("name") or primary_id[:8],
            "local_path": combined_cache_path or (attachment_docs[0].get("corpus_cache_path") if attachment_docs else ""),
            "status": primary_meta.get("status"),
            "processing_status": primary_meta.get("processingStatus"),
        }
    session["corpus"] = {
        "primary_document_id": primary_id,
        "document_ids": doc_ids,
        "combined_cache_path": combined_cache_path,
        "folder_id": folder_id_resolved,
    }
    return session
