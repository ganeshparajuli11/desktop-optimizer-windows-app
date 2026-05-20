Set WshShell = CreateObject("WScript.Shell")
script = WScript.ScriptFullName
folder = Left(script, InStrRev(script, "\"))
WshShell.Run "pythonw " & folder & "sysctl.py", 0, False
