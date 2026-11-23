# Windows CRT argument quoting for Start-Process. No shell command evaluation.
function Join-AredokoNativeArguments {
    param([Parameter(Mandatory)][AllowEmptyCollection()][AllowEmptyString()][string[]]$Values)
    $quoted = foreach ($value in $Values) {
        if ($value.IndexOfAny([char[]]@(0, 10, 13, 34)) -ge 0) {
            throw 'Invalid character in an Aredoko launch argument.'
        }
        # A closing quote needs twice the trailing backslashes (e.g. C:\).
        $tail = $value.Length - $value.TrimEnd('\').Length
        '"' + $value + ('\' * $tail) + '"'
    }
    return ($quoted -join ' ')
}
