"""Project model-version contracts for supported PIG generations."""

WORKBENCH_MODEL_VERSION = "workbench-v1"
PROJECT_CONTEXT_MODEL_VERSION = "project-context-v2.1"
CURRENT_PROJECT_MODEL_VERSION = PROJECT_CONTEXT_MODEL_VERSION


def is_current_project_model(model_version: str) -> bool:
    return model_version == CURRENT_PROJECT_MODEL_VERSION
