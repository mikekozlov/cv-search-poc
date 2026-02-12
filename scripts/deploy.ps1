 <#
.SYNOPSIS
    Deploy current project to the Azure VM in one step.

.DESCRIPTION
    1. Creates a deployment zip from the project files
    2. Uploads it to the VM via scp
    3. Unzips and runs deploy-vm.sh on the VM

.EXAMPLE
    .\scripts\deploy.ps1
    .\scripts\deploy.ps1 -VmIp 10.0.0.1
    .\scripts\deploy.ps1 -SkipBuild   # only restart containers, no rebuild
#>
param(
    [string]$VmIp = "20.55.80.228",
    [string]$KeyPath = (Join-Path $env:USERPROFILE 'Downloads\cvsearch-vm_key.pem'),
    [string]$VmUser = "azureuser",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ZipName = "cv-search-poc.zip"
$ZipPath = Join-Path $ProjectRoot $ZipName
$RemoteHome = "/home/$VmUser"
$RemoteApp = "/opt/cvsearch"

# --- Helpers ---
function Log($msg) { Write-Host "[deploy] $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "[deploy] ERROR: $msg" -ForegroundColor Red; exit 1 }

function Invoke-Ssh {
    param([string]$Command)
    ssh -i $KeyPath "$VmUser@$VmIp" $Command
    if ($LASTEXITCODE -ne 0) { Fail "SSH command failed: $Command" }
}

# --- Validate ---
if (-not (Test-Path $KeyPath)) { Fail "SSH key not found: $KeyPath" }

# --- Step 0: Write BUILD_COMMIT ---
$commitHash = (git rev-parse --short HEAD).Trim()
Set-Content -Path (Join-Path $ProjectRoot "BUILD_COMMIT") -Value $commitHash -NoNewline
Log "Commit hash: $commitHash"

# --- Step 1: Create zip ---
Log "Creating deployment zip..."
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

$items = @(
    "src", "data", "scripts", "docker",
    "Dockerfile", ".dockerignore", "docker-compose.yml",
    "pyproject.toml", "api_server.py", "main.py", "README.md",
    "BUILD_COMMIT"
)
# Include .env.production if it exists
if (Test-Path (Join-Path $ProjectRoot ".env.production")) {
    $items += ".env.production"
}

$fullPaths = $items | ForEach-Object { Join-Path $ProjectRoot $_ } | Where-Object { Test-Path $_ }
Compress-Archive -Path $fullPaths -DestinationPath $ZipPath -Force
$sizeMB = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
Log "Zip created: $ZipName ($sizeMB MB)"

# --- Step 2: Upload ---
Log "Uploading to $VmUser@${VmIp}..."
scp -i $KeyPath $ZipPath "$VmUser@${VmIp}:$RemoteHome/"
if ($LASTEXITCODE -ne 0) { Fail "scp upload failed" }
Log "Upload complete."

# --- Step 3: Unzip on VM ---
Log "Unzipping on VM..."
Invoke-Ssh "sudo apt-get install -y -qq unzip > /dev/null 2>&1; rm -rf $RemoteHome/cv-search-poc; unzip -o $RemoteHome/$ZipName -d $RemoteHome/cv-search-poc > /dev/null"
Log "Unzip complete."

# --- Step 4: Deploy ---
if ($SkipBuild) {
    Log "Restarting containers (skip build)..."
    Invoke-Ssh "cd $RemoteHome/cv-search-poc && sudo cp docker-compose.yml Dockerfile .dockerignore pyproject.toml README.md $RemoteApp/ && sudo cp -r src $RemoteApp/ && sudo cp api_server.py $RemoteApp/ 2>/dev/null; cd $RemoteApp && sudo docker compose up -d --force-recreate"
} else {
    Log "Running full deploy (build + restart)..."
    Invoke-Ssh "cd $RemoteHome/cv-search-poc && sudo bash scripts/deploy-vm.sh"
}

# --- Step 5: Verify ---
Log "Waiting for API..."
Start-Sleep -Seconds 5

$healthy = $false
for ($i = 0; $i -lt 12; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri "http://${VmIp}:8000/ready" -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($resp.status -eq "ready") {
            $healthy = $true
            break
        }
    } catch {}
    Start-Sleep -Seconds 5
}

if ($healthy) {
    Log "API is ready at http://${VmIp}:8000"
    Log "Docs: http://${VmIp}:8000/docs"
    Write-Host ""
    Write-Host "Deployment successful!" -ForegroundColor Green
} else {
    Write-Host ""
    Fail "API did not become ready. Check logs: ssh $VmUser@$VmIp 'sudo docker compose -f $RemoteApp/docker-compose.yml logs api'"
}