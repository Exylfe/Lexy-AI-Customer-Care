#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Lexy — AI Assistant Launcher
.DESCRIPTION
    Starts one or all Lexy services: terminal chat, web dashboard,
    WhatsApp server, and WhatsApp bridge.
.PARAMETER Mode
    terminal | web | all | whatsapp | full
.PARAMETER Port
    Web dashboard port (default: 5050)
.EXAMPLE
    .\start.ps1 -Mode web
    .\start.ps1 -Mode full
#>

param(
    [ValidateSet("terminal","web","all","whatsapp","full")]
    [string]$Mode = "terminal",
    [int]$Port = 5050
)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Start-ProcessInDir {
    param([string]$File, [string]$Args, [string]$Title)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "python"
    $psi.Arguments = $Args
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
    if ($Title) { $psi.Arguments = "cmd /c start `"$Title`" python $Args" }
    [System.Diagnostics.Process]::Start($psi)
}

switch ($Mode) {
    "terminal" {
        Write-Host "Starting terminal chat..." -ForegroundColor Green
        python main.py
    }
    "web" {
        Write-Host "Starting web dashboard on port $Port..." -ForegroundColor Green
        python main.py --web --port $Port
    }
    "all" {
        Write-Host "Starting terminal + dashboard..." -ForegroundColor Green
        python main.py --all --port $Port
    }
    "whatsapp" {
        Write-Host "Starting WhatsApp bridge..." -ForegroundColor Green
        $psi1 = Start-Process "python" "frontends/whatsapp_server.py" -PassThru
        Start-Sleep 2
        Set-Location "$Root/whatsapp-bridge"
        node index.js
    }
    "full" {
        Write-Host "Starting all services..." -ForegroundColor Green
        Start-Process "python" "main.py --all --port $Port"
        Start-Sleep 1
        Start-Process "python" "frontends/whatsapp_server.py"
        Start-Sleep 3
        Set-Location "$Root/whatsapp-bridge"
        Start-Process "node" "index.js"
    }
}
