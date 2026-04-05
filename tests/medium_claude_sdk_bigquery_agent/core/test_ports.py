import pytest

from medium_claude_sdk_skills_data_agent.core.ports import (
    AgentServicePort,
    BigQueryPort,
)


@pytest.mark.parametrize(
    "sql, expected",
    [
        ("SELECT * FROM t", [{"id": 1}]),
        ("SELECT COUNT(*) FROM t", [{"n": 99}]),
        ("SELECT name FROM t WHERE id = 5", []),
    ],
)
def test_bigquery_port_concrete_execute_query(sql, expected):
    class ConcreteBQPort(BigQueryPort):
        def execute_query(self, _):
            return expected

        async def execute_query_async(self, _):
            return expected

    port = ConcreteBQPort()
    assert isinstance(port, BigQueryPort)
    assert port.execute_query(sql) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql, expected",
    [
        ("SELECT * FROM t", [{"id": 1}]),
        ("SELECT COUNT(*) FROM t", [{"n": 99}]),
        ("SELECT name FROM t WHERE id = 5", []),
    ],
)
async def test_bigquery_port_concrete_execute_query_async(sql, expected):
    class ConcreteBQPort(BigQueryPort):
        def execute_query(self, _):
            return expected

        async def execute_query_async(self, _):
            return expected

    port = ConcreteBQPort()
    assert isinstance(port, BigQueryPort)
    assert await port.execute_query_async(sql) == expected


def test_bigquery_port_is_abstract():
    with pytest.raises(TypeError):
        BigQueryPort()  # type: ignore[abstract]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question, schema, session_id, expected_result",
    [
        ("What are total sales?", "schema_str", "session-1", ("50000", "session-1")),
        ("Top products?", "schema_str", None, ("Product A", "generated-id")),
    ],
)
async def test_agent_service_port_concrete_run(
    question, schema, session_id, expected_result
):
    class ConcreteAgent(AgentServicePort):
        async def run(self, *_, **__):
            return expected_result

    agent = ConcreteAgent()
    assert isinstance(agent, AgentServicePort)
    result = await agent.run(question=question, schema=schema, session_id=session_id)
    assert result == expected_result


def test_agent_service_port_is_abstract():
    with pytest.raises(TypeError):
        AgentServicePort()  # type: ignore[abstract]
