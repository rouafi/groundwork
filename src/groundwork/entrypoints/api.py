"""HTTP entrypoint."""

from fastapi import FastAPI

app = FastAPI(title="groundwork")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
