import pytest
import asyncio
from unittest.mock import patch
from tests.helpers import create_flaky_task_with_retry, event_bus, log_event_for_test, TaskState

@pytest.mark.asyncio
async def test_flaky_task_succeeds_first_try(capsys):
    """Tests flaky task succeeding on the first attempt."""
    task_flaky = create_flaky_task_with_retry(name="FlakyFirstSuccess")
    
    # Subscribe a test logger to capture events
    logged_events = []
    # It's important to manage subscriptions carefully if event_bus is global.
    # For isolated tests, a fresh event_bus or specific subscription handling is needed.
    # Here, we assume basic subscription for simplicity.
    handler = lambda e: log_event_for_test(e, logged_events) # Returns a coroutine
    event_bus.subscribe(handler)

    with patch('random.random', return_value=0.8): # Ensure it succeeds (random > 0.7)
        result = await task_flaky.run()
        assert result == "flaky_success"
    
    event_bus.unsubscribe(handler) # Clean up subscription

    # Check that no retry events were logged for this task
    retry_events = [e for e in logged_events if e.get("task") == task_flaky and e.get("state") == TaskState.RETRYING]
    assert not retry_events
    
    captured = capsys.readouterr() # Check console output from log_event_for_test
    assert "RETRYING" not in captured.out # Assuming log_event_for_test prints RETRYING for such states

@pytest.mark.asyncio
async def test_flaky_task_succeeds_after_retries(capsys):
    """Tests flaky task succeeding after a few retries."""
    task_flaky = create_flaky_task_with_retry(name="FlakyEventualSuccess", max_tries=3)
    
    logged_events = []
    handler = lambda e: log_event_for_test(e, logged_events) # Returns a coroutine
    event_bus.subscribe(handler)

    # Mock random.random to fail, then succeed
    side_effects = [0.1, 0.8] # Fail (random < 0.7), then Succeed (random > 0.7)
    with patch('random.random', side_effect=side_effects):
        result = await task_flaky.run()
        assert result == "flaky_success"

    event_bus.unsubscribe(handler)

    retry_events = [e for e in logged_events if e.get("task") == task_flaky and e.get("state") == TaskState.RETRYING]
    assert len(retry_events) == 1 # Should have retried once
    
    captured = capsys.readouterr()
    # Check for retry event in console output
    assert "RETRYING" in captured.out

@pytest.mark.asyncio
async def test_flaky_task_fails_after_all_retries(capsys):
    """Tests flaky task failing after exhausting all retries."""
    max_retries = 3
    task_flaky = create_flaky_task_with_retry(name="FlakyUltimateFailure", max_tries=max_retries)

    logged_events = []
    handler = lambda e: log_event_for_test(e, logged_events) # Returns a coroutine
    event_bus.subscribe(handler)

    # Mock random.random to always fail
    with patch('random.random', return_value=0.1): # Always fail
        with pytest.raises(RuntimeError, match="Flaky failure!"):
            await task_flaky.run()
            
    event_bus.unsubscribe(handler)

    retry_events = [e for e in logged_events if e.get("task") == task_flaky and e.get("state") == TaskState.RETRYING]
    # max_tries = 3 means 1 initial attempt + 2 retries. So 2 RETRYING events.
    assert len(retry_events) == max_retries - 1
    
    captured = capsys.readouterr()
    # Check for retry event in console output
    assert captured.out.count("RETRYING") == max_retries - 1
