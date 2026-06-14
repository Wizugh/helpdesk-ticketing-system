param(
    [string]$NewUsername = "NewUser"
)

$date = Get-Date -Format "yyyy-MM-dd HH:mm"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   IT ONBOARDING CHECKLIST" -ForegroundColor Cyan
Write-Host "   User: $NewUsername" -ForegroundColor Cyan
Write-Host "   Date: $date" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$tasks = @(
    "Create user account in Active Directory",
    "Assign user to appropriate security groups",
    "Set up Microsoft 365 account and email",
    "Configure Microsoft Teams access",
    "Install and configure laptop/workstation",
    "Install required software (Office, Zoom, etc.)",
    "Configure VPN access",
    "Set up Multi-Factor Authentication (MFA)",
    "Grant access to shared drives and folders",
    "Send welcome email with login credentials",
    "Schedule IT orientation walkthrough",
    "Confirm user can log in successfully"
)

foreach ($task in $tasks) {
    Write-Host "[ ] $task" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Total tasks: $($tasks.Count)" -ForegroundColor Green
Write-Host "Onboarding checklist generated for: $NewUsername" -ForegroundColor Green
Write-Host "Log saved to: onboarding_$NewUsername`_$($date -replace ':', '-' -replace ' ', '_').txt" -ForegroundColor Green

$output = "Onboarding Checklist for $NewUsername - $date`n"
$output += "="*40 + "`n"
foreach ($task in $tasks) {
    $output += "[ ] $task`n"
}

$filename = "onboarding_$NewUsername`_$($date -replace ':', '-' -replace ' ', '_').txt"
$output | Out-File -FilePath $filename