import json
from dataclasses import dataclass, field
from pathlib import Path

from claude_agent_sdk import get_session_messages
from claude_agent_sdk._internal.sessions import (
    _canonicalize_path,
    _find_project_dir,
    _get_project_dir,
)
from google.cloud import firestore

from medium_claude_sdk_skills_data_agent.core.ports import PersistencePort
from medium_claude_sdk_skills_data_agent.utils.constants import FIRESTORE_MESSAGES_FIELD
from medium_claude_sdk_skills_data_agent.utils.file_paths import FIRESTORE_DATABASE
from medium_claude_sdk_skills_data_agent.utils.helpers import create_logger


@dataclass
class FirestoreSessionStore(PersistencePort):
    """
    Persists Claude Agent SDK checkpoint files in Firestore so that session
    state survives infrastructure scale-to-zero events.

    Documents are organised as:
        collection: <user_id>
        document:   <thread_id>
        field:      messages  (list[dict] — one entry per JSONL line)

    :param project: the GCP project ID
    :param _client: the Firestore Async Client
    """

    project_id: str
    _client: firestore.AsyncClient = field(init=False, repr=False)

    def __post_init__(self):
        self.logger = create_logger(name="FirestoreSessionStore")
        self._client = firestore.AsyncClient(
            project=self.project_id, database=FIRESTORE_DATABASE
        )

    def _return_session_file(self, thread_id: str, checkpoint_dir: str) -> Path:
        """
        Returns the .claude project directory session file path for session

        :param thread_id: the unique session id
        :param checkpoint_dir: the location of the session file
        :returns path to session file
        """
        canonical = _canonicalize_path(checkpoint_dir)
        project_dir = _find_project_dir(project_path=canonical)
        if project_dir is None:
            project_dir = _get_project_dir(project_path=canonical)
            project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir / f"{thread_id}.jsonl"

    async def load_session(self, user_id: str, thread_id: str) -> list[dict] | None:
        """
        Fetches the session state for the given user/session from Firestore

        :param user_id: Firestore collection ID (one collection per user)
        :param thread_id: Firestore document ID within that collection
        :returns list of message dicts if the document exists, else None
        """
        doc_ref = self._client.collection(user_id).document(document_id=thread_id)
        doc = await doc_ref.get()
        if doc.exists:
            messages = doc.get(FIRESTORE_MESSAGES_FIELD)
            self.logger.info(
                f"Session {thread_id} found in Firestore " f"({len(messages)} messages)"
            )
            return messages
        self.logger.info(f"Session {thread_id} not found in Firestore")
        return None

    async def restore_checkpoint(
        self, thread_id: str, checkpoint_dir: str, messages: list[dict]
    ) -> None:
        """
        Serialises the message dicts back to JSONL and writes them to the local
        .claude session file so that the SDK can resume the conversation.

        :param thread_id: the thread ID being restored
        :param checkpoint_dir: the directory for checkpoint files
        :param messages: list of message dicts previously loaded from Firestore
        """
        session_file = self._return_session_file(
            thread_id=thread_id, checkpoint_dir=checkpoint_dir
        )
        session_file.write_text(
            "\n".join(json.dumps(msg) for msg in messages),
            encoding="utf-8",
        )
        self.logger.info(
            f"Session {thread_id} checkpoint restored {len(messages)} messages"
        )

    async def save_session(
        self, user_id: str, thread_id: str, checkpoint_dir: str
    ) -> None:
        """
        Reads the session messages via the SDK (same path resolution used at
        resume time) and persists them to Firestore so that future requests can
        restore the state even after a scale-to-zero event.

        :param user_id: the Firestore collection ID
        :param thread_id: the Firestore document ID
        :param checkpoint_dir: the directory for checkpoint files
        """
        raw_messages = get_session_messages(
            session_id=thread_id, directory=checkpoint_dir
        )
        if not raw_messages:
            self.logger.warning(
                f"Session {thread_id} has no messages; skipping Firestore write"
            )
            return
        messages = [
            {
                "type": m.type,
                "uuid": m.uuid,
                "session_id": m.session_id,
                "message": m.message,
            }
            for m in raw_messages
        ]
        doc_ref = self._client.collection(user_id).document(document_id=thread_id)
        await doc_ref.set(
            document_data={FIRESTORE_MESSAGES_FIELD: messages},
            merge=False,
            timeout=45.0,
        )
        self.logger.info(
            f"Session {thread_id} saved to Firestore ({len(messages)} messages)"
        )

    async def close(self) -> None:
        await self._client.close()
