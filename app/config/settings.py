import os
from dotenv import load_dotenv

load_dotenv()

LLM_MODEL = os.environ.get('LLM_MODEL', 'gpt-4o-mini')
# must use tmp path, DO NOT EDIT
GIT_REPO_PATH = os.environ.get('GIT_REPO_PATH', '/tmp/stack_vm/runtime/')
VM_SPEC_PATH = os.path.join(os.getcwd(), "spec.md")
PLAN_EXAMPLE_PATH = os.path.join(os.getcwd(), "plan_example.md")
TOOLS_INSTRUCTION_PATH = os.path.join(os.getcwd(), "tools_instruction.md")

# Load VM_SPEC_CONTENT
try:
    with open(VM_SPEC_PATH, 'r') as file:
        VM_SPEC_CONTENT = file.read()
    with open(PLAN_EXAMPLE_PATH, 'r') as file:
        PLAN_EXAMPLE_CONTENT = file.read()
    with open(TOOLS_INSTRUCTION_PATH, 'r') as file:
        TOOLS_INSTRUCTION_CONTENT = file.read()
except FileNotFoundError:
    print(f"Warning: spec.md file not found at {VM_SPEC_PATH}")
    VM_SPEC_CONTENT = ""
