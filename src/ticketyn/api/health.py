from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get('/api/system/version')
def system_version(request: Request, response: Response) -> dict[str, str]:
    response.headers['Cache-Control'] = 'no-store'
    return {'version': request.app.version}
