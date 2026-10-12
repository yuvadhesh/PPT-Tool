<#
.SYNOPSIS
  Read-only inventory of the MathType / PowerPoint installation on this Windows PC.

.DESCRIPTION
  Collects only information Windows already records about installed software:
  uninstall registry entries, COM ProgID/CLSID registrations for the MathType
  equation object classes, and the Office/PowerPoint installation. Nothing is
  changed. Send the generated mathtype_discovery.json back so the MathType
  worker can be implemented against the interfaces your installation actually
  provides.
#>
$ErrorActionPreference = "SilentlyContinue"
$result = [ordered]@{
  generated_at = (Get-Date).ToString("o")
  os           = (Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture)
  installed    = @()
  progids      = @()
  powerpoint   = $null
}

$uninstallRoots = @(
  "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
  "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
  "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
)
$result.installed = Get-ItemProperty $uninstallRoots |
  Where-Object { $_.DisplayName -match "MathType|Wiris|Microsoft (Office|365)|PowerPoint" } |
  Select-Object DisplayName, DisplayVersion, Publisher, InstallLocation

# Equation object classes registered with COM (Equation.DSMT* = MathType, Equation.3 = Equation Editor 3.0).
$classes = Get-ChildItem "Registry::HKEY_CLASSES_ROOT" | Where-Object { $_.PSChildName -like "Equation.*" }
foreach ($c in $classes) {
  $clsid = (Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\$($c.PSChildName)\CLSID")."(default)"
  $server = $null
  if ($clsid) {
    foreach ($view in @("CLSID", "WOW6432Node\CLSID")) {
      $key = "Registry::HKEY_CLASSES_ROOT\$view\$clsid"
      $local = (Get-ItemProperty "$key\LocalServer32")."(default)"
      $inproc = (Get-ItemProperty "$key\InprocServer32")."(default)"
      if ($local -or $inproc) { $server = @{ view = $view; local_server = $local; inproc_server = $inproc }; break }
    }
  }
  $result.progids += [ordered]@{
    progid      = $c.PSChildName
    description = (Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\$($c.PSChildName)")."(default)"
    clsid       = $clsid
    server      = $server
  }
}

$ppt = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\powerpnt.exe")."(default)"
if ($ppt) {
  $result.powerpoint = @{ path = $ppt; version = (Get-Item $ppt).VersionInfo.ProductVersion }
}

# PowerPoint add-ins registered for the current user / machine (MathType ships a PowerPoint add-in).
$result.powerpoint_addins = @(
  Get-ChildItem "HKCU:\SOFTWARE\Microsoft\Office\PowerPoint\Addins", "HKLM:\SOFTWARE\Microsoft\Office\PowerPoint\Addins" |
    ForEach-Object { [ordered]@{ key = $_.Name; friendly = (Get-ItemProperty $_.PSPath).FriendlyName } }
)

$out = Join-Path $PSScriptRoot "mathtype_discovery.json"
$result | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 $out
Write-Host "Wrote $out"
