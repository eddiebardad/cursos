$python = "c:/Users/Eddie Barillas/OneDrive - Veeva Systems, Inc/Desktop/cursos-exe/.venv/Scripts/python.exe"
$script = "gui_app.py"
$spec = "gui_app.spec"

Write-Host "Building standalone executable from $script..."
& $python -m PyInstaller --onefile --noconsole $spec

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build complete. Executable is located in .\dist\gui_app.exe"
} else {
    Write-Host "Build failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}
