import os

LLM_MODEL = "gpt-4o-mini"
# must use tmp path
GIT_REPO_PATH = os.environ.get('GIT_REPO_PATH', '/tmp/stack_vm/runtime/')