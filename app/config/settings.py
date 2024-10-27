import os
from dotenv import load_dotenv

load_dotenv()

# LLM settings
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")
LLM_MODEL = os.environ.get("LLM_MODEL", "aya-expanse")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

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
