# AccessPPT Local Development Launcher
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "          Starting AccessPPT Services" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$baseDir = Join-Path $PSScriptRoot "AccessPPT"

Write-Host "[1/2] Launching Backend API (FastAPI on http://127.0.0.1:8000)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$baseDir\backend'; & '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

Write-Host "[2/2] Launching Frontend Web App (Next.js on http://localhost:3000)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$baseDir\frontend'; npm run dev"

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "AccessPPT is starting up!" -ForegroundColor Yellow
Write-Host "  Frontend : http://localhost:3000" -ForegroundColor White
Write-Host "  API Docs : http://127.0.0.1:8000/api/docs" -ForegroundColor White
Write-Host "  Demo User: demo@accessppt.com / Password123!" -ForegroundColor White
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

Start-Sleep -Seconds 3
Start-Process "http://localhost:3000"
