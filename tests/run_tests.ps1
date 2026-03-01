# Test runner script for PC User Statistics integration (Windows)
# Usage: .\run_tests.ps1

$ErrorActionPreference = "Stop"

Write-Host "🧪 Running PC User Statistics Tests" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# Check if pytest is installed
$pytestInstalled = Get-Command pytest -ErrorAction SilentlyContinue
if (-not $pytestInstalled) {
    Write-Host "❌ pytest not found. Installing test requirements..." -ForegroundColor Red
    pip install -r requirements_test.txt
}

Write-Host "📋 Running unit tests..." -ForegroundColor Yellow
pytest tests/test_helpers.py -v

Write-Host ""
Write-Host "🔧 Running integration tests..." -ForegroundColor Yellow
pytest tests/test_init.py -v

Write-Host ""
Write-Host "📊 Generating coverage report..." -ForegroundColor Yellow
pytest --cov=custom_components.pc_user_statistics `
       --cov-report=term-missing `
       --cov-report=html `
       tests/

Write-Host ""
Write-Host "✅ All tests completed!" -ForegroundColor Green
Write-Host ""
Write-Host "📈 Coverage report saved to htmlcov/index.html" -ForegroundColor Cyan
Write-Host "   Open it in your browser to view detailed coverage" -ForegroundColor Cyan