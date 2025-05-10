import pytest
from async_orch import TaskRunner, Parallel
from tests.helpers import fetch_data

@pytest.mark.asyncio
async def test_simple_parallel_execution():
    """
    Tests parallel execution of tasks.
    Corresponds to example_simple_parallel.
    """
    parallel_flow = Parallel(
        TaskRunner(fetch_data, 10, name="Fetch10"),
        TaskRunner(fetch_data, 20, name="Fetch20"),
        TaskRunner(fetch_data, 30, name="Fetch30"),
        limit=2, # As in original example
        name="TestSimpleParallel"
    )
    results = await parallel_flow.run()

    assert len(results) == 3
    expected_results = ["data_10", "data_20", "data_30"]
    # Results from Parallel might not be in order, so check for presence
    for item in expected_results:
        assert item in results
    
    # To check if limit=2 was respected, we'd need to inspect timing or events,
    # which is more complex. For now, this test focuses on correctness of results.

@pytest.mark.asyncio
async def test_parallel_with_empty_tasks():
    """Tests Parallel flow with no tasks."""
    parallel_flow = Parallel(name="TestEmptyParallel")
    results = await parallel_flow.run()
    assert results == []

@pytest.mark.asyncio
async def test_parallel_with_one_task():
    """Tests Parallel flow with a single task."""
    parallel_flow = Parallel(
        TaskRunner(fetch_data, 1, name="FetchSingle"),
        name="TestSingleTaskParallel"
    )
    results = await parallel_flow.run()
    assert results == ["data_1"]
