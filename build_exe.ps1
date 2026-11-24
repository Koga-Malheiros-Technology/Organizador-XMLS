# Compila os executáveis de distribuição.
#
#   .\build_exe.ps1            # interface (OrganizadorXML.exe) e console
#   .\build_exe.ps1 -SoGui     # só a interface
#
# Saída: .\dist\OrganizadorXML.exe  (arquivo único, sem dependência de Python)

param(
    [switch]$SoGui
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Instalando dependências de build..." -ForegroundColor Cyan
uv sync --group build

if (-not (Test-Path packaging\icone.ico)) {
    Write-Host "Gerando o ícone..." -ForegroundColor Cyan
    uv run --group build python packaging\gerar_icone.py
}

Write-Host "Compilando a interface..." -ForegroundColor Cyan
uv run pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/OrganizadorXML.spec

if (-not $SoGui) {
    Write-Host "Compilando a versão de console..." -ForegroundColor Cyan
    uv run pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/OrganizadorXML-CLI.spec
}

Copy-Item packaging\LEIA-ME-cliente.txt dist\ -Force

Get-ChildItem dist -Filter *.exe | ForEach-Object {
    "{0}  ({1:N1} MB)" -f $_.Name, ($_.Length / 1MB)
}
