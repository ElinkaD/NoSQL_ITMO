from neo4j.exceptions import Neo4jError

from app.db import StorageUnavailableError, get_neo4j_driver


def run_query(query: str, parameters: dict[str, object]) -> list[dict[str, object]]:
    try:
        with get_neo4j_driver().session() as session:
            return [record.data() for record in session.run(query, parameters)]
    except Neo4jError as exc:
        raise StorageUnavailableError("neo4j") from exc
    except Exception as exc:
        raise StorageUnavailableError("neo4j") from exc
