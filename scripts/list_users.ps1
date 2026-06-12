$date = Get-Date -Format "yyyy-MM-dd HH:mm"
$csvFile = "users_export_$($date -replace ':', '-' -replace ' ', '_').csv"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   LOCAL USER ACCOUNT REPORT" -ForegroundColor Cyan
Write-Host "   Generated: $date" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$users = Get-LocalUser

$userList = @()

foreach ($user in $users) {
    $status = if ($user.Enabled) { "Active" } else { "Disabled" }
    $lastLogin = if ($user.LastLogon) { $user.LastLogon.ToString("yyyy-MM-dd HH:mm") } else { "Never" }

    if ($user.Enabled) {
        $color = "Green"
    } else {
        $color = "Red"
    }

    Write-Host "User: $($user.Name)" -ForegroundColor $color
    Write-Host "  Status:     $status"
    Write-Host "  Last Login: $lastLogin"
    Write-Host ""

    $userList += [PSCustomObject]@{
        Username  = $user.Name
        Status    = $status
        LastLogin = $lastLogin
        FullName  = $user.FullName
    }
}

$userList | Export-Csv -Path $csvFile -NoTypeInformation
Write-Host "Total users found: $($users.Count)" -ForegroundColor Green
Write-Host "Export saved to: $csvFile" -ForegroundColor Green