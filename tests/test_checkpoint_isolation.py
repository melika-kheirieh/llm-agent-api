from app.agent.checkpoints import CheckpointStore, ContextCheckpoint


def test_checkpoint_isolation_by_thread():
    store = CheckpointStore()
    store.save(ContextCheckpoint(thread_id="a", state={"tenant": "one"}))

    assert store.load("a").state["tenant"] == "one"
    assert store.load("b") is None
