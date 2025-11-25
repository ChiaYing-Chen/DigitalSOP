$BaseDir = Get-Location
$StaticDir = Join-Path $BaseDir "static"
$JsDir = Join-Path $StaticDir "js"
$CssDir = Join-Path $StaticDir "css"
# bpmn-js css expects fonts in ../font/ relative to the css file location (if css is in css/)
# actually standard dist is assets/bpmn-font/css/.. and assets/bpmn-font/font/..
# If we put css in static/css/bpmn.css, and it references ../font/bpmn.woff, it looks for static/font/bpmn.woff
$FontsDir = Join-Path $StaticDir "font"

New-Item -ItemType Directory -Force -Path $JsDir | Out-Null
New-Item -ItemType Directory -Force -Path $CssDir | Out-Null
New-Item -ItemType Directory -Force -Path $FontsDir | Out-Null

$Assets = @(
    @{ Url = "https://unpkg.com/react@18/umd/react.development.js"; Path = "js/react.js" },
    @{ Url = "https://unpkg.com/react-dom@18/umd/react-dom.development.js"; Path = "js/react-dom.js" },
    @{ Url = "https://unpkg.com/@babel/standalone/babel.min.js"; Path = "js/babel.js" },
    @{ Url = "https://cdn.tailwindcss.com"; Path = "js/tailwindcss.js" },
    @{ Url = "https://unpkg.com/bpmn-js@14.0.0/dist/bpmn-modeler.development.js"; Path = "js/bpmn-modeler.js" },
    @{ Url = "https://unpkg.com/bpmn-js@14.0.0/dist/bpmn-navigated-viewer.development.js"; Path = "js/bpmn-viewer.js" },
    @{ Url = "https://unpkg.com/bpmn-js@14.0.0/dist/assets/diagram-js.css"; Path = "css/diagram-js.css" },
    @{ Url = "https://unpkg.com/bpmn-js@14.0.0/dist/assets/bpmn-font/css/bpmn.css"; Path = "css/bpmn.css" },
    @{ Url = "https://unpkg.com/bpmn-js@14.0.0/dist/assets/bpmn-font/font/bpmn.woff"; Path = "font/bpmn.woff" },
    @{ Url = "https://unpkg.com/bpmn-js@14.0.0/dist/assets/bpmn-font/font/bpmn.woff2"; Path = "font/bpmn.woff2" },
    @{ Url = "https://unpkg.com/bpmn-js@14.0.0/dist/assets/bpmn-font/font/bpmn.ttf"; Path = "font/bpmn.ttf" },
    @{ Url = "https://unpkg.com/bpmn-js@14.0.0/dist/assets/bpmn-font/font/bpmn.eot"; Path = "font/bpmn.eot" },
    @{ Url = "https://unpkg.com/bpmn-js@14.0.0/dist/assets/bpmn-font/font/bpmn.svg"; Path = "font/bpmn.svg" }
)

foreach ($Asset in $Assets) {
    $FilePath = Join-Path $StaticDir $Asset.Path
    Write-Host "Downloading $($Asset.Url) to $FilePath..."
    try {
        Invoke-WebRequest -Uri $Asset.Url -OutFile $FilePath
        Write-Host "Success."
    }
    catch {
        Write-Error "Failed to download $($Asset.Url): $_"
    }
}

Write-Host "All assets downloaded."
