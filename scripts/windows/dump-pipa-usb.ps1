<#
  Copy the Xiaomi Pad 6's UFS disks, offered READ ONLY by the UEFI tools "USB disk: LUN 0 (read only)" and
  "USB disk: boot LUN (read only)" (hakios-pipa docs/IPADOS-PARTITION.md, sections 12-13), into files on this PC.
  Run in PowerShell as Administrator (raw disk reads need it). The disk is opened with FileAccess.Read only; nothing is
  ever written to it. Windows may offer to "initialize" or "format" the disk: always Cancel (the tablet refuses writes
  anyway).

    .\dump-pipa-usb.ps1 -List                       every USB disk, and which pipa disk its GPT says it is
    .\dump-pipa-usb.ps1 -Disk N -Mode boot -Out DIR  the whole boot LUN -> boot-lun.img (about 2 GiB)
    .\dump-pipa-usb.ps1 -Disk N -Mode lun0 -Out DIR  LUN 0 up to userdata -> lun0-head.img (~10.3 GiB) + lun0-tail.bin

  A disk is copied only when its identity is proven first, never from BusType alone:
    - USB, not a Windows system/boot disk, 4096-byte logical sectors;
    - primary GPT at LBA 1: signature, header size, header CRC32 and entry-array CRC32 as computed here; backup header
      at the last LBA naming itself and LBA 1;
    - lun0: 253 461 790 720 bytes, 34 partitions, userdata = LBA 0x293000 .. 61880314 (the layout measured on
      2026-11-24); boot: partitions boot_a, boot_b, vendor_boot_b, dtbo_b, vbmeta_b, abl_b, xbl_b present.
  Every file gets a SHA-256 line in SHA256SUMS.txt. Then, in WSL: python3 tools/usb_dump_check.py DIR ...
#>
param(
  [switch]$List,
  [switch]$Check,                # print the identity of -Disk N and copy nothing
  [string]$ImageFile,            # tests only: a disk image file in place of \\.\PhysicalDriveN (BusType checks skipped)
  [int]$Disk = -1,
  [ValidateSet('boot', 'lun0')][string]$Mode,
  [string]$Out
)
$ErrorActionPreference = 'Stop'
$Lun0Bytes = [int64]253461790720
$BootNames = @('boot_a', 'boot_b', 'vendor_boot_b', 'dtbo_b', 'vbmeta_b', 'abl_b', 'xbl_b')

$CrcTable = New-Object 'uint32[]' 256
for ($n = 0; $n -lt 256; $n++) {
  [uint32]$c = $n
  for ($k = 0; $k -lt 8; $k++) { if ($c -band 1) { $c = [uint32]([uint32]3988292384 -bxor ($c -shr 1)) } else { $c = [uint32]($c -shr 1) } }
  $CrcTable[$n] = $c
}
function Get-Crc32([byte[]]$b, [int]$off, [int]$len) {
  [uint32]$c = [uint32]::MaxValue
  for ($i = $off; $i -lt $off + $len; $i++) { $c = [uint32]($CrcTable[($c -bxor $b[$i]) -band 0xFF] -bxor ($c -shr 8)) }
  return [uint32]($c -bxor [uint32]::MaxValue)
}

function Open-ReadOnly([int]$n) {
  $path = if ($ImageFile) { $ImageFile } else { "\\.\PhysicalDrive$n" }
  return [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read,
                                [System.IO.FileShare]::ReadWrite)
}
function Read-At($s, [int64]$offset, [int]$length) {
  $b = New-Object byte[] $length; $s.Position = $offset
  $got = 0
  while ($got -lt $length) { $r = $s.Read($b, $got, $length - $got); if ($r -le 0) { throw 'short read' }; $got += $r }
  return ,$b
}

# The identity of disk $n from its GPT: @{ Kind = 'lun0' | 'boot' | $null; Why = ...; Sector; Size; UserdataFirst }
function Get-Identity([int]$n) {
  if ($ImageFile) {
    $info = [pscustomobject]@{ BusType = 'USB'; IsSystem = $false; IsBoot = $false; LogicalSectorSize = 4096;
                               Size = (Get-Item $ImageFile).Length }
  } else { $info = Get-Disk -Number $n }
  $id = @{ Kind = $null; Why = ''; Sector = [int]$info.LogicalSectorSize; Size = [int64]$info.Size; UserdataFirst = 0 }
  if ($info.BusType -ne 'USB') { $id.Why = "bus $($info.BusType), not USB"; return $id }
  if ($info.IsSystem -or $info.IsBoot) { $id.Why = 'a Windows system/boot disk'; return $id }
  if ($id.Sector -ne 4096) { $id.Why = "sector $($id.Sector), not 4096"; return $id }
  $s = Open-ReadOnly $n
  try {
    $hdr = Read-At $s 4096 4096
    if ([System.Text.Encoding]::ASCII.GetString($hdr, 0, 8) -ne 'EFI PART') { $id.Why = 'no GPT at LBA 1'; return $id }
    $hsize = [BitConverter]::ToUInt32($hdr, 12); $hcrc = [BitConverter]::ToUInt32($hdr, 16)
    if ($hsize -lt 92 -or $hsize -gt 512) { $id.Why = 'GPT header size out of range'; return $id }
    $copy = New-Object byte[] $hsize; [Array]::Copy($hdr, $copy, $hsize); $copy[16] = 0; $copy[17] = 0; $copy[18] = 0; $copy[19] = 0
    if ((Get-Crc32 $copy 0 $hsize) -ne $hcrc) { $id.Why = 'GPT header CRC32 does not match'; return $id }
    $backupLba = [BitConverter]::ToInt64($hdr, 32); $lastUsable = [BitConverter]::ToInt64($hdr, 48)
    $entriesLba = [BitConverter]::ToInt64($hdr, 72); $count = [BitConverter]::ToInt32($hdr, 80)
    $esize = [BitConverter]::ToInt32($hdr, 84); $ecrc = [BitConverter]::ToUInt32($hdr, 88)
    if ($backupLba -ne ($id.Size / 4096) - 1) { $id.Why = 'backup LBA is not the last LBA'; return $id }
    $entries = Read-At $s ($entriesLba * 4096) ($count * $esize)
    if ((Get-Crc32 $entries 0 $entries.Length) -ne $ecrc) { $id.Why = 'GPT entries CRC32 does not match'; return $id }
    $back = Read-At $s ($backupLba * 4096) 4096
    if ([System.Text.Encoding]::ASCII.GetString($back, 0, 8) -ne 'EFI PART' -or
        [BitConverter]::ToInt64($back, 24) -ne $backupLba -or [BitConverter]::ToInt64($back, 32) -ne 1) {
      $id.Why = 'backup GPT header is not the mirror'; return $id
    }
    $names = @{}; $parts = 0
    for ($i = 0; $i -lt $count; $i++) {
      $o = $i * $esize
      $empty = $true; for ($j = 0; $j -lt 16; $j++) { if ($entries[$o + $j] -ne 0) { $empty = $false; break } }
      if ($empty) { continue }
      $parts++
      $name = [System.Text.Encoding]::Unicode.GetString($entries, $o + 56, 72).Split([char]0)[0]
      $names[$name] = @([BitConverter]::ToInt64($entries, $o + 32), [BitConverter]::ToInt64($entries, $o + 40))
    }
    if ($names.ContainsKey('userdata')) {
      $u = $names['userdata']
      if ($id.Size -eq $Lun0Bytes -and $parts -eq 34 -and $u[0] -eq 0x293000 -and $u[1] -eq 61880314 -and $lastUsable -eq 61880314) {
        $id.Kind = 'lun0'; $id.UserdataFirst = $u[0]; $id.Why = 'pipa LUN 0 (measured layout)'
      } else { $id.Why = "has userdata, but not the measured LUN 0 (size $($id.Size), $parts partitions, userdata $($u[0])..$($u[1]))" }
    } elseif (@($BootNames | Where-Object { -not $names.ContainsKey($_) }).Count -eq 0) {
      $id.Kind = 'boot'; $id.Why = "pipa boot LUN ($parts partitions)"
    } else { $id.Why = 'GPT of another disk' }
  } finally { $s.Close() }
  return $id
}

if ($List) {
  Get-Disk | Where-Object BusType -eq 'USB' | ForEach-Object {
    $id = Get-Identity $_.Number
    "{0,3}  {1,-28} {2,10} MiB  {3,-5} {4}" -f $_.Number, $_.FriendlyName, [math]::Floor($_.Size / 1MB), $id.Kind, $id.Why
  }
  exit 0
}
if ($Check) { $id = Get-Identity $Disk; "kind=$($id.Kind) why=$($id.Why)"; exit 0 }
if ($Disk -lt 0 -or -not $Mode -or -not $Out) { throw 'give -Disk N -Mode boot|lun0 -Out DIR (see -List)' }
$id = Get-Identity $Disk
if ($id.Kind -ne $Mode) { throw "disk ${Disk}: $($id.Why) -- not the pipa $Mode disk: refusing" }
New-Item -ItemType Directory -Force -Path $Out | Out-Null

$stream = Open-ReadOnly $Disk
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
try {
  if ($Mode -eq 'boot') {
    Copy-Range 0 $id.Size 'boot-lun.img'
  } else {
    Copy-Range 0 ($id.UserdataFirst * 4096) 'lun0-head.img'
    Copy-Range ($id.Size - 5 * 4096) (5 * 4096) 'lun0-tail.bin'
  }
} finally { $stream.Close() }

$sums = Join-Path $Out 'SHA256SUMS.txt'
$listed = if (Test-Path $sums) { @(Get-Content $sums | ForEach-Object { ($_ -split '\s+', 2)[1] }) } else { @() }
foreach ($name in @('boot-lun.img', 'lun0-head.img', 'lun0-tail.bin')) {
  $f = Join-Path $Out $name
  if ((Test-Path $f) -and ($listed -notcontains $name)) {
    "{0}  {1}" -f (Get-FileHash $f -Algorithm SHA256).Hash.ToLower(), $name | Add-Content $sums
  }
}
"disk $Disk ($($id.Why), $([math]::Floor($id.Size / 1MB)) MiB): $Mode copied to $Out"
