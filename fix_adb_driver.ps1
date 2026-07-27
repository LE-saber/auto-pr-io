$AdbPath = "D:\Android_adb\platform-tools\adb.exe"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Write-Host "[ERROR] Run as Administrator" -ForegroundColor Red; Read-Host "Press Enter"; exit 1 }
$driverDir = "$env:TEMP\adb_usb_driver"
$zipPath = "$env:TEMP\usb_driver.zip"
if (-not (Test-Path "$driverDir\android_winusb.inf")) {
    Write-Host "[INFO] Downloading Google USB driver..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "https://dl.google.com/android/repository/usb_driver_r13-windows.zip" -OutFile $zipPath -UseBasicParsing
    Expand-Archive $zipPath -DestinationPath $driverDir -Force
    $inner = Join-Path $driverDir "usb_driver"
    if (Test-Path $inner) { Get-ChildItem $inner | Copy-Item -Destination $driverDir -Recurse -Force }
}
$infPath = "$driverDir\android_winusb.inf"
$c = Get-Content $infPath -Raw
if ($c -notmatch "vivo") {
    $a = [char]38; $b = "`r`n"; $v = "VID_2D95"
    $add = $b + "; vivo " + $v + $b
    $add += "%SingleAdbInterface% = USB_Install, USB\" + $v + $a + "PID_6013" + $b
    $add += "%CompositeAdbInterface% = USB_Install, USB\" + $v + $a + "PID_6013" + $a + "MI_02" + $b
    $add += "%SingleAdbInterface% = USB_Install, USB\" + $v + $a + "PID_6015" + $b
    $add += "%CompositeAdbInterface% = USB_Install, USB\" + $v + $a + "PID_6015" + $a + "MI_02" + $b
    $c = $c.Replace("[Google.NTamd64]", "[Google.NTamd64]" + $add)
    $c = $c.Replace("[Google.NTx86]", "[Google.NTx86]" + $add)
    Set-Content $infPath $c -Encoding UTF8
    Write-Host "[INFO] vivo entries injected" -ForegroundColor Green
}
Get-ChildItem $driverDir -Filter "*.cat" | Remove-Item -Force
Write-Host ""
Write-Host "Driver files ready at: $driverDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "Steps to install:" -ForegroundColor Yellow
Write-Host "  1. Device Manager will open now" -ForegroundColor White
Write-Host "  2. Find: Other devices or AndroidUsbDeviceClass" -ForegroundColor White
Write-Host "  3. Right-click Android Composite ADB Interface -> Update driver" -ForegroundColor White
Write-Host "  4. Browse my computer -> Let me pick from list -> Have Disk" -ForegroundColor White
Write-Host "  5. Browse to: $driverDir" -ForegroundColor White
Write-Host "  6. Click OK -> Install anyway (ignore unsigned warning)" -ForegroundColor White
Write-Host ""
Start-Process devmgmt.msc
Start-Process explorer.exe $driverDir
Read-Host "Press Enter after installing driver"
& $AdbPath kill-server
Start-Sleep -Seconds 1
& $AdbPath start-server
Start-Sleep -Seconds 2
& $AdbPath devices -l
Read-Host "Press Enter to exit"
