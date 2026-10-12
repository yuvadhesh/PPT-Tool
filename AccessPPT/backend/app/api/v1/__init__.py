from fastapi import APIRouter
from app.api.v1 import auth, presentations, issues, jobs, dashboard, equations

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(presentations.router)
api_router.include_router(issues.router)
api_router.include_router(jobs.router)
api_router.include_router(dashboard.router)
api_router.include_router(equations.router)
