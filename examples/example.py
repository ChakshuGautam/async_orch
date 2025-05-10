from async_orch import TaskRunner, Sequence, Parallel, CircuitGroup, event_bus, TaskState
import asyncio

# Subscribe a simple logger to event bus
async def log_event(event): # Made async as per wiki.md suggestion for event_bus
    print(f"EVENT: {event}")

event_bus.subscribe(lambda e: asyncio.create_task(log_event(e)))

# --- Task Definitions -----------------------------------------------------
# 1. Simple I/O Task: fetch data (simulated)
async def fetch_data(id):
    await asyncio.sleep(0.5)
    return f"data_{id}"

# 2. CPU-bound-like Task: process data (sync)
def process_data(data):
    # pretend heavy compute
    return data.upper()

# 3. Nested Pipeline Task: load, process, and save
def save_data(processed):
    print(f"Saved: {processed}")

nested_pipeline = Sequence(
    TaskRunner(fetch_data, 1, name="Fetch1"),
    TaskRunner(process_data, name="Process1"),
    TaskRunner(save_data, name="Save1"),
    name="NestedPipeline"
)

# 4. Failing Task for Retry Demo
def flaky_task():
    import random
    if random.random() < 0.7:
        raise RuntimeError("Flaky failure!")
    return "flaky_success"

task_flaky = TaskRunner(flaky_task, name="Flaky")
# Monkey-patch retry policy
import backoff
from async_orch import TaskState # Corrected import
def retry_policy(fn_to_wrap, task_instance): # Added task_instance for better event emitting
    async def on_backoff_handler(details):
        await event_bus.emit({
            "type":"task",
            "task": task_instance, # Use task_instance
            "state":TaskState.RETRYING,
            **details
        })
    
    @backoff.on_exception(
        backoff.expo, Exception, max_tries=3,
        on_backoff=lambda details: asyncio.create_task(on_backoff_handler(details))
    )
    async def wrapped_execute_with_policies(): 
        return await fn_to_wrap() 

    return wrapped_execute_with_policies

original_execute_policies = task_flaky._execute_with_policies
task_flaky._execute_with_policies = retry_policy(original_execute_policies, task_flaky)


# 5. Circuit Breaker Group Demo
breaker_group = CircuitGroup(
    TaskRunner(fetch_data, 2, name="Fetch2"),
    TaskRunner(process_data, name="Process2"),
    fail_max=2, reset_timeout=10,
    name="CircuitDemo"
)

# --- Examples -------------------------------------------------------------
async def example_simple_parallel():
    print("Example 1: Simple Parallel Execution")
    results = await Parallel(
        TaskRunner(fetch_data, 10),
        TaskRunner(fetch_data, 20),
        TaskRunner(fetch_data, 30),
        limit=2,
        name="SimpleParallel"
    ).run()
    print("Results:", results)

async def example_nested_sequence():
    print("Example 2: Nested Sequence (pipeline)")
    await nested_pipeline.run()

async def example_retry_flaky():
    print("Example 3: Retry on Flaky Task")
    try:
        result = await task_flaky.run()
        print("Flaky result:", result)
    except Exception as e:
        print("Flaky ultimately failed", e)

async def example_circuit_breaker():
    print("Example 4: Circuit Breaker Demo")
    for i in range(5):
        try:
            print(f"Circuit attempt {i+1}")
            await breaker_group.run()
            print("Circuit group succeeded.") 
        except Exception as e:
            print(f"Circuit attempt {i+1} failed: {e}")
            if "OPEN" in str(e) or "CircuitBreakerError" in str(e.__class__): 
                 print("Circuit is OPEN.")
        await asyncio.sleep(1)


async def example_mixed_pipeline():
    print("Example 5: Mixed Sequence & Parallel")
    
    pipeline = Sequence(
        TaskRunner(fetch_data, 100, name="Fetch100"), 
        Parallel(
            TaskRunner(process_data, "alpha", name="ProcessAlpha"),
            TaskRunner(process_data, "beta", name="ProcessBeta"),
            name="ProcessParallel"
        ),
        TaskRunner(save_data, "Mixed pipeline processed data saved.", name="SaveMixedSummary"),
        name="MixedPipeline"
    )
    await pipeline.run()

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
