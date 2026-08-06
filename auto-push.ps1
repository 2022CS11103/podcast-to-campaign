Write-Host "🚀 Auto Git Push Started..."

while ($true) {

    git add .

    git diff --cached --quiet

    if ($LASTEXITCODE -ne 0) {

        $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

        git commit -m "Auto update $time"

        git push origin main

        Write-Host "✅ Pushed at $time"
    }

    Start-Sleep -Seconds 10
}