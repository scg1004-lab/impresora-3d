@echo off
rem Fuerza la actualizacion del Taller AD5X desde GitHub, y cuenta que pasa.
rem
rem Para cuando el programa no se actualiza solo y no se sabe por que. Se
rem copian ESTE fichero y "forzar_actualizacion.py" dentro de la carpeta del
rem Taller -la que tiene dentro "py" y "Taller AD5X.cmd"- y se da doble clic.
rem
rem Pesa dos kilobytes: se manda por correo o por WhatsApp. No hace falta
rem volver a pasar el paquete entero.
setlocal
cd /d "%~dp0"

if not exist "py\python.exe" (
  echo.
  echo  Este fichero no esta en la carpeta del Taller.
  echo.
  echo  Tiene que estar AL LADO de "Taller AD5X.cmd", en la carpeta que
  echo  tambien contiene una carpeta llamada "py".
  echo.
  pause
  exit /b 1
)

if not exist "forzar_actualizacion.py" (
  echo.
  echo  Falta "forzar_actualizacion.py", que viene junto a este fichero.
  echo  Copia los dos.
  echo.
  pause
  exit /b 1
)

"py\python.exe" forzar_actualizacion.py
echo.
pause
