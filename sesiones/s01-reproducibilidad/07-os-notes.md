## Notas específicas por SO (macOS y Windows)

### Shells y activación

- El shell por defecto en macOS es zsh. Usa `source .venv/bin/activate` para activar entornos.
- Windows PowerShell: `\.venv\Scripts\Activate.ps1`.
- Si usas Cmd: `\.venv\Scripts\activate.bat`.

### Gestores de paquetes

- macOS: Homebrew (`brew`) para Git y Python.
- Windows: Winget (`winget`) es lo más simple. Chocolatey también funciona si lo prefieres.

### Política de ejecución (PowerShell)

Si no puedes ejecutar scripts locales:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### Rutas y saltos de línea

- Windows usa `\` como separador de rutas; macOS/Linux usan `/`.
