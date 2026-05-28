def serialize_event(document: dict[str, object]) -> dict[str, object]:
    event = {
        "id": str(document["_id"]),
        "title": document["title"],
        "location": dict(document["location"]),
        "created_at": document["created_at"],
        "created_by": document["created_by"],
        "started_at": document["started_at"],
        "finished_at": document["finished_at"],
    }

    if "category" in document:
        event["category"] = document["category"]
    if "price" in document:
        event["price"] = document["price"]
    if "description" in document:
        event["description"] = document["description"]

    return event
