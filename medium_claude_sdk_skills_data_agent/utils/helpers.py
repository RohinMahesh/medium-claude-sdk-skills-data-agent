import json
import logging
import time
from typing import Any

from google.cloud import bigquery


def create_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Creates a logger

    :param name: the name of the logger
    :param level: the logging level
    :returns logger: the logger object
    """
    # Create handler
    logger = logging.getLogger(name=name)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)

    # Add handler
    logger.addHandler(handler)

    # Prevent propogation to any parent loggers
    logger.propagate = False

    # Set the logger level
    logger.setLevel(level)
    return logger


async def get_schema(project_id: str, dataset_id: str, table_id: str) -> str:
    """
    Fetches and formats the BigQuery table schema for use in agent prompts.
    Intended to be called once at application startup.

    :param project_id: GCP project ID
    :param dataset_id: BigQuery dataset ID
    :param table_id: BigQuery table ID
    :returns formatted schema string for the foundation model
    """
    client = bigquery.Client(project=project_id)
    table = client.get_table(f"{project_id}.{dataset_id}.{table_id}")
    _table_prefix = f"{project_id}.{dataset_id}.{table_id}"
    return f"{_table_prefix}\n".join(
        f"- {field.name}: \n Type:{field.field_type}\n Mode: {field.mode}\n Description: {field.description}\n"
        for field in table.schema
    )


def bigquery_poll(
    client: bigquery.Client,
    jid: str,
    jloc: str,
    timeout: int = 100,
    interval: int = 5,
):
    """
    Polls for completion of BigQuery job

    :param client: the BigQuery client
    :param jid: the job id for the submitted BigQuery job
    :param jloc: the location for the submitted BigQuery job
    :param timeout: the maximum time to poll for
    :param interval: the frequency to check for completion
    """
    logger = create_logger(name="bigquery-poll")

    # Start polling
    start = time.time()
    while True:
        elapsed = time.time() - start

        # Check for timeout
        if elapsed > timeout:
            raise TimeoutError(f"Query did not complete in {timeout} seconds")

        # Check for status
        try:
            _current_status = client.get_job(job_id=jid, location=jloc)
            if _current_status.done():
                break
        except Exception as e:
            logger.info(f"Error polling: {e}")

        # Wait before polling agian
        time.sleep(interval)
        logger.info(f"Polling for completion. Elapsed time: {elapsed}")

    _formatted_elapsed = round(elapsed, 2)
    logger.info(f"Completed polling: {_formatted_elapsed} seconds")


def parse_jsonl_session(content: str) -> list[dict[str, Any]]:
    """
    Parses all JSON objects out of a checkpoint string. Uses raw_decode so it
    handles both strict JSONL (one object per line) and the SDK writing multiple
    objects on the same line without a newline separator.

    :param content: raw text content of a JSONL checkpoint file
    :returns list of parsed message dicts
    """
    decoder = json.JSONDecoder()
    messages = []
    pos = 0
    while pos < len(content):
        while pos < len(content) and content[pos].isspace():
            pos += 1
        if pos >= len(content):
            break
        obj, pos = decoder.raw_decode(content, pos)
        messages.append(obj)
    return messages
