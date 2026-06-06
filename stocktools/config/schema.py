CONFIG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS model_config (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    base_url    TEXT    NOT NULL,
    api_key     TEXT    NOT NULL,
    model_name  TEXT    NOT NULL
);
"""

