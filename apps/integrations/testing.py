from __future__ import annotations

import random
import time
from typing import Any, Dict


def run_mock_integration_test(integration, parameters: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Simulate an integration test execution."""

    time.sleep(0.01)
    success = True
    response_data = {
        "status": 200,
        "body": {
            "message": "Mock integration executed.",
            "parameters": parameters or {},
        },
        "mappings": {mapping["key"]: f"mock-{random.randint(100,999)}" for mapping in integration.response_mappings},
        "durationMs": random.randint(50, 300),
    }
    return {"success": success, "result": response_data}

