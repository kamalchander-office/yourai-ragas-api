"""Bootstrap a full PWA QA session: chat + upload + scope + intents."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yourai_pwa.client import YourAIPWAClient
from yourai_pwa.config import PWAConfig, load_pwa_config
from yourai_pwa.intents import intent_by_key

log = logging.getLogger(__name__)


def bootstrap_qa_session(
    document_path: Path,
    *,
    config: PWAConfig | None = None,
    new_chat: bool = True,
    document_name: str | None = None,
    default_intent_key: str = "GENERAL_CHAT",
) -> dict[str, Any]:
    """
    Run PWA automation recipe (QA only):
      auth/me → conversations/start → intents → upload → poll → scope
    """
    config = config or load_pwa_config()
    client = YourAIPWAClient(config)
    doc_path = Path(document_path).expanduser().resolve()

    log.info("Phase 1: auth + conversation bootstrap")
    me = client.auth_me()
    user_id = str(me.get("id") or me.get("userId") or me.get("sub") or "")
    org_id = str(me.get("orgId") or me.get("org") or me.get("organizationId") or "")
    role = me.get("role")

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

    default_intent = intent_by_key(intents, default_intent_key) or (intents[0] if intents else None)

    session = {
        "spec_version": "1.0",
        "environment": "qa",
        "base_url": config.base_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "org_id": org_id,
        "role": role,
        "conversation_id": conversation_id,
        "new_chat": new_chat,
        "document": {
            "id": document_id,
            "name": upload.get("name") or doc_path.stem,
            "local_path": str(doc_path),
            "status": ready.get("status"),
            "processing_status": ready.get("processingStatus") or ready.get("processing_status"),
        },
        "intents": intents,
        "default_intent_key": default_intent_key,
        "default_intent_id": (default_intent or {}).get("id", ""),
    }
    return session
