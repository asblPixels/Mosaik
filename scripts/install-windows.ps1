# Mosaïk — installation pour Windows 10/11 (aucun droit administrateur requis pour installer)
# Usage : clic droit > « Exécuter avec PowerShell », ou double-clic sur install-windows.bat
$ErrorActionPreference = "Stop"
$Src  = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $env:LOCALAPPDATA "Mosaik"

Write-Host "`n  Mosaïk — installation pour Windows`n" -ForegroundColor Cyan

# 1. Python 3.8+
function Find-Python {
    foreach ($c in @("py -3", "python", "python3")) {
        try {
            $exe = & ([scriptblock]::Create("$c -c `"import sys;print(sys.executable) if sys.version_info>=(3,8) else exit(1)`"")) 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch {}
    }
    return $null
}
$py = Find-Python
if (-not $py) {
    Write-Host "Python 3 est nécessaire. Installation via winget…" -ForegroundColor Yellow
    try { winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements | Out-Host }
    catch { }
    $env:Path = [Environment]::GetEnvironmentVariable("Path","User") + ";" + [Environment]::GetEnvironmentVariable("Path","Machine")
    $py = Find-Python
    if (-not $py) {
        Write-Host "Installez Python depuis https://www.python.org/downloads/ (cochez « Add Python to PATH »), puis relancez." -ForegroundColor Red
        Read-Host "Appuyez sur Entrée pour fermer"; exit 1
    }
}
Write-Host "Python trouvé : $py"
$pyw = Join-Path (Split-Path $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }

# 2. Copie des fichiers
New-Item -ItemType Directory -Force -Path "$Dest\assets\fonts" | Out-Null
Copy-Item "$Src\mosaik.py","$Src\ui.html","$Src\LICENSE" $Dest -Force
Copy-Item "$Src\assets\*.svg","$Src\assets\*.png","$Src\assets\*.ico" "$Dest\assets" -Force
Copy-Item "$Src\assets\fonts\*" "$Dest\assets\fonts" -Force

# 3. Raccourcis (menu Démarrer + Bureau)
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop"))) {
    $lnk = $shell.CreateShortcut((Join-Path $dir "Mosaïk.lnk"))
    $lnk.TargetPath = $pyw
    $lnk.Arguments = "`"$Dest\mosaik.py`""
    $lnk.WorkingDirectory = $Dest
    $lnk.IconLocation = "$Dest\assets\mosaik.ico"
    $lnk.Description = "Mosaïk — récupération de fichiers"
    $lnk.Save()
}

# 4. The Sleuth Kit (facultatif)
if (-not (Get-Command fls -ErrorAction SilentlyContinue)) {
    Write-Host "`nFacultatif : pour retrouver les noms d'origine des fichiers, installez The Sleuth Kit pour Windows"
    Write-Host "(https://www.sleuthkit.org/sleuthkit/download.php) et ajoutez son dossier « bin » au PATH."
}

Write-Host "`nMosaïk est installé ! Lancez-le depuis le menu Démarrer ou l'icône du Bureau." -ForegroundColor Green
Write-Host "Windows demandera l'autorisation administrateur : elle est nécessaire pour lire un disque."
Read-Host "`nAppuyez sur Entrée pour fermer"
