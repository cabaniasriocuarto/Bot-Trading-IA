from __future__ import annotations

import os

import uvicorn

from rtlab_core.web.app import app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("rtlab_core.web.main:app", host="0.0.0.0", port=port, log_level="info")
