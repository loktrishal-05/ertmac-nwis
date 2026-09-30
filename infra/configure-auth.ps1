# One-step setup for real email codes (Gmail) and Google sign-in on the local NWIS stack.
# Run from any folder:  powershell -ExecutionPolicy Bypass -File "<path>\infra\configure-auth.ps1"
# Secrets are typed hidden and written only to infra\.env (git-ignored). Nothing is sent anywhere else.
$ErrorActionPreference = 'Stop'
$envFile = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $PSScriptRoot 'nwis-auth.env.example') $envFile }
$utf8 = New-Object System.Text.UTF8Encoding $false   # no BOM, so docker compose reads the first line correctly

function Set-EnvValue([string]$key, [string]$value) {
  $lines = [System.Collections.Generic.List[string]]([System.IO.File]::ReadAllLines($envFile))
  $index = $lines.FindIndex([Predicate[string]]{ param($l) $l -match "^$([regex]::Escape($key))=" })
  if ($index -ge 0) { $lines[$index] = "$key=$value" } else { $lines.Add("$key=$value") }
  [System.IO.File]::WriteAllLines($envFile, $lines, $utf8)
}
function Read-Secret([string]$prompt) {
  $secure = Read-Host $prompt -AsSecureString
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

# The OTP / Google features need a server secret; create one if missing.
$current = [System.IO.File]::ReadAllText($envFile)
if ($current -notmatch '(?m)^NWIS_AUTH_SECRET=\S{32,}') {
  $bytes = New-Object byte[] 48; [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  Set-EnvValue 'NWIS_AUTH_SECRET' ([Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_'))
}

Write-Host "`n1) Real email codes through Gmail" -ForegroundColor Cyan
Write-Host "   Needs a Gmail App Password: https://myaccount.google.com/apppasswords (2-Step Verification must be on)."
$gmail = Read-Host '   Gmail address that will send the codes (Enter to skip)'
if ($gmail) {
  $appPassword = (Read-Secret '   16-letter App Password (hidden; spaces are fine)') -replace '\s', ''
  if ($appPassword.Length -ne 16) { throw 'An App Password has exactly 16 letters. Nothing was changed for email.' }
  Set-EnvValue 'NWIS_SMTP_HOST' 'smtp.gmail.com'
  Set-EnvValue 'NWIS_SMTP_PORT' '587'
  Set-EnvValue 'NWIS_SMTP_TLS' 'starttls'
  Set-EnvValue 'NWIS_SMTP_USERNAME' $gmail
  Set-EnvValue 'NWIS_SMTP_PASSWORD' $appPassword
  Set-EnvValue 'NWIS_SMTP_SENDER' "`"eRTMAC-NWIS <$gmail>`""
  Write-Host '   Gmail delivery configured.' -ForegroundColor Green
}

Write-Host "`n2) Google sign-in" -ForegroundColor Cyan
Write-Host '   Google Cloud Console > APIs & Services > Credentials > Create OAuth client ID > Web application.'
Write-Host '   Authorized JavaScript origin: http://localhost:3000'
Write-Host '   Authorized redirect URI:      http://localhost:3000/api/auth/google/callback'
$clientId = Read-Host '   OAuth Client ID (Enter to skip)'
if ($clientId) {
  $clientSecret = Read-Secret '   OAuth Client secret (hidden)'
  if (-not $clientSecret) { throw 'The client secret is required. Nothing was changed for Google.' }
  Set-EnvValue 'NWIS_GOOGLE_ENABLED' 'true'
  Set-EnvValue 'NWIS_GOOGLE_CLIENT_ID' $clientId.Trim()
  Set-EnvValue 'NWIS_GOOGLE_CLIENT_SECRET' $clientSecret.Trim()
  Set-EnvValue 'NWIS_GOOGLE_CALLBACK_URL' 'http://localhost:3000/api/auth/google/callback'
  Set-EnvValue 'NWIS_AUTH_FRONTEND_ORIGIN' 'http://localhost:3000'
  Write-Host '   Google sign-in configured. Open the app at http://localhost:3000 (not 127.0.0.1).' -ForegroundColor Green
}

Write-Host "`nRestarting the NWIS backend..." -ForegroundColor Cyan
docker compose -f (Join-Path $PSScriptRoot 'docker-compose.nwis.yml') up -d | Out-Host
for ($i = 0; $i -lt 40; $i++) { try { $caps = Invoke-RestMethod 'http://127.0.0.1:8011/auth/capabilities' -TimeoutSec 3; break } catch { Start-Sleep 1 } }
if (-not $caps) { throw 'The backend did not come back; run: docker compose -f infra\docker-compose.nwis.yml logs backend' }
Write-Host ("Email delivery: {0}   Google sign-in: {1}" -f $caps.email_delivery, $caps.google) -ForegroundColor Green
if ($gmail -and $caps.email_delivery -ne 'smtp') { Write-Host 'Email is not using Gmail yet - check the values above.' -ForegroundColor Yellow }
if ($clientId -and -not $caps.google) { Write-Host 'Google sign-in is not active - check the client ID/secret.' -ForegroundColor Yellow }
