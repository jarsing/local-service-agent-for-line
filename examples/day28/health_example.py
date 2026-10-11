"""Local FastAPI teaching example; it does not diagnose the deployed service."""
from fastapi import FastAPI
from fastapi.testclient import TestClient


def add_health(app: FastAPI) -> None:
    @app.get('/healthz')
    async def healthz():
        return {'status': 'ok'}


def reproduce() -> dict:
    decorated_app = FastAPI()
    add_health(decorated_app)
    wrong_export = FastAPI()
    correct_export = decorated_app
    mounted_app = FastAPI()
    mounted_app.mount('/api', decorated_app)
    with TestClient(wrong_export) as wrong, TestClient(correct_export) as correct, TestClient(mounted_app) as mounted:
        return {
            'scope': 'LOCAL_SYNTHETIC_FASTAPI_EXAMPLE',
            'wrong_export_health': wrong.get('/healthz').status_code,
            'correct_export_health': correct.get('/healthz').status_code,
            'mounted_root_health': mounted.get('/healthz').status_code,
            'mounted_prefixed_health': mounted.get('/api/healthz').status_code,
            'external_calls': 0,
            'production_root_cause': 'UNCONFIRMED',
        }


if __name__ == '__main__':
    import json
    print(json.dumps(reproduce(), indent=2))
