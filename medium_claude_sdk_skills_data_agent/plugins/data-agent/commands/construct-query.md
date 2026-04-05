# Construct Query

Translate the user question into a valid BigQuery SQL query.

## Steps
1. Review the provided table schema to understand available columns and their types.
2. Identify which columns are relevant to answering the question.
3. Construct an accurate, efficient SQL query that retrieves only the data needed.
4. If the question is ambiguous or lacks sufficient detail, ask the user for clarification rather than guessing.
5. Validate that all referenced columns and table names match the schema exactly.
