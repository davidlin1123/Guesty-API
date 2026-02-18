"""
models/tasks.py
All Task-related Guesty API calls.
Docs: https://open-api-docs.guesty.com/reference/get_tasks-open-api-tasks
"""

from typing import Optional
from client import make_request


def get_all(limit: int = 25, skip: int = 0, listing_id: Optional[str] = None) -> dict:
    """
    GET /tasks/open-api/tasks
    Retrieve a list of tasks.
    """
    params = {"limit": limit, "skip": skip}
    if listing_id:
        params["listingId"] = listing_id
    return make_request("GET", "/tasks/open-api/tasks", params=params)


def get_by_id(task_id: str) -> dict:
    """
    GET /tasks/open-api/{taskId}
    Retrieve a specific task.
    """
    return make_request("GET", f"/tasks/open-api/{task_id}")


def create(payload: dict) -> dict:
    """
    POST /tasks/open-api/create-single-task
    Create a new task.

    Example payload:
        {
            "title": "Clean room",
            "listingId": "abc123",
            "scheduledDate": "2026-03-01",
            "assigneeId": "xyz789"
        }
    """
    return make_request("POST", "/tasks/open-api/create-single-task", body=payload)


def update(task_id: str, payload: dict) -> dict:
    """
    PUT /tasks/open-api/{taskId}
    Update an existing task.
    """
    return make_request("PUT", f"/tasks/open-api/{task_id}", body=payload)


def delete(task_id: str) -> dict:
    """
    DELETE /tasks/open-api/{taskId}
    Delete a task.
    """
    return make_request("DELETE", f"/tasks/open-api/{task_id}")
