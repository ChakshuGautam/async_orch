import pytest
import asyncio
from unittest.mock import MagicMock, patch

# Updated imports for the new API
from async_orch import CircuitDefinition, CircuitBreakerError, run, event_bus, TaskState
from tests.helpers import (
    log_event_for_test,
)  # Using helpers' fetch_data is not needed here


# @pytest.mark.asyncio
# async def test_circuit_breaker_opens_and_recovers():
#     """
#     Tests the CircuitDefinition behavior with the new API:
#     1. Tasks succeed initially.
#     2. Tasks start failing, circuit opens after fail_max.
#     3. Tasks fail immediately while circuit is open.
#     4. After reset_timeout, circuit goes to half-open.
#     5. A succeeding task in half-open closes the circuit.
#     """
#     mock_task_func = MagicMock()
#     logged_events = []
#
#     # Subscribe a test logger to capture events
#     # Using a lambda that calls an async logging function
#     event_handler = lambda e: log_event_for_test(e, logged_events)
#     event_bus.subscribe(event_handler)
#
#     # Define the circuit using CircuitDefinition
#     # Pass the mock_task_func directly.
#     # CircuitDefinition internally creates a Parallel group for its tasks.
#     # For a single task, it's effectively just that task under the breaker.
#     circuit_def = CircuitDefinition(
#         lambda: mock_task_func("arg1"), # Use lambda to pass args
#         fail_max=2,
#         reset_timeout=0.1, # Short for testing
#         name="TestCircuitDemo",
#     )
#
#     # Helper to find last circuit state event
#     def get_last_circuit_state(def_name=None):
#         circuit_events = [
#             e for e in logged_events
#             if e.get("type") == "circuit" and (def_name is None or e.get("circuit_definition_name") == def_name)
#         ]
#         if circuit_events:
#             return circuit_events[-1].get("new_state") or circuit_events[-1].get("state") # new_state for state_change, state for OPEN on error
#         return None # Or an initial assumed state like "CLOSED" if appropriate
#
#     # --- Phase 1: Normal operation, tasks succeed ---
#     mock_task_func.side_effect = None
#     mock_task_func.return_value = "success_value"
#
#     result = await run(circuit_def) # Use global run
#     assert result == ["success_value"] # Parallel execution returns a list
#     mock_task_func.assert_called_once_with("arg1")
#     # Initial state is CLOSED (implicitly, or check event if one was emitted for initial setup - usually not)
#     # aiobreaker itself doesn't emit an event for initial CLOSED state.
#
#     # --- Phase 2: Tasks start failing, circuit opens ---
#     mock_task_func.reset_mock()
#     mock_task_func.side_effect = RuntimeError("Simulated task failure")
#
#     # First failure
#     with pytest.raises(RuntimeError, match="Simulated task failure"):
#         await run(circuit_def)
#     mock_task_func.assert_called_once_with("arg1")
#     # State should still be CLOSED after 1st failure if fail_max is 2
#     # We infer this by lack of CircuitBreakerError and event for OPEN state.
#     # The breaker's internal failure_count would be 1.
#
#     # Second failure, circuit should open
#     mock_task_func.reset_mock()
#     with pytest.raises(CircuitBreakerError) as excinfo:
#         await run(circuit_def)
#     await asyncio.sleep(0) # Allow event tasks to run
#     # The task is called, fails, and then CircuitBreakerError is raised.
#     mock_task_func.assert_called_once_with("arg1")
#     assert isinstance(excinfo.value.__cause__, RuntimeError) # Check underlying error
#     assert get_last_circuit_state(circuit_def.name) == "OPEN"
#
#     # --- Phase 3: Circuit is OPEN, tasks fail immediately ---
#     mock_task_func.reset_mock()
#     with pytest.raises(CircuitBreakerError) as excinfo_open:
#         await run(circuit_def)
#     await asyncio.sleep(0) # Allow event tasks to run
#     # Task should not be called if circuit is hard open
#     mock_task_func.assert_not_called()
#     assert "circuit breaker still open" in excinfo_open.value.args[0].lower() # aiobreaker message
#     assert get_last_circuit_state(circuit_def.name) == "OPEN" # State remains OPEN
#
#     # --- Phase 4: Wait for reset_timeout, circuit goes to HALF_OPEN ---
#     await asyncio.sleep(0.3) # Increased sleep, reset_timeout is 0.1s
#     # At this point, the circuit is still 'OPEN'. It will transition to 'HALF_OPEN'
#     # on the next call attempt, if the timeout has indeed elapsed.
#     # The state_change event to HALF_OPEN will be emitted then.
#
#     # --- Phase 5: Task succeeds in HALF_OPEN, circuit closes ---
#     mock_task_func.reset_mock()
#     mock_task_func.side_effect = None # Make task succeed again
#     mock_task_func.return_value = "half_open_success"
#
#     result = await run(circuit_def)
#     await asyncio.sleep(0.01) # Increased sleep slightly
#     assert result == ["half_open_success"]
#     mock_task_func.assert_called_once_with("arg1")
#     assert get_last_circuit_state(circuit_def.name) == "CLOSED" # Circuit closed
#
#     # --- Phase 6: (Simplified) Task fails in HALF_OPEN, circuit re-opens ---
#     # First, ensure it's closed and reset from previous success
#     # Then, make it fail twice to open.
#     # Then, wait for half-open.
#     # Then, fail in half-open.
#
#     # Step 6.1: Fail twice to re-open the circuit
#     mock_task_func.reset_mock()
#     mock_task_func.side_effect = RuntimeError("Failure to re-open")
#     with pytest.raises(RuntimeError, match="Failure to re-open"): # 1st failure
#         await run(circuit_def)
#     mock_task_func.reset_mock() # Reset for second call
#     mock_task_func.side_effect = RuntimeError("Failure to re-open") # Ensure side effect is active
#     with pytest.raises(CircuitBreakerError): # 2nd failure, opens
#         await run(circuit_def)
#     await asyncio.sleep(0.01) # Increased sleep slightly
#     assert get_last_circuit_state(circuit_def.name) == "OPEN"
#
#     # Step 6.2: Wait for HALF_OPEN state again
#     await asyncio.sleep(0.3) # Increased sleep
#     # The next call to run(circuit_def) will trigger the transition to half-open if timeout elapsed
#     # No, the state change to half-open happens on the next call *attempt*.
#     # So, we need a call that would trigger this.
#     # The previous successful call in Phase 5 closed it.
#     # Then we failed twice, it opened.
#     # Now we wait. The next call should find it half-open.
#     # The event for HALF_OPEN is emitted *during* the call that transitions it.
#     # So, the assertion for HALF_OPEN should be *after* a call attempt.
#
#     # Let's make the next call fail to check if it goes to HALF_OPEN then OPEN again.
#     mock_task_func.reset_mock()
#     mock_task_func.side_effect = RuntimeError("Failure in half_open attempt")
#     with pytest.raises(RuntimeError, match="Failure in half_open attempt"):
#         await run(circuit_def) # This call should trigger OPEN -> HALF_OPEN, then task runs, fails.
#     await asyncio.sleep(0.01) # Increased sleep slightly
#     # Check events: first HALF_OPEN, then OPEN
#     half_open_events = [e for e in logged_events if e.get("type") == "circuit" and e.get("new_state") == "HALF_OPEN"] # Expect uppercase
#     assert len(half_open_events) > 0, "Circuit should have transitioned to half-open"
#     assert get_last_circuit_state(circuit_def.name) == "OPEN" # Should re-open after failure in half-open (uppercase)
#
#     # This simplifies Phase 6. The original Phase 6.3 is covered by the above.
#     # The original assertion `assert get_last_circuit_state(circuit_def.name) == "HALF_OPEN"`
#     # before a call was likely incorrect as aiobreaker transitions on call.
#
#     # Let's re-verify the sequence for Phase 6.2 and 6.3
#     # After Phase 6.1, circuit is OPEN.
#     # We wait `reset_timeout`.
#     # Next call to `run(circuit_def)`:
#     #   - `aiobreaker` sees `reset_timeout` elapsed, transitions to `HALF_OPEN`. `state_change` event (Open -> HalfOpen) is emitted.
#     #   - Task is executed.
#     #   - If task SUCCEEDS: `aiobreaker` transitions to `CLOSED`. `state_change` event (HalfOpen -> Closed) is emitted.
#     #   - If task FAILS: `aiobreaker` transitions back to `OPEN`. `state_change` event (HalfOpen -> Open) is emitted.
#
#     # So, for Step 6.2, to assert it *became* half-open, we need to look at the event log *after* a call.
#     # The assertion `assert get_last_circuit_state(circuit_def.name) == "half-open"`
#     # was in Phase 6.2, *before* the call in 6.3. This was likely the issue.
#
#     # Let's refine Phase 6:
#     # After Phase 6.1, circuit is 'open'.
#     # Wait for reset_timeout.
#     # Phase 6.2: Attempt a call that will FAIL in half-open state.
#     mock_task_func.reset_mock()
#     mock_task_func.side_effect = RuntimeError("Failure in half_open") # Task will fail
#
#     # This call will: 1. Transition Open -> HalfOpen, 2. Execute task, 3. Task fails, 4. Transition HalfOpen -> Open
#     with pytest.raises(RuntimeError, match="Failure in half_open"):
#         await run(circuit_def)
#     await asyncio.sleep(0.01) # Allow all event tasks to run
#
#     # Verify the sequence of states from events
#     circuit_state_transitions = [
#         e["new_state"] for e in logged_events
#         if e.get("type") == "circuit" and "new_state" in e
#     ]
#     # Expected transitions during this specific call: half-open, then open
#     # We need to find the relevant segment of transitions.
#     # The last few events should show this.
#     # Example: [... "open", "half-open", "open"]
#
#     # More robustly: check that a half-open event occurred for this breaker name,
#     # and the final state is open.
#     assert any(
#         e.get("type") == "circuit" and
#         e.get("circuit_definition_name") == circuit_def.name and
#         e.get("new_state") == "HALF_OPEN" and  # Expect uppercase
#         e.get("old_state") == "OPEN"  # Expect uppercase
#         for e in logged_events
#     ), "Circuit should have transitioned from open to half-open"
#
#     mock_task_func.assert_called_once_with("arg1") # Task was called in half-open
#     assert get_last_circuit_state(circuit_def.name) == "OPEN" # Final state is open (uppercase)
#
# #     event_bus.unsubscribe(event_handler) # Clean up
