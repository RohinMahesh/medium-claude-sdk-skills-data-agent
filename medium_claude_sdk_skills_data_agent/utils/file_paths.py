import os
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKPOINT_DIR = os.path.join(BASE_DIR, ".claude")
PLUGINS_DIR = Path(BASE_DIR) / "plugins"
CLAUDE_DIR = Path(BASE_DIR).parent / ".claude"
DATASET_ID = "tableau_sample_datasets"
TABLE_ID = "superstore_sales"
BQ_LOCATION = "us-central1"
FIRESTORE_DATABASE = "claude-skills-data-agent"
