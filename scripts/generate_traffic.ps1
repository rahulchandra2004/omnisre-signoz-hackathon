Write-Host "Starting traffic generation for /checkout endpoint..."
Write-Host "Press Ctrl+C to stop."

while ($true) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/checkout" -Method GET -UseBasicParsing
        Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] Status: $($response.StatusCode)"
    } catch {
        Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] Error: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Red
    }
    Start-Sleep -Seconds 1
}
