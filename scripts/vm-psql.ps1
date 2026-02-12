<#
.SYNOPSIS
    Run a SQL query against the VM's Postgres database.

.EXAMPLE
    .\scripts\vm-psql.ps1 "SELECT count(*) FROM candidate"
    .\scripts\vm-psql.ps1 "SELECT candidate_id, name, seniority FROM candidate LIMIT 5"
#>
param(
    [Parameter(Mandatory, Position = 0)]
    [string]$Query,

    [string]$VmIp = "20.55.80.228",
    [string]$KeyPath = (Join-Path $env:USERPROFILE 'Downloads\cvsearch-vm_key.pem')
)

ssh -i $KeyPath azureuser@$VmIp "sudo docker compose -f /opt/cvsearch/docker-compose.yml exec -T postgres psql -U cvsearch -d cvsearch -c '$Query'"
