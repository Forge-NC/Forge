' Forge.vbs — Launch Forge Neural Cortex GUI without any console window.
' Uses the embedded .venv Python so users don't need to install anything.

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

' Set working directory to script location
strDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strDir

' Use embedded venv pythonw.exe (no console)
strPythonW = strDir & "\.venv\Scripts\pythonw.exe"

If FSO.FileExists(strPythonW) Then
    WshShell.Run """" & strPythonW & """ -m forge --fnc", 0, False
Else
    ' Fallback: venv python.exe (will show brief console flash)
    Dim strPython
    strPython = strDir & "\.venv\Scripts\python.exe"
    If FSO.FileExists(strPython) Then
        WshShell.Run """" & strPython & """ -m forge --fnc", 0, False
    Else
        ' Last resort: system python (venv not created yet — run install.py)
        MsgBox "Forge venv not found." & vbCrLf & vbCrLf & _
               "Run install.py first to set up Forge:" & vbCrLf & _
               "  python install.py", vbExclamation, "Forge Setup Required"
    End If
End If
