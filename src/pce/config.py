from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PCE_", env_file=".env", extra="ignore")

    db_path: Path = Path("data/pce.db")
    data_dir: Path = Path("data")
    watch_dirs: list[str] = []
    watch_extensions: list[str] = [".py", ".md", ".txt", ".ts", ".js", ".json", ".yaml", ".yml", ".toml", ".rst"]

    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_batch_size: int = 32
    chunk_size: int = 400       # tokens
    chunk_overlap: int = 64     # tokens

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # Route to cloud only when local can't handle it
    llm_backend: str = "ollama"   # "ollama" | "anthropic"

    retrieval_top_k: int = 10
    retrieval_fts_weight: float = 1.0
    retrieval_vec_weight: float = 1.0

    port: int = 8766
    log_level: str = "INFO"


settings = Settings()
