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

# Get the environment variable and parse it
BACKEND_CORS_ORIGINS: list[str] = parse_cors(os.environ.get("BACKEND_CORS_ORIGINS", ""))

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
