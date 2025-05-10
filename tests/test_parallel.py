import pytest
from async_orch import Parallel, run  # Import global run
from tests.helpers import fetch_data


@pytest.mark.asyncio
async def test_simple_parallel_execution():
    """
    Tests parallel execution of tasks using the new definition API.
    """
    # Define parallel tasks using raw functions (or lambdas for arguments)
    parallel_def = Parallel(
        lambda: fetch_data(10),
        lambda: fetch_data(20),
        lambda: fetch_data(30),
        max_workers=2,
        name="TestSimpleParallel",
    )
    # Execute using the global run function
    results = await run(parallel_def)

    assert len(results) == 3
    expected_results = ["data_10", "data_20", "data_30"]
    for item in expected_results:
        assert item in results


@pytest.mark.asyncio
async def test_parallel_with_empty_tasks():
    """Tests Parallel flow with no tasks using the new definition API."""
    empty_parallel_def = Parallel(name="TestEmptyParallel")
    results = await run(empty_parallel_def)
    assert results == []


@pytest.mark.asyncio
async def test_parallel_with_one_task():
    """Tests Parallel flow with a single task using the new definition API."""
    single_task_parallel_def = Parallel(
        lambda: fetch_data(1), name="TestSingleTaskParallel"  # Use lambda for args
    )
    results = await run(single_task_parallel_def)
    # Parallel always returns a list of results, even for one task.
    assert results == ["data_1"]
