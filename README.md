# async_orch: Asynchronous Task Pipelines

[![PyPI version](https://badge.fury.io/py/async_orch.svg)](https://badge.fury.io/py/async_orch)
[![codecov](https://codecov.io/gh/ChakshuGautam/async_orch/graph/badge.svg?token=Q9L3VBK3G5)](https://codecov.io/gh/ChakshuGautam/async_orch)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

`async_orch` is a Python library designed for building and managing asynchronous task pipelines. It provides a flexible framework to define individual tasks, sequence them, run them in parallel with concurrency controls, and apply resilience patterns like circuit breakers. The library is built on `asyncio` (Python 3.11+) to handle non-blocking operations efficiently.

## Key Features

- **Asynchronous by Design**: Leverages `asyncio` for efficient I/O-bound operations and concurrency.
- **Composability**: Build complex workflows by nesting `TaskRunner`, `Sequence`, `Parallel`, and `CircuitGroup` components.
- **State Management & Observability**: A global `EventBus` allows for monitoring TaskRunner states and circuit breaker events.
- **Resilience Patterns**: Includes `CircuitGroup` for circuit breaker functionality (using `aiobreaker`).
- **Extensible Policies**: Customize TaskRunner execution with retry mechanisms or other strategies (e.g., using `backoff` as shown in examples).

## Installation

You can install `async_orch` using pip:

```bash
pip install async_orch
```

Requires Python 3.11 or newer.

## Quick Start

Here's a simple example of defining and running a sequence of tasks:

```python
import asyncio
from async_orch import TaskRunner, Sequence, run

# Define some tasks
async def fetch_user_data(user_id: int) -> dict:
    print(f"Fetching data for user {user_id}...")
    await asyncio.sleep(0.1) # Simulate I/O
    return {"id": user_id, "name": f"User {user_id}", "status": "active"}

def process_user_data(data: dict) -> dict:
    print(f"Processing data for {data['name']}...")
    data["processed"] = True
    return data

async def notify_user(data: dict):
    print(f"Notifying {data['name']} about processing completion...")
    await asyncio.sleep(0.05) # Simulate I/O
    print(f"Notification sent for {data['name']}.")

# Create a pipeline
user_pipeline = Sequence(
    TaskRunner(fetch_user_data, 101, name="FetchUserData"),
    TaskRunner(process_user_data, name="ProcessUserData"), # Takes output from previous task
    TaskRunner(notify_user, name="NotifyUser")            # Takes output from previous task
)

async def main():
    print("Starting user pipeline...")
    results = await run(user_pipeline)
    print("\nPipeline completed.")
    if results and len(results) > 1:
        final_data = results[1] # Result from process_user_data
        print(f"Final processed data from pipeline: {final_data}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Documentation

For detailed information on all components, advanced usage, and more examples, please refer to the [**async_orch Wiki**](docs/wiki.md).

The wiki covers:

- Core Components: `TaskRunner`, `EventBus`, `Sequence`, `Parallel`, `CircuitGroup`, `TaskState`.
- Advanced Patterns: Implementing retries, using the event bus for logging.
- Codebase structure and how to run the bundled examples.

## Examples

The `examples/` directory contains scripts demonstrating various features of `async_orch`. You can run them directly:

## Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
