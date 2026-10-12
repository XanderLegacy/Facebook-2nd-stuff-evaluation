"""Entry point for python -m evaluator."""

import sys

if len(sys.argv) > 1 and sys.argv[1] in ("api", "serve", "server"):
    # Run API server
    import os
    import uvicorn

    sys.argv.pop(1)  # Remove the api/serve argument
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))

    uvicorn.run("evaluator.api:app", host=host, port=port, reload=True)
else:
    # Run CLI
    from .cli import main

    main()