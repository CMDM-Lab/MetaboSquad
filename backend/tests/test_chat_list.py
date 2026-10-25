def test_chat_list_returns_all_threads_newest_first(client, session):
    first = client.post("/api/chat/").json()
    second = client.post("/api/chat/").json()

    res = client.get("/api/chat/")
    assert res.status_code == 200
    thread_ids = [c["thread_id"] for c in res.json()["chats"]]
    assert thread_ids == [second["thread_id"], first["thread_id"]]


def test_chat_list_includes_created_at(client, session):
    """The sidebar's per-row timestamp needs `created_at` on the wire.

    `Chat.created_at` already exists on the table and `list_chat` already
    orders by it; only the `ChatPublic` response model was dropping it on
    the way out. Assert the field survives serialisation and is a real,
    parseable timestamp rather than merely "some string" — a response model
    that renamed the column or emitted the literal string "created_at"
    would still pass a bare key-presence check.
    """
    created = client.post("/api/chat/").json()
    assert "created_at" in created

    res = client.get("/api/chat/")
    assert res.status_code == 200
    [chat] = res.json()["chats"]
    assert chat["thread_id"] == created["thread_id"]
    assert chat["created_at"] == created["created_at"]

    from datetime import datetime
    datetime.fromisoformat(chat["created_at"])
