import os

LLM_MODEL = "gpt-4o"
# LLM_MODEL = "gpt-4o"
# must use tmp path, DO NOT EDIT
GIT_REPO_PATH = os.environ.get('GIT_REPO_PATH', '/tmp/stack_vm/runtime/')
VM_SPEC_PATH = os.path.join(os.getcwd(), "spec.md")

# Load VM_SPEC_CONTENT
try:
    with open(VM_SPEC_PATH, 'r') as file:
        VM_SPEC_CONTENT = file.read()
except FileNotFoundError:
    print(f"Warning: spec.md file not found at {VM_SPEC_PATH}")
    VM_SPEC_CONTENT = ""
