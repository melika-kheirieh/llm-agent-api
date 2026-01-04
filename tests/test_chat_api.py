def test_chat_success(client, override_agent_ok):
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 200
    assert resp.json()["response"] == "echo: hello"


def test_chat_empty_message(client, override_agent_ok):
    resp = client.post("/chat", json={"message": "   "})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "message is required"


def test_chat_llm_failure(client, override_agent_llm_error):
    resp = client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 502
    assert resp.json()["detail"] == "LLM failure"

def test_chat_persists(mocker, client, override_agent_ok):
    spy = mocker.patch("app.api.routes.save_chat")
    client.post("/chat", json={"message": "hi"})
    spy.assert_called_once()

