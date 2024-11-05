import os
from dotenv import load_dotenv
from typing import Annotated, Any
from pydantic import BeforeValidator, AnyUrl

load_dotenv()

def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)

BACKEND_CORS_ORIGINS: Annotated[list[AnyUrl] | str, BeforeValidator(parse_cors)] = (
    []
)

# LLM settings
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")
LLM_MODEL = os.environ.get("LLM_MODEL", "aya-expanse")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

DATABASE_URI = os.environ.get("DATABASE_URI") or os.environ.get(
    "SQLALCHEMY_DATABASE_URI"
)

# Existing settings
# must use tmp path, DO NOT EDIT
GIT_REPO_PATH = os.environ.get("GIT_REPO_PATH", "/tmp/stack_vm/runtime/")
VM_SPEC_PATH = os.path.join(os.getcwd(), "spec.md")
PLAN_EXAMPLE_PATH = os.path.join(os.getcwd(), "plan_example.md")


if not os.path.exists(GIT_REPO_PATH):
    try:
        os.makedirs(GIT_REPO_PATH)
    except Exception as e:
        print(f"Error creating GIT_REPO_PATH: {e}")

# Load VM_SPEC_CONTENT
try:
    with open(VM_SPEC_PATH, "r") as file:
        VM_SPEC_CONTENT = file.read()
    with open(PLAN_EXAMPLE_PATH, "r") as file:
        PLAN_EXAMPLE_CONTENT = file.read()
except FileNotFoundError:
    print(f"Warning: spec.md file not found at {VM_SPEC_PATH}")
    VM_SPEC_CONTENT = ""
