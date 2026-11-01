import asyncio

import uvicorn

if __name__ == "__main__":
    # Windows ProactorEventLoop hard-fails its listener when a client aborts
    # mid-accept (WinError 64); the selector loop recovers instead of taking
    # the whole server offline.
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
