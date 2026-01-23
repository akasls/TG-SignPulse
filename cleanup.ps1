
Write-Host "Starting aggressive cleanup..."

# Kill Node
$node = Get-Process node -ErrorAction SilentlyContinue
if ($node) {
    Write-Host "Killing $($node.Count) Node processes..."
    Stop-Process -Name node -Force -ErrorAction SilentlyContinue
}

# Kill Python
$python = Get-Process python -ErrorAction SilentlyContinue
if ($python) {
    Write-Host "Killing $($python.Count) Python processes..."
    Stop-Process -Name python -Force -ErrorAction SilentlyContinue
}

# Wait for locks to release
Start-Sleep -Seconds 3

# Check Port 8000
$netstat = netstat -ano | findstr :8000
if ($netstat) {
    Write-Host "WARNING: Port 8000 still in use!"
    Write-Host $netstat
    # Parse PID and kill?
    # For now just warn
} else {
    Write-Host "Port 8000 is free."
}

Write-Host "Cleanup complete."
