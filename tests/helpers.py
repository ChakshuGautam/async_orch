import asyncio
import random
import backoff
from async_orch import TaskRunner, Sequence, Parallel, CircuitGroup, event_bus as global_event_bus, TaskState

# --- Event Bus and Logging (Test-Friendly) --------------------------------
# Provide the global event_bus instance from async_orch
event_bus = global_event_bus

async def log_event_for_test(event, log_list=None):
    """
    Logs events to console and optionally to a list for assertions.
    Made async as per wiki.md suggestion for event_bus.
    """
    output = f"EVENT: {event}"
    print(output)
    if log_list is not None:
        log_list.append(event)

# --- Task Definitions (from original examples) -----------------------------
# 1. Simple I/O Task: fetch data (simulated)
async def fetch_data(id):
    await asyncio.sleep(0.01) # Reduced sleep for faster tests
    return f"data_{id}"

# 2. CPU-bound-like Task: process data (sync)
def process_data(data):
    # pretend heavy compute
    return data.upper()

# 3. Save data task
def save_data(processed_data):
    # In tests, we'll usually capture this with capsys or mock it.
    if isinstance(processed_data, list):
        print(f"Saved: {processed_data}")
        return processed_data
    else:
        print(f"Saved: {processed_data}")
        return processed_data

# 4. Failing Task for Retry Demo
def flaky_task_func():
    if random.random() < 0.7: # Original threshold
        raise RuntimeError("Flaky failure!")
    return "flaky_success"

# Helper to create a flaky task with retry policy
def create_flaky_task_with_retry(name="FlakyTaskWithRetry", max_tries=3):
    task_flaky = TaskRunner(flaky_task_func, name=name)

    # Monkey-patch retry policy (as in original example)
    def retry_policy_for_task(fn_to_wrap, task_instance):
        async def on_backoff_handler(details):
            await event_bus.emit({
                "type": "task",
                "task": task_instance,
                "state": TaskState.RETRYING,
                **details
            })
        
        @backoff.on_exception(
            backoff.expo, Exception, max_tries=max_tries,
            on_backoff=lambda details: asyncio.create_task(on_backoff_handler(details))
        )
        async def wrapped_execute_with_policies(): 
            return await fn_to_wrap() 

        return wrapped_execute_with_policies

    original_execute_policies = task_flaky._execute_with_policies
    # Ensure the original_execute_policies is callable (it's an async method)
    async def callable_original_execute_policies():
        return await original_execute_policies()

    task_flaky._execute_with_policies = retry_policy_for_task(callable_original_execute_policies, task_flaky)
    return task_flaky
