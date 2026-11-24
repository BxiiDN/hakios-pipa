<#
  Copy the Xiaomi Pad 6's UFS disks, offered READ ONLY by the UEFI tools "USB disk: LUN 0 (read only)" and
  "USB disk: boot LUN (read only)" (hakios-pipa docs/IPADOS-PARTITION.md, section 12), into files on this PC.
  Run in PowerShell as Administrator (raw disk reads need it). The disk is opened with FileAccess.Read only; nothing is
  ever written to it. Windows may offer to "initialize" or "format" the disk: always Cancel (the tablet refuses writes
  anyway).

    .\dump-pipa-usb.ps1 -List
    .\dump-pipa-usb.ps1 -Disk N -Mode boot -Out \\wsl.localhost\Ubuntu\home\<user>\.hakios-private\usb-dump
    .\dump-pipa-usb.ps1 -Disk N -Mode lun0 -Out \\wsl.localhost\Ubuntu\home\<user>\.hakios-private\usb-dump

  boot : the whole disk -> boot-lun.img (about 2 GiB)
  lun0 : bytes 0 .. start of "userdata" -> lun0-head.img (GPT, super, persist, ...; about 10.3 GiB) and the last
         5 sectors -> lun0-tail.bin (backup GPT). userdata itself is not copied (design B formats it).
  Every file gets a SHA-256 line in SHA256SUMS.txt. Then, in WSL: python3 tools/usb_dump_check.py DIR
#>
param(
  [switch]$List,
  [int]$Disk = -1,
  [ValidateSet('boot', 'lun0')][string]$Mode,
  [string]$Out
)
$ErrorActionPreference = 'Stop'

if ($List) {
  Get-Disk | Where-Object BusType -eq 'USB' |
    Select-Object Number, FriendlyName, @{n='MiB';e={[math]::Floor($_.Size / 1MB)}}, LogicalSectorSize, PartitionStyle |
    Format-Table -AutoSize
  exit 0
}
if ($Disk -lt 0 -or -not $Mode -or -not $Out) { throw 'give -Disk N -Mode boot|lun0 -Out DIR (see -List)' }
$info = Get-Disk -Number $Disk
if ($info.BusType -ne 'USB') { throw "disk $Disk is not a USB disk ($($info.BusType)): refusing" }
$sector = [int]$info.LogicalSectorSize
$size = [int64]$info.Size
New-Item -ItemType Directory -Force -Path $Out | Out-Null

$stream = [System.IO.File]::Open("\\.\PhysicalDrive$Disk", [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read,
                                 [System.IO.FileShare]::ReadWrite)
function Copy-Range([int64]$offset, [int64]$length, [string]$file) {
  $dst = [System.IO.File]::Open((Join-Path $Out $file), [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
  $buf = New-Object byte[] (16MB)
  $stream.Position = $offset
  $left = $length
  while ($left -gt 0) {
    $n = [int][math]::Min($buf.Length, $left)
    $got = $stream.Read($buf, 0, $n)
    if ($got -le 0) { throw "short read at $($offset + $length - $left)" }
    $dst.Write($buf, 0, $got)
    $left -= $got
    Write-Progress -Activity $file -PercentComplete ([int](100 * ($length - $left) / $length))
  }
  $dst.Close()
}
function Read-Bytes([int64]$offset, [int]$length) {
  $b = New-Object byte[] $length; $stream.Position = $offset
  if ($stream.Read($b, 0, $length) -ne $length) { throw 'short read' }; return ,$b
}

try {
  $hdr = Read-Bytes $sector $sector
  if ([System.Text.Encoding]::ASCII.GetString($hdr, 0, 8) -ne 'EFI PART') { throw 'no GPT at LBA 1: is this the tablet?' }
  if ($Mode -eq 'boot') {
    Copy-Range 0 $size 'boot-lun.img'
  } else {
    $entriesLba = [BitConverter]::ToInt64($hdr, 72); $count = [BitConverter]::ToInt32($hdr, 80); $esize = [BitConverter]::ToInt32($hdr, 84)
    $entries = Read-Bytes ($entriesLba * $sector) ($count * $esize)
    $first = -1
    for ($i = 0; $i -lt $count; $i++) {
      $name = [System.Text.Encoding]::Unicode.GetString($entries, $i * $esize + 56, 72).TrimEnd([char]0)
      if ($name -eq 'userdata') { $first = [BitConverter]::ToInt64($entries, $i * $esize + 32) }
    }
    if ($first -le 0) { throw 'no userdata partition on this disk: not LUN 0' }
    Copy-Range 0 ($first * $sector) 'lun0-head.img'
    Copy-Range ($size - 5 * $sector) (5 * $sector) 'lun0-tail.bin'
  }
} finally { $stream.Close() }

Get-ChildItem $Out -File | Where-Object Name -ne 'SHA256SUMS.txt' | ForEach-Object {
  "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
} | Add-Content (Join-Path $Out 'SHA256SUMS.txt')
"disk $Disk ($($info.FriendlyName), $([math]::Floor($size / 1MB)) MiB, sector $sector): $Mode copied to $Out"
