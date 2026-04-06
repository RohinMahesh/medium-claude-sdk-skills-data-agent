from abc import ABC, abstractmethod
from typing import Any


class PersistencePort(ABC):
    """
    Outbound port defining the session-state persistence
    """

    @abstractmethod
    async def load_session(self, user_id: str, thread_id: str) -> list[dict] | None:
        """
        Fetches the persisted session state for the given user/session

        :param user_id: logical owner of the session
        :param thread_id: unique session identifier
        :returns list of message dicts if the session exists, else None
        """
        pass

    @abstractmethod
    async def restore_checkpoint(
        self, thread_id: str, checkpoint_dir: str, messages: list[dict]
    ) -> None:
        """
        Writes the loaded session state to the local checkpoint file

        :param thread_id: the thread ID being restored
        :param checkpoint_dir: the directory for checkpoint files
        :param messages: message dicts previously returned by load_session
        """
        pass

    @abstractmethod
    async def save_session(
        self, user_id: str, thread_id: str, checkpoint_dir: str
    ) -> None:
        """
        Reads the latest local checkpoint file and persists to Firestore

        :param user_id: logical owner of the session
        :param thread_id: unique thread identifier
        :param checkpoint_dir: the directory for checkpoint files
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Releases any resources held by the backing Firestore client
        """
        pass


class PluginSyncPort(ABC):
    """
    Outbound port defining the plugin synchronization
    """

    @property
    @abstractmethod
    def skill_names(self) -> list[str]:
        """
        Returns the names of all skills that have been synced

        :returns list of skill names available to the agent
        """
        pass

    @abstractmethod
    def sync(self) -> None:
        """
        Copies all skills and commands from plugins into the working directory
        """
        pass

    @abstractmethod
    def clean(self) -> None:
        """
        Removes all skills and commands that were previously synced
        """
        pass


class BigQueryPort(ABC):
    """
    Outbound port defining the BigQuery execution providing sync/async BigQuery execution
    """

    @abstractmethod
    def execute_query(self, sql: str) -> list[dict[str, Any]]:
        """
        Executes a SQL query synchronously against BigQuery

        :param sql: the SQL query to execute
        :returns list of result rows as dictionaries
        """
        pass

    @abstractmethod
    async def execute_query_async(self, args: dict[str, Any]) -> list:
        """
        Executes a SQL query asynchronously, using the tool-compatible args schema

        :param args: dictionary containing key 'sql' with the query string
        :returns list of result rows
        """
        pass


class AgentServicePort(ABC):
    """
    Inbound port defining the agent orchestration utilizing the Claude SDK agent
    """

    @abstractmethod
    async def run(
        self,
        question: str,
        schema: str,
        user_id: str,
        session_id: str | None = None,
        resume_session: str | None = None,
        checkpoint_dir: str | None = None,
    ) -> tuple[str, str]:
        """
        Runs the agent with the given question

        :param question: the user question to answer
        :param schema: pre-fetched formatted table schema string
        :param user_id: identifier for the user; used as the Firestore collection ID
        :param session_id: optional session ID; generated if not provided
        :param resume_session: optional session ID to resume a prior conversation
        :param checkpoint_dir: optional directory for checkpoint files
        :returns tuple of (result_text, session_id)
        """
        pass
