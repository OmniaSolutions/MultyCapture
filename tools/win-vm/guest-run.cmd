@echo off
rem ==========================================================================
rem Run the test suite -- and optionally the full installer build -- inside a
rem Windows VirtualBox guest, against the source tree on the host.
rem
rem This file is READ FROM THE SHARED FOLDER and executed in the guest. It is
rem not copied anywhere first, so you can also run it by hand from a Windows
rem shell in the VM:
rem
rem     \\VBoxSvr\workspace\MultyCapture\tools\win-vm\guest-run.cmd test
rem     \\VBoxSvr\workspace\MultyCapture\tools\win-vm\guest-run.cmd build
rem
rem Why a batch file instead of the host generating cmd strings: the host side
rem has to escape through bash -> VBoxManage -> cmd, and that silently
rem mangles quotes. An `if () else ()` swallowed the rest of a line; a quoted
rem path came back as "syntax is incorrect". A real file on disk has no such
rem layer, and it can be read and run by a human.
rem
rem   %1  test | build   (default: test)
rem   %2+ passed through to pytest in `test` mode
rem ==========================================================================
setlocal

rem The repo root, derived from where this file lives -- two levels up from
rem tools\win-vm\. Never a hardcoded drive letter: the auto-mounted Y: exists
rem only in an interactive logon session, and VBoxManage guestcontrol runs in a
rem different one, where only the UNC path resolves.
for %%i in ("%~dp0..\..") do set "SRC=%%~fi"

rem Work in the profile, not C:\ -- listing C:\ is denied for this account.
if not defined MC_WORK set "MC_WORK=%USERPROFILE%\mc-test"
rem The venv lives OUTSIDE the mirrored tree on purpose: robocopy /MIR deletes
rem anything in the destination that is not in the source, so a venv inside
rem MC_WORK would be destroyed and re-downloaded (PySide6, ~hundreds of MB)
rem on every single run.
if not defined MC_VENV set "MC_VENV=%USERPROFILE%\mc-venv"
if not defined MC_PYTHON set "MC_PYTHON=py -3.12"
if not defined ISCC set "ISCC=C:\Program Files\Inno Setup 7\ISCC.exe"

rem tesseract is not installed system-wide here: its installer demands
rem elevation, and guestcontrol cannot answer a UAC prompt. An extracted copy
rem in the profile works identically -- ocr.available() only ever runs the
rem binary -- and needs no admin, no registry and no uninstaller.
if not defined MC_TESSERACT set "MC_TESSERACT=%LOCALAPPDATA%\Tesseract-OCR"
if exist "%MC_TESSERACT%\tesseract.exe" (
  set "PATH=%MC_TESSERACT%;%PATH%"
  rem Same reason as CI: without this, 26 OCR tests skip and the run still
  rem reports success. Set only when the binary is actually here, so a machine
  rem without it gets the warning below instead of a confusing hard failure.
  set "MULTYCAPTURE_REQUIRE_OCR=1"
) else (
  echo WARNING: no tesseract at %MC_TESSERACT% -- 26 OCR tests will skip.
  echo          Extract the UB-Mannheim installer there, or set MC_TESSERACT.
)

set "MODE=%~1"
if not defined MODE set "MODE=test"
shift

set "PY=%MC_VENV%\Scripts\python.exe"

echo == source      %SRC%
echo == work dir    %MC_WORK%
echo == venv        %MC_VENV%
echo == mode        %MODE%

rem ---------------------------------------------------------------------- rem
rem 1. Copy the source in.
rem ---------------------------------------------------------------------- rem
rem Run from a local copy rather than straight off the share: pytest and an
rem editable install write __pycache__, .pytest_cache and *.egg-info next to
rem the source, and on the share that means writing into the host's working
rem tree from Windows. .git is excluded because it is large and unused here;
rem build outputs are excluded so a Linux build does not leak into a Windows
rem one.
echo.
echo == copying source
robocopy "%SRC%" "%MC_WORK%" /MIR /NFL /NDL /NJH /NJS /NP ^
  /XD .git build dist dist-deb dist-win .venv __pycache__ .pytest_cache .settings node_modules ^
  /XF *.pyc
rem robocopy uses exit codes as a bitmask: 0-7 are success (files copied, extra
rem files removed, ...), 8 and above are real failures.
if errorlevel 8 (
  echo ERROR: robocopy failed
  exit /b 1
)

cd /d "%MC_WORK%" || exit /b 1

rem ---------------------------------------------------------------------- rem
rem 2. Virtualenv, created once and reused.
rem ---------------------------------------------------------------------- rem
if not exist "%PY%" (
  echo.
  echo == creating venv ^(first run: this downloads a few hundred MB^)
  %MC_PYTHON% -m venv "%MC_VENV%" || exit /b 1
  "%PY%" -m pip install --quiet --upgrade pip || exit /b 1
)

echo.
echo == installing the package
if "%MODE%"=="build" (
  "%PY%" -m pip install --quiet -e ".[build,test]" || exit /b 1
) else (
  "%PY%" -m pip install --quiet -e ".[test]" || exit /b 1
)

rem ---------------------------------------------------------------------- rem
rem 3. Tests. In build mode too -- freezing code that fails its tests wastes
rem    several minutes on 2 cores before telling you anything useful.
rem ---------------------------------------------------------------------- rem
echo.
echo == running tests
"%PY%" -m pytest %1 %2 %3 %4 %5 %6 %7 %8 %9
if errorlevel 1 (
  echo.
  echo == TESTS FAILED
  exit /b 1
)

if not "%MODE%"=="build" (
  echo.
  echo == TESTS PASSED
  exit /b 0
)

rem ---------------------------------------------------------------------- rem
rem 4. Freeze and build the installer.
rem ---------------------------------------------------------------------- rem
rem The version comes from the one file that holds it, exactly as CI does it --
rem never a literal here. _version.py imports nothing, so this cannot drag in
rem Qt just to read a string.
rem Via a temp file rather than `for /f`: that construct runs its command
rem through a second cmd, which re-parses the quotes around the python -c
rem argument and splits the line in half. A redirect has no such layer.
"%PY%" -c "from multycapture._version import VERSION;print(VERSION)" > "%TEMP%\mc-version.txt" || exit /b 1
set /p VERSION=<"%TEMP%\mc-version.txt"
del "%TEMP%\mc-version.txt" >nul 2>&1
if not defined VERSION (
  echo ERROR: could not read the version from src\multycapture\_version.py
  exit /b 1
)
echo.
echo == version %VERSION%

echo.
echo == freezing with PyInstaller
"%PY%" -m PyInstaller --noconfirm --log-level ERROR packaging\multycapture.spec || exit /b 1

echo.
echo == verifying the frozen bundle
"dist\MultyCapture\MultyCapture.exe" selftest || exit /b 1

if not exist "%ISCC%" (
  echo ERROR: Inno Setup compiler not found at %ISCC%
  echo Set ISCC to its real location.
  exit /b 1
)

echo.
echo == building the installer
"%ISCC%" /DMyAppVersion=%VERSION% installer\windows\multycapture.iss || exit /b 1

rem Hand the artefact back through the share so it can be picked up on Linux.
echo.
echo == copying the installer back to the host
robocopy "%MC_WORK%\installer\windows\Output" "%SRC%\dist-win" *.exe /NFL /NDL /NJH /NJS /NP
if errorlevel 8 (
  echo ERROR: could not copy the installer back to %SRC%\dist-win
  exit /b 1
)

echo.
echo == BUILD OK -- dist-win\MultyCapture-Setup-%VERSION%.exe
exit /b 0
