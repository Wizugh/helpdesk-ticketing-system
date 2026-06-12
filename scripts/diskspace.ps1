$date = Get-Date -Format "yyyy-MM-dd HH:mm"
$logFile = "diskspace_log_$($date -replace ':', '-' -replace ' ', '_').txt"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   DISK SPACE REPORT" -ForegroundColor Cyan
Write-Host "   Generated: $date" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$output = "Disk Space Report - $date`n"
$output += "="*40 + "`n"

$drives = Get-PSDrive -PSProvider FileSystem

foreach ($drive in $drives) {
    if ($drive.Used -ne $null -and $drive.Free -ne $null) {
        $totalGB = [math]::Round(($drive.Used + $drive.Free) / 1GB, 2)
        $usedGB = [math]::Round($drive.Used / 1GB, 2)
        $freeGB = [math]::Round($drive.Free / 1GB, 2)
        $percentUsed = [math]::Round(($drive.Used / ($drive.Used + $drive.Free)) * 100, 1)

        if ($percentUsed -ge 80) {
            $color = "Red"
            $warning = " *** WARNING: Low disk space ***"
        } elseif ($percentUsed -ge 60) {
            $color = "Yellow"
            $warning = " * Monitor this drive"
        } else {
            $color = "Green"
            $warning = ""
        }

        Write-Host "Drive $($drive.Name):" -ForegroundColor $color
        Write-Host "  Total:  $totalGB GB"
        Write-Host "  Used:   $usedGB GB ($percentUsed% used)$warning" -ForegroundColor $color
        Write-Host "  Free:   $freeGB GB"
        Write-Host ""

        $output += "Drive $($drive.Name): Total=$totalGB GB | Used=$usedGB GB ($percentUsed%) | Free=$freeGB GB$warning`n"
    }
}

$output | Out-File -FilePath $logFile
Write-Host "Report saved to: $logFile" -ForegroundColor Green