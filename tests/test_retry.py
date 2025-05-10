import pytest
import asyncio
from unittest.mock import patch
from tests.helpers import (
    create_flaky_task_with_retry,
    event_bus,
    log_event_for_test,
    TaskState,
    run,  # Import global run
)


@pytest.mark.asyncio
async def test_flaky_task_succeeds_first_try(capsys):
    """Tests flaky task succeeding on the first attempt."""
    task_flaky_instance = create_flaky_task_with_retry(name="FlakyFirstSuccess")

    logged_events = []
    handler = lambda e: log_event_for_test(e, logged_events)
    event_bus.subscribe(handler)

    with patch("random.random", return_value=0.8):  # Ensure it succeeds
        result = await run(task_flaky_instance)  # Use global run
        assert result == "flaky_success"

    event_bus.unsubscribe(handler)

    # Check that no retry events were logged for this task instance
    # The event structure for "task" might now be the _TaskRunner instance itself.
    # The name comparison should still work.
    retry_events = [
        e
        for e in logged_events
        if e.get("task") == task_flaky_instance and e.get("state") == TaskState.RETRYING
    ]
    assert not retry_events

    # Check console output from log_event_for_test
    captured = capsys.readouterr()
    # Ensure the specific task's retry is not in output
    # This check might be too broad if other tests run concurrently and log.
    # For now, assume isolated or specific enough logging.
    assert (
        f"EVENT: {{'type': 'task', 'task': {task_flaky_instance}, 'state': TaskState.RETRYING"
        not in captured.out
    )


@pytest.mark.asyncio
async def test_flaky_task_succeeds_after_retries(capsys):
    """Tests flaky task succeeding after a few retries."""
    task_flaky_instance = create_flaky_task_with_retry(
        name="FlakyEventualSuccess", max_tries=3
    )

    logged_events = []
    handler = lambda e: log_event_for_test(e, logged_events)
    event_bus.subscribe(handler)

    side_effects = [0.1, 0.8]  # Fail, then Succeed
    with patch("random.random", side_effect=side_effects):
        result = await run(task_flaky_instance)  # Use global run
        assert result == "flaky_success"

    event_bus.unsubscribe(handler)

    retry_events = [
        e
        for e in logged_events
        if e.get("task") == task_flaky_instance and e.get("state") == TaskState.RETRYING
    ]
    assert len(retry_events) == 1

    # capsys check for RETRYING events can be unreliable due to asyncio.create_task timing.
    # Relying on logged_events list is more robust for counting.
    # We can still check if *any* retry printout made it to capsys if desired,
    # but the count from logged_events is the primary truth.
    # captured = capsys.readouterr()
    # if retry_events: # Only check capsys if we expect retries
    #     assert f"'task': {task_flaky_instance!r}, 'state': {TaskState.RETRYING!r}" in captured.out


@pytest.mark.asyncio
async def test_flaky_task_fails_after_all_retries(capsys):
    """Tests flaky task failing after exhausting all retries."""
    max_retries_config = 3  # This is max_tries for backoff
    task_flaky_instance = create_flaky_task_with_retry(
        name="FlakyUltimateFailure", max_tries=max_retries_config
    )

    logged_events = []
    handler = lambda e: log_event_for_test(e, logged_events)
    event_bus.subscribe(handler)

    with patch("random.random", return_value=0.1):  # Always fail
        with pytest.raises(RuntimeError, match="Flaky failure!"):
            await run(task_flaky_instance)  # Use global run

    event_bus.unsubscribe(handler)

    retry_events = [
        e
        for e in logged_events
        if e.get("task") == task_flaky_instance and e.get("state") == TaskState.RETRYING
    ]
    # max_tries = 3 means 1 initial attempt + 2 retries. So 2 RETRYING events.
    assert len(retry_events) == max_retries_config - 1

    # As above, capsys check for counting RETRYING events is less reliable than logged_events.
    # The logged_events check (len(retry_events)) is the primary assertion for the count.
    # captured = capsys.readouterr()
    # retry_event_count_in_output = sum(
    #     1 for line in captured.out.splitlines()
    #     if f"'task': {task_flaky_instance!r}, 'state': {TaskState.RETRYING!r}" in line
    # )
    # assert retry_event_count_in_output == max_retries_config - 1
