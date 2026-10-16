<#
.SYNOPSIS
    Make one FairLend Watch team access code and its SHA-256 hash (Phase 11).

.DESCRIPTION
    Prints a random 16-character code and its SHA-256 hash ONCE, to this terminal only. Writes nothing to disk.
    - Give the CODE to the team member privately (not by email in plain text, if you can avoid it).
    - Put only the HASH in the Streamlit secret FAIRLEND_ACCESS_HASHES (a TOML list).
    - To revoke a code, remove its hash from the secret.
    The code uses a cryptographic random generator and letters and digits that are hard to confuse
    (no 0/O, 1/l/I). Run it again for each person.

.EXAMPLE
    .\tools\make_access_code.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"   # 56 characters
$length = 16
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$limit = 256 - (256 % $alphabet.Length)   # reject bytes above this so every character is equally likely
$chars = New-Object System.Collections.Generic.List[char]
$buffer = New-Object byte[] 1
try {
    while ($chars.Count -lt $length) {
        $rng.GetBytes($buffer)
        if ($buffer[0] -lt $limit) { $chars.Add($alphabet[$buffer[0] % $alphabet.Length]) }
    }
}
finally {
    $rng.Dispose()
}
$code = -join $chars
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
    $bytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($code))
}
finally {
    $sha.Dispose()
}
$hash = -join ($bytes | ForEach-Object { $_.ToString("x2") })

Write-Output "Access code (give to the person; shown once, not saved): $code"
Write-Output "SHA-256 hash (put in FAIRLEND_ACCESS_HASHES):            $hash"
