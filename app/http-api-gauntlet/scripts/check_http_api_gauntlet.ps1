param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# This script now lives in app/http-api-gauntlet/scripts/, so the repo root
# climb is three levels (..\..\..). The compile target is the project-mode
# build tape (build.sem) in the parent directory; semsc inlines main.sem.
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..\..")
$AppDir = Resolve-Path (Join-Path $ScriptDir "..")
$SourcePath = Join-Path $AppDir "build.sem"
$ExePath = Join-Path $ScriptDir "http_api_gauntlet.exe"
$BaseUrl = "http://127.0.0.1:18082"
$TempFiles = New-Object System.Collections.Generic.List[string]
$Server = $null

function New-GauntletTempFile {
    $file = New-TemporaryFile
    $TempFiles.Add($file.FullName)
    return $file.FullName
}

function Invoke-GauntletCurl {
    param(
        [string]$Method,
        [string]$Path,
        [int]$ExpectedStatus,
        [string]$ExpectedBody,
        [hashtable]$Headers = @{},
        [AllowNull()][string]$Body = $null,
        [AllowNull()][string]$ContentType = $null,
        [switch]$Quiet
    )

    $bodyFile = New-GauntletTempFile
    $headerFile = New-GauntletTempFile
    $curlArgs = @("-sS", "-o", $bodyFile, "-D", $headerFile, "-w", "%{http_code}", "-X", $Method)

    foreach ($key in $Headers.Keys) {
        $curlArgs += @("-H", "${key}: $($Headers[$key])")
    }
    if ($ContentType) {
        $curlArgs += @("-H", "Content-Type: $ContentType")
    }
    if ($null -ne $Body) {
        $curlArgs += @("--data-binary", $Body)
    }
    $curlArgs += @("--url", "${BaseUrl}${Path}")

    $statusText = & curl.exe @curlArgs
    if ($LASTEXITCODE -ne 0) {
        throw "curl failed for $Method $Path"
    }

    $actualStatus = [int]$statusText
    $actualBody = [System.IO.File]::ReadAllText($bodyFile)
    if ($actualStatus -ne $ExpectedStatus) {
        throw "$Method $Path expected HTTP $ExpectedStatus but got $actualStatus with body [$actualBody]"
    }
    if ($actualBody -ne $ExpectedBody) {
        throw "$Method $Path expected body [$ExpectedBody] but got [$actualBody]"
    }

    if (-not $Quiet) {
        Write-Host "OK $Method $Path -> $ExpectedStatus"
    }
    return @{
        Status = $actualStatus
        Body = $actualBody
        Headers = [System.IO.File]::ReadAllLines($headerFile)
    }
}

function Assert-GauntletHeader {
    param(
        [hashtable]$Response,
        [string]$Name,
        [string]$ExpectedValue
    )

    $pattern = "^" + [regex]::Escape($Name) + "\s*:"
    $line = $Response.Headers | Where-Object { $_ -match $pattern } | Select-Object -Last 1
    if (-not $line) {
        throw "Missing response header $Name"
    }
    $actualValue = ($line -replace "^[^:]+:\s*", "")
    if ($actualValue -ne $ExpectedValue) {
        throw "Header $Name expected [$ExpectedValue] but got [$actualValue]"
    }
}

function Wait-GauntletServer {
    for ($attempt = 0; $attempt -lt 80; $attempt += 1) {
        try {
            $health = Invoke-GauntletCurl -Method "GET" -Path "/health" -ExpectedStatus 200 -ExpectedBody "ok`n" -Quiet
            Assert-GauntletHeader -Response $health -Name "X-Gauntlet-App" -ExpectedValue "http-api-gauntlet"
            return
        } catch {
            Start-Sleep -Milliseconds 100
        }
    }
    throw "HTTP gauntlet server did not become reachable at $BaseUrl"
}

Push-Location $RepoRoot
try {
    & $Python "SemanticScript/compiler/semsc.py" $SourcePath "--emit-exe" $ExePath "--quiet"
    if ($LASTEXITCODE -ne 0) {
        throw "failed to build HTTP gauntlet executable"
    }

    $Server = Start-Process -FilePath $ExePath -PassThru -WindowStyle Hidden
    Wait-GauntletServer

    Invoke-GauntletCurl -Method "GET" -Path "/reflect/method" -ExpectedStatus 200 -ExpectedBody "GET" | Out-Null
    Invoke-GauntletCurl -Method "GET" -Path "/reflect/path?x=1" -ExpectedStatus 200 -ExpectedBody "/reflect/path" | Out-Null
    Invoke-GauntletCurl -Method "GET" -Path "/reflect/header" -ExpectedStatus 200 -ExpectedBody "abc" -Headers @{"X-Gauntlet-Token" = "abc"} | Out-Null
    Invoke-GauntletCurl -Method "GET" -Path "/reflect/header" -ExpectedStatus 400 -ExpectedBody "missing header: X-Gauntlet-Token`n" | Out-Null
    Invoke-GauntletCurl -Method "GET" -Path "/reflect/required-header-or-fail" -ExpectedStatus 200 -ExpectedBody "yes" -Headers @{"X-Gauntlet-Required" = "yes"} | Out-Null
    Invoke-GauntletCurl -Method "GET" -Path "/reflect/required-header-or-fail" -ExpectedStatus 500 -ExpectedBody "handler failed`n" | Out-Null
    Invoke-GauntletCurl -Method "GET" -Path "/reflect/query?name=earl" -ExpectedStatus 200 -ExpectedBody "earl" | Out-Null
    Invoke-GauntletCurl -Method "GET" -Path "/reflect/query-empty?empty" -ExpectedStatus 200 -ExpectedBody "" | Out-Null
    Invoke-GauntletCurl -Method "GET" -Path "/reflect/query-repeat?name=a&name=b" -ExpectedStatus 200 -ExpectedBody "a" | Out-Null
    Invoke-GauntletCurl -Method "POST" -Path "/reflect/body" -ExpectedStatus 201 -ExpectedBody "hello" -Body "hello" | Out-Null
    Invoke-GauntletCurl -Method "POST" -Path "/reflect/body-size" -ExpectedStatus 200 -ExpectedBody "small body`n" -Body "hello" | Out-Null
    Invoke-GauntletCurl -Method "PUT" -Path "/reflect/body-size" -ExpectedStatus 200 -ExpectedBody "large body`n" -Body "hello world!!!!" | Out-Null

    $options = Invoke-GauntletCurl -Method "OPTIONS" -Path "/capabilities" -ExpectedStatus 200 -ExpectedBody "capabilities: method path header query body bodyBytes bodyLength multipart responseHeader responseBytes sse middleware`n"
    Assert-GauntletHeader -Response $options -Name "Allow" -ExpectedValue "GET, POST, PUT, PATCH, DELETE, OPTIONS"

    $custom = Invoke-GauntletCurl -Method "GET" -Path "/content/custom" -ExpectedStatus 200 -ExpectedBody "custom content`n"
    Assert-GauntletHeader -Response $custom -Name "Content-Type" -ExpectedValue "application/x-gauntlet; charset=utf-8"

    $redirect = Invoke-GauntletCurl -Method "GET" -Path "/redirect" -ExpectedStatus 302 -ExpectedBody "redirecting`n"
    Assert-GauntletHeader -Response $redirect -Name "Location" -ExpectedValue "/health"

    Invoke-GauntletCurl -Method "DELETE" -Path "/empty" -ExpectedStatus 204 -ExpectedBody "" | Out-Null
    Invoke-GauntletCurl -Method "PATCH" -Path "/patch" -ExpectedStatus 200 -ExpectedBody "patched`n" | Out-Null
    Invoke-GauntletCurl -Method "GET" -Path "/middleware-short-circuit" -ExpectedStatus 418 -ExpectedBody "middleware short-circuited; handler skipped by dispatcher`n" | Out-Null

    $sse = Invoke-GauntletCurl -Method "GET" -Path "/events/one" -ExpectedStatus 200 -ExpectedBody "event: gauntlet`ndata: connected`n`n"
    Assert-GauntletHeader -Response $sse -Name "Content-Type" -ExpectedValue "text/event-stream; charset=utf-8"

    $uploadFile = New-GauntletTempFile
    [System.IO.File]::WriteAllText($uploadFile, "upload-body")
    $multipartBodyFile = New-GauntletTempFile
    $multipartHeaderFile = New-GauntletTempFile
    $multipartStatus = & curl.exe -sS -o $multipartBodyFile -D $multipartHeaderFile -w "%{http_code}" -X POST `
        -F "description=semantic upload" `
        -F "upload=@$uploadFile;filename=todo.bin;type=application/x-gauntlet" `
        "${BaseUrl}/multipart/file-name"
    if ($LASTEXITCODE -ne 0 -or [int]$multipartStatus -ne 200) {
        throw "multipart file-name route failed"
    }
    $multipartBody = [System.IO.File]::ReadAllText($multipartBodyFile)
    if ($multipartBody -ne "todo.bin") {
        throw "multipart file-name expected [todo.bin] but got [$multipartBody]"
    }
    Write-Host "OK POST /multipart/file-name -> 200"

    Write-Host "HTTP API gauntlet curl smoke passed"
} finally {
    if ($Server -and -not $Server.HasExited) {
        Stop-Process -Id $Server.Id -Force
    }
    foreach ($file in $TempFiles) {
        if (Test-Path $file) {
            Remove-Item -LiteralPath $file -Force
        }
    }
    if (Test-Path $ExePath) {
        Remove-Item -LiteralPath $ExePath -Force
    }
    Pop-Location
}
