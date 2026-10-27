@echo off
rem Abre un Chrome normal con depuracion remota para que el RPA se conecte a el.
rem Cloudflare Turnstile rechaza el navegador que lanza Playwright, pero acepta
rem un Chrome abierto por el usuario. Deja esta ventana de Chrome abierta mientras
rem corre el RPA (main.py --connect-chrome, o la casilla en la interfaz web).
rem
rem Se usa un perfil propio (chrome-profile) porque Chrome no permite la
rem depuracion remota sobre el perfil predeterminado.

set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

start "" %CHROME% --remote-debugging-port=9222 --user-data-dir="%~dp0chrome-profile" https://catalogo-vpfe.dian.gov.co/User/SearchDocument
