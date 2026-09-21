import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    ENV: str = os.getenv("ENV", "dev")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENABLE_LANGGRAPH: bool = os.getenv("ENABLE_LANGGRAPH", "false").lower() == "true"
    ENABLE_CONNECTORS: bool = os.getenv("ENABLE_CONNECTORS", "false").lower() == "true"

settings = Settings()
