Set objFSO = CreateObject("Scripting.FileSystemObject")
Set objShell = CreateObject("WScript.Shell")

strDesktop = objShell.SpecialFolders("Desktop")
strTarget = objFSO.GetAbsolutePathName("run.bat")
strIcon = objFSO.GetAbsolutePathName("assets\images\cipsa.ico")

Set objShortcut = objShell.CreateShortcut(strDesktop & "\G360 App.lnk")
objShortcut.TargetPath = strTarget
objShortcut.WorkingDirectory = objFSO.GetParentFolderName(strTarget)
objShortcut.Description = "G360 App"
objShortcut.IconLocation = strIcon
objShortcut.Save()

WScript.Echo "Atajo creado en el escritorio: G360 App.lnk"
