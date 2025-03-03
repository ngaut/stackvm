import os
from dotenv import load_dotenv
from typing import Any
import json

load_dotenv()


def parse_cors(v: Any) -> list[str]:
    if isinstance(v, str):
        # If the string is not a JSON list, split by commas
        if not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        # If it's a JSON list, parse it
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid format for CORS origins: {v}")
    elif isinstance(v, list):
        return v
    raise ValueError(f"Invalid type for CORS origins: {type(v)}")


TASK_QUEUE_WORKERS: int = 20
# in seconds
TASK_QUEUE_TIMEOUT: int = 600

# Get the environment variable and parse it
BACKEND_CORS_ORIGINS: list[str] = parse_cors(os.environ.get("BACKEND_CORS_ORIGINS", ""))

# LLM settings
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")
LLM_MODEL = os.environ.get("LLM_MODEL", "aya-expanse")

# Reasoning model settings (fallback to legacy settings if not set)
REASON_LLM_PROVIDER = os.environ.get("REASON_LLM_PROVIDER", None)
REASON_LLM_MODEL = os.environ.get("REASON_LLM_MODEL", None)
if REASON_LLM_PROVIDER is None or REASON_LLM_MODEL is None:
    REASON_LLM_PROVIDER = LLM_PROVIDER
    REASON_LLM_MODEL = LLM_MODEL

# Evaluation model settings (fallback to legacy settings if not set)
EVALUATION_LLM_PROVIDER = os.environ.get("EVALUATION_LLM_PROVIDER", None)
EVALUATION_LLM_MODEL = os.environ.get("EVALUATION_LLM_MODEL", None)
if EVALUATION_LLM_PROVIDER is None or EVALUATION_LLM_MODEL is None:
    EVALUATION_LLM_PROVIDER = LLM_PROVIDER
    EVALUATION_LLM_MODEL = LLM_MODEL

# Common LLM provider settings
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

DATABASE_URI = os.environ.get("DATABASE_URI") or os.environ.get(
    "SQLALCHEMY_DATABASE_URI"
)
SESSION_POOL_SIZE: int = os.environ.get("SESSION_POOL_SIZE", 40)

# Get project root directory
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# Update path definitions to use PROJECT_ROOT
VM_SPEC_PATH = os.path.join(PROJECT_ROOT, "spec.md")
PLAN_EXAMPLE_PATH = os.path.join(PROJECT_ROOT, "plan_example.md")
GIT_REPO_PATH = os.environ.get("GIT_REPO_PATH", "/tmp/stack_vm/runtime/")
GENERATED_FILES_DIR = os.environ.get("GENERATED_FILES_DIR", "/tmp/stack_vm/generated/")

if not os.path.exists(GIT_REPO_PATH):
    try:
        os.makedirs(GIT_REPO_PATH)
    except Exception as e:
        print(f"Error creating GIT_REPO_PATH: {e}")

if not os.path.exists(GENERATED_FILES_DIR):
    try:
        os.makedirs(GENERATED_FILES_DIR)
    except Exception as e:
        print(f"Error creating GENERATED_FILES_DIR: {e}")

# Load VM_SPEC_CONTENT
try:
    with open(VM_SPEC_PATH, "r") as file:
        VM_SPEC_CONTENT = file.read()
    with open(PLAN_EXAMPLE_PATH, "r") as file:
        PLAN_EXAMPLE_CONTENT = file.read()
except FileNotFoundError:
    print(f"Warning: spec.md file not found at {VM_SPEC_PATH}")
    VM_SPEC_CONTENT = ""


# Model configurations
def parse_model_configs() -> dict:
    """Parse MODEL_CONFIGS from environment variable"""
    config_str = os.environ.get("MODEL_CONFIGS", "{}")
    try:
        return json.loads(config_str)
    except json.JSONDecodeError:
        print(f"Warning: Invalid MODEL_CONFIGS format: {config_str}")
        return {}


MODEL_CONFIGS = parse_model_configs()
