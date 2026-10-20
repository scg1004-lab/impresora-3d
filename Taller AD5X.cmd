@echo off
rem Arranca el Taller AD5X. El mismo fichero sirve en los dos sitios:
rem   - en el paquete portatil, con el Python de la carpeta py\
rem   - en el ordenador donde se programa, con el entorno .venv\
setlocal
cd /d "%~dp0"

set "PY="
if exist "py\python.exe" set "PY=py\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

if not defined PY (
  echo.
  echo  No encuentro ningun Python al lado de este fichero.
  echo.
  echo  Si acabas de descomprimir el ZIP: copia la carpeta ENTERA,
  echo  no solo este acceso directo. Al lado tiene que estar "py".
  echo.
  echo  Si estas en el ordenador donde se programa: este lanzador va
  echo  en la raiz del proyecto, al lado de ".venv".
  echo.
  pause
  exit /b 1
)

"%PY%" run.py

rem Solo se para la ventana si algo ha ido mal, para que se pueda leer.
rem Cuando run.py termina bien -porque ya estaba abierto, o porque has
rem cerrado el programa- no hay nada que contar.
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)
