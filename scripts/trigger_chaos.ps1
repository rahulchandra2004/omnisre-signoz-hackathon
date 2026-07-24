Write-Host "Injecting chaos into buggy_service..." -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/chaos/inject" -Method POST -UseBasicParsing
    Write-Host "Success: $($response.Content)" -ForegroundColor Green
    Write-Host "Traffic on /checkout should now experience high latency and errors." -ForegroundColor Yellow
} catch {
    Write-Host "Failed to inject chaos: $($_.Exception.Message)" -ForegroundColor Red
}
