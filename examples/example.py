from async_orch import (
    Sequence,
    Parallel,
    CircuitDefinition,
    event_bus,
    TaskState,
    run,  # Import the global run function
    # _TaskRunner no longer needed for examples
)
import asyncio
import backoff  # Keep for retry example


# Subscribe a simple logger to event bus
async def log_event(event):
    # For task events, 'task' is an internal _TaskRunner instance.
    # We can try to get its configured name for better logging.
    if event.get("type") == "task" and hasattr(event.get("task"), "name"):
        event_copy = event.copy()
        event_copy["task_name"] = event["task"].name
        del event_copy["task"]  # Remove the object itself for cleaner log
        print(f"EVENT: {event_copy}")
    else:
        print(f"EVENT: {event}")


# Ensure event_bus.subscribe is called correctly
# The lambda now directly calls the async log_event
event_bus.subscribe(lambda e: asyncio.create_task(log_event(e)))


# --- Task Definitions (Functions) -----------------------------------------
# 1. Simple I/O Task: fetch data (simulated)
async def fetch_data(id_val):  # Renamed id to id_val to avoid conflict with built-in
    await asyncio.sleep(0.5)
    return f"data_{id_val}"


# 2. CPU-bound-like Task: process data (sync)
def process_data(data):
    return data.upper()


# 3. Task for saving data
def save_data(processed_data):  # Renamed processed to processed_data
    print(f"Saved: {processed_data}")


# --- Composed Definitions -------------------------------------------------

# Nested Pipeline Definition
# Users now define sequences with raw functions or other definitions.
# Names for individual function steps can be set on _TaskRunner if needed,
# but the primary API encourages naming the Sequence/Parallel/CircuitDefinition.
nested_pipeline_def = Sequence(
    lambda: fetch_data(1),  # Use lambdas or functools.partial for args
    process_data,
    save_data,
    name="NestedPipeline",
)


# Flaky Task for Retry Demo
def flaky_task():
    import random

    if random.random() < 0.7:
        raise RuntimeError("Flaky failure!")
    return "flaky_success"


# Flaky Task for Retry Demo
# Original flaky_task definition remains the same.
# The retry logic is now applied directly via a decorator.


async def on_retry_handler(details):
    """Event handler for backoff to log retries."""
    # We don't have a direct _TaskRunner instance here in the new API style.
    # The event_bus will log RUNNING, FAILED states from the internal runner.
    # This handler is specific to backoff's retry attempt.
    print(
        f"BACKOFF: Retrying {details['target'].__name__} "
        f"after {details['tries']} tries, "
        f"sleeping {details['wait']:.2f}s. "
        f"Error: {details['exception']}"
    )
    # If we want to emit a TaskState.RETRYING event, we'd need more context
    # or a way to signal the internal runner. For now, simple print.


@backoff.on_exception(
    backoff.expo,
    Exception,  # Catch all exceptions for retry
    max_tries=3,
    on_backoff=on_retry_handler,  # Pass the async handler directly
)
async def flaky_task_with_retry():  # Renamed to reflect it's already wrapped
    import random

    if random.random() < 0.7:
        raise RuntimeError("Flaky failure!")
    return "flaky_success_from_decorated_task"


# Circuit Breaker Definition
# Define tasks to be run under circuit breaker.
# CircuitDefinition internally runs its tasks as a Parallel group.
# These tasks will run in parallel. If one fails repeatedly, the circuit opens for all.
circuit_def_final = CircuitDefinition(
    lambda: fetch_data(21),  # task 1 for circuit
    lambda: fetch_data(22),  # task 2 for circuit
    name="CircuitDemo",
    fail_max=2,
    reset_timeout=10,
)


# --- Examples -------------------------------------------------------------
async def example_simple_parallel():
    print("Example 1: Simple Parallel Execution")
    # Define parallel tasks using raw functions (or lambdas for arguments)
    parallel_def = Parallel(
        lambda: fetch_data(10),
        lambda: fetch_data(20),
        lambda: fetch_data(30),
        max_workers=2,
        name="SimpleParallel",
    )
    results = await run(parallel_def)  # Use the global run function
    print("Results:", results)


async def example_nested_sequence():
    print("Example 2: Nested Sequence (pipeline)")
    # nested_pipeline_def is already defined
    await run(nested_pipeline_def)  # Use the global run function


async def example_retry_flaky():
    print("Example 3: Retry on Flaky Task (using decorated function)")
    # Define a sequence using the decorated flaky_task_with_retry
    retry_def = Sequence(flaky_task_with_retry, name="FlakyTaskSequence")
    try:
        result = await run(retry_def)
        print("Flaky task with retry result:", result)
    except Exception as e:
        print("Flaky task with retry ultimately failed:", e)


async def example_circuit_breaker():
    print("Example 4: Circuit Breaker Demo")
    # circuit_def_final is the definition
    for i in range(5):
        try:
            print(f"Circuit attempt {i+1}")
            # Run the CircuitDefinition
            await run(circuit_def_final)
            print("Circuit group succeeded.")
        except Exception as e:
            print(f"Circuit attempt {i+1} failed: {e}")
            # Check for CircuitBreakerError specifically if possible
            # The event bus will also log state changes.
            if "OPEN" in str(e) or "CircuitBreakerError" in str(e.__class__.__name__):
                print("Circuit is OPEN.")
        await asyncio.sleep(1)


async def example_mixed_pipeline():
    print("Example 5: Mixed Sequence & Parallel")

    # Define the mixed pipeline using Sequence and Parallel definitions
    mixed_pipeline_def = Sequence(
        lambda: fetch_data(100),
        Parallel(
            lambda: process_data(
                "alpha_from_mixed"
            ),  # Needs input or be self-contained
            lambda: process_data("beta_from_mixed"),  # Needs input or be self-contained
            name="ProcessParallelMixed",
        ),
        # The save_data function expects input.
        # The Parallel block above returns a list of results.
        # We need to adapt how save_data is called or what it receives.
        # For simplicity, let's assume save_data can handle a list or we modify it.
        # Or, more realistically, one might process the list from Parallel before saving.
        # Let's make a simple summary save.
        lambda results_list: save_data(f"Mixed pipeline summary: {results_list}"),
        name="MixedPipeline",
    )
    await run(mixed_pipeline_def)


# --- Run All Examples -----------------------------------------------------
async def main():
    await example_simple_parallel()
    print("-" * 30)
    await example_nested_sequence()
    print("-" * 30)
    await example_retry_flaky()
    print("-" * 30)
    await example_circuit_breaker()
    print("-" * 30)
    await example_mixed_pipeline()


if __name__ == "__main__":
    asyncio.run(main())
