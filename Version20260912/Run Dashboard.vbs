' Launches the dashboard without a big console window in your face.
' A minimized window still appears in the taskbar in case anything
' goes wrong and you need to check the messages.
Set fso = CreateObject("Scripting.FileSystemObject")
scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)

Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = scriptFolder
shell.Run """" & scriptFolder & "\run_dashboard.bat""", 7, False
