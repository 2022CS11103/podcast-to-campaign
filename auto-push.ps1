Write-Host "🚀 Auto Git Push Started..."

while ($true) {

    git add .

    git diff --cached --quiet

    if ($LASTEXITCODE -ne 0) {

        $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

        git commit -m "autosave: $time"

        git push origin main

        if ($LASTEXITCODE -ne 0) {
            Write-Host "⚠️ Remote changed. Syncing..."
            git pull --rebase origin main

            if ($LASTEXITCODE -eq 0) {
                git push origin main
            }
        }

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ GitHub updated at $time"
        }
    }

    Start-Sleep -Seconds 30
}