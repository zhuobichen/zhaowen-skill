' Start the daily archiver hidden (no console window). Path resolved from this file's folder.
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "cmd /c """ & dir & "\daily.cmd""", 0, False
