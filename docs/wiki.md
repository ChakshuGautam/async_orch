# async_orch Wiki

## 1. Introduction

`async_orch` is a Python library designed for building and managing asynchronous task pipelines. It provides a flexible framework to define individual tasks, sequence them, run them in parallel with concurrency controls, and apply resilience patterns like circuit breakers. The library is built on `asyncio` to handle non-blocking operations efficiently.

## 2. Core Components & Concepts

The library revolves around a few key components:

- **`Task`**: The fundamental unit of work.

  - It can wrap both synchronous (`def`) and asynchronous (`async def`) functions.
  - Each task maintains its state, tracked by the `TaskState` enum (`PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `RETRYING`, `CANCELLED`).
  - State transitions and results/errors are typically communicated via the `EventBus`.

- **`EventBus`**:

  - A global publish-subscribe mechanism.
  - Tasks, CircuitGroups, and other components emit events (e.g., state changes, errors, results) to this bus.
  - Allows for decoupled monitoring, logging, or other reactions to workflow events.

- **`Sequence`**:

  - A composite task that executes a series of steps (Tasks, other Sequences, or Parallels) one after another.
  - If any step fails, the sequence typically stops and propagates the error.
  - Returns an ordered list of results from each successfully completed step.

- **`Parallel`**:

  - A composite task that executes multiple jobs (Tasks, Sequences, or other Parallels) concurrently.
  - Supports an optional `limit` parameter to control the maximum number of jobs running at the same time.
  - Waits for all jobs to complete and returns a list of their results. The order of results corresponds to the order of jobs defined.

- **`CircuitGroup`**:

  - A specialized composite that wraps one or more tasks with a circuit breaker pattern, utilizing the `aiobreaker` library.
  - Helps prevent repeated calls to services or tasks that are failing.
  - Monitors failures and "opens" the circuit if the failure threshold (`fail_max`) is reached within a certain time, preventing further calls for a `reset_timeout` period.
  - Emits events for circuit state changes (e.g., `OPEN`, `CLOSED`, `HALF_OPEN`).

- **`TaskState`**:
  - An `Enum` defining the possible lifecycle states of a `Task`:
    - `PENDING`: Task is created but not yet started.
    - `RUNNING`: Task is currently executing.
    - `SUCCEEDED`: Task completed successfully.
    - `FAILED`: Task terminated with an error.
    - `RETRYING`: Task failed and is being retried (often part of a custom retry policy).
    - `CANCELLED`: Task execution was cancelled.

## 3. Key Features

- **Asynchronous by Design**: Built on Python's `asyncio` library, enabling efficient handling of I/O-bound operations and concurrent task execution.
- **Composability**: Tasks and composite structures (`Sequence`, `Parallel`, `CircuitGroup`) can be nested to create complex and sophisticated workflows.
- **State Management & Observability**: The `EventBus` provides a centralized way to monitor the state and progress of tasks and circuit breakers, facilitating logging, metrics collection, and real-time feedback.
- **Extensible Execution Policies**: The `Task._execute_with_policies` method is designed to be overridden or monkey-patched. This allows for the integration of custom behaviors such as retry mechanisms (as demonstrated in `examples/example.py` using the `backoff` library) or other advanced execution strategies.

## 4. How to Use (Illustrated with examples from `examples/example.py`)

### Defining Basic Tasks

Tasks can wrap either asynchronous or synchronous functions.

```python
# From examples/example.py
from async_orch import Task
import asyncio

# Asynchronous task
async def fetch_data(id):
    await asyncio.sleep(0.5)
    return f"data_{id}"

task_fetch = Task(fetch_data, 1)

# Synchronous task
def process_data(data):
    return data.upper()

task_process = Task(process_data, "some_data")
```

### Creating a `Sequence`

Execute tasks one after another.

```python
# From examples/example.py
from async_orch import Task, Sequence, event_bus, TaskState # Assuming fetch_data, process_data, save_data are defined
# ... (fetch_data, process_data, save_data definitions) ...

nested_pipeline = Sequence(
    Task(fetch_data, 1, name="Fetch1"),
    Task(process_data, name="Process1"), # process_data is sync
    Task(save_data, name="Save1"),      # save_data is sync
    name="NestedPipeline"
)

# To run:
# await nested_pipeline.run()
```

### Creating a `Parallel` Execution

Execute tasks concurrently, optionally limiting concurrency.

```python
# From examples/example.py
from async_orch import Task, Parallel # Assuming fetch_data is defined
# ... (fetch_data definition) ...

results = await Parallel(
    Task(fetch_data, 10),
    Task(fetch_data, 20),
    Task(fetch_data, 30),
    limit=2, # Optional: Max 2 tasks run at once
    name="SimpleParallel"
).run()
# results will be: ['data_10', 'data_20', 'data_30'] (order maintained)
```

### Implementing Retries

The `Task._execute_with_policies` method can be enhanced for retries. `examples/example.py` demonstrates this by monkey-patching with the `backoff` library.

```python
# From examples/example.py (simplified)
from async_orch import Task, TaskState, event_bus # Assuming flaky_task is defined
import backoff
import asyncio

# ... (flaky_task definition) ...
task_flaky = Task(flaky_task, name="Flaky")

def retry_policy(fn_to_wrap, task_instance):
    async def on_backoff_handler(details):
        await event_bus.emit({
            "type": "task",
            "task": task_instance,
            "state": TaskState.RETRYING,
            **details
        })

    # This wraps the original _execute_with_policies method
    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        on_backoff=lambda details: asyncio.create_task(on_backoff_handler(details))
    )
    async def wrapped_execute_with_policies():
        return await fn_to_wrap() # Calls the original method logic

    return wrapped_execute_with_policies

# Apply the retry policy
original_execute_policies = task_flaky._execute_with_policies
task_flaky._execute_with_policies = retry_policy(original_execute_policies, task_flaky)


# To run:
# try:
#     result = await task_flaky.run()
# except Exception as e:
#     print(f"Flaky task ultimately failed: {e}")
```

### Using `CircuitGroup`

Protect your system from cascading failures.

```python
# From examples/example.py
from async_orch import Task, CircuitGroup # Assuming fetch_data, process_data are defined
# ... (fetch_data, process_data definitions) ...

breaker_group = CircuitGroup(
    Task(fetch_data, 2, name="Fetch2"),
    Task(process_data, name="Process2"), # Assuming process_data can also fail
    fail_max=2,        # Open circuit after 2 failures
    reset_timeout=10,  # Try to close circuit after 10 seconds
    name="CircuitDemo"
)

# To run:
# from aiobreaker import CircuitBreakerError # Import for catching specific error
# try:
#     await breaker_group.run()
# except CircuitBreakerError as e:
#     print(f"Circuit breaker triggered: {e}")
# except Exception as e:
#     print(f"Other error in breaker group: {e}")

```

### Subscribing to the `EventBus`

Monitor task and circuit events.

```python
# From examples/example.py
from async_orch import event_bus # Assuming TaskState is also imported if used in event
import asyncio

async def log_event(event): # Made async to match EventBus.emit
    print(f"EVENT: {event}")

# Subscribe the logger
# The lambda creates an asyncio.create_task for fire-and-forget
event_bus.subscribe(lambda e: asyncio.create_task(log_event(e)))
```

When a task changes state, an event like this might be emitted:
`{'type': 'task', 'task': <Task Fetch1>, 'state': TaskState.RUNNING}`
`{'type': 'task', 'task': <Task Fetch1>, 'state': TaskState.SUCCEEDED, 'result': 'data_1'}`

For circuit breakers:
`{'type': 'circuit', 'circuit': <CircuitGroup CircuitDemo>, 'old_state': <CircuitBreakerState.CLOSED: 'closed'>, 'new_state': <CircuitBreakerState.OPEN: 'open'>}`

### Top-level Runner

The `async_orch.run()` function provides a convenient way to execute any top-level task, sequence, parallel group, or circuit group.

```python
import async_orch

# Assuming 'my_main_workflow' is a Task, Sequence, Parallel, or CircuitGroup instance
# await async_orch.run(my_main_workflow)
```

## 5. Codebase Structure

- **`async_orch/__init__.py`**: This file contains the core framework classes:

  - `EventBus`: Manages event subscriptions and emissions.
  - `TaskState`: Enum for task lifecycle states.
  - `Task`: The basic execution unit.
  - `Sequence`: For sequential execution of tasks.
  - `Parallel`: For concurrent execution of tasks.
  - `CircuitGroup`: Implements the circuit breaker pattern for a group of tasks.
  - `run()`: A top-level convenience function to execute any workflow component.

- **`examples/example.py`**: This file provides practical usage examples of the `async_orch` library. It demonstrates:
  - Defining various types of tasks (I/O-bound, CPU-bound-like).
  - Constructing sequences and parallel groups.
  - Implementing a retry mechanism for a flaky task.
  - Using a circuit breaker.
  - Subscribing to the event bus for logging.
  - Running a mixed pipeline of sequences and parallel groups.

## 6. Running the Examples

To see the `async_orch` library in action, you can run the `examples/example.py` script:

```bash
python examples/example.py
```

This will execute all the defined examples and print event logs and results to the console.
