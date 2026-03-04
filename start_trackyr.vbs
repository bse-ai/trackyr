Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\projects\autarkic\trackyr"
WshShell.Run "pythonw -m trackyr", 0, False
