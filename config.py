import os

LLM_MODEL = "gpt-4o-mini"
# must use tmp path, DO NOT EDIT
GIT_REPO_PATH = os.environ.get('GIT_REPO_PATH', '/tmp/stack_vm/runtime/')
VM_SPEC_PATH = os.path.join(os.getcwd(), "spec.md")