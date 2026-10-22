PONDO TILL  ->  ZIMRA FISCALISATION   (FiscalStackZW engine)
=================================================================

WHAT THIS FOLDER IS
  The FiscalStackZW engine (FiscalStackZW.dll and its helpers) plus PondoFiscalBridge.exe,
  the small program Pondo uses to talk to it. Pondo starts the bridge by itself – you never
  open anything in here. Keep the x64 and x86 folders: the engine needs them.

  The engine keeps its own fiscal records in C:\ProgramData\FiscalStackZW (receipts, fiscal
  day, counters, waiting receipts) and the device certificates in C:\FiscalStackZW certificates.
  NEVER delete those two folders. Back them up with the Pondo backups.

WHAT PONDO DOES NOW
  * Every till sale becomes a ZIMRA fiscal tax invoice with the ZIMRA QR code on the slip.
  * Every till refund becomes a ZIMRA credit note that points to the original slip.
  * No internet? Keep selling. The slip is signed on this computer (it still gets its QR code)
    and waits. "Send waiting receipts" on the Fiscal page sends them when the line is back.
  * If ZIMRA refuses a slip, the sale is still saved. The slip says "NOT YET FISCALISED" and
    the Fiscal page lists it with the reason and a "Try again" button.
  * The fiscal day opens by itself at the first sale. At night, after the last till is closed,
    a Supervisor presses "Close fiscal day (Z report)" on the Fiscal page.
  * The DEMO copy of Pondo never fiscalises.

SETTING IT UP (the Manager login – menu: Fiscal (ZIMRA) -> Setup)
  Do it all on the ZIMRA TEST server first.

  1. Mode: choose "ZIMRA TEST", check the shop address, type the HS code your accountant
     gives you for bakery products, Save. (This writes the engine's config.ini.)
  2. Licence: paste the FiscalStackZW licence key for this computer -> Apply licence.
     Without it every fiscal call is refused ("License required ...").
  3. Device: type the TEST device ID, serial number and activation key from ZIMRA, then press
     in this order:  Make certificates -> Check certificates -> Register with ZIMRA -> Apply.
  4. Open Fiscal (ZIMRA): you should see the fiscal day, "Licence OK" and "ZIMRA online".
  5. Test a whole day: open a till, sell (cash, EcoCash, ZiG, a by-the-kg item), do a refund,
     pull the network cable and sell again (it says "waiting"), plug it back and press
     "Send waiting receipts", close the till, then "Close fiscal day (Z report)".
     Scan a slip's QR code with a phone – it must open ZIMRA's verification page.
  6. Only then: get the LIVE device from ZIMRA, choose LIVE (type LIVE in the box), Save,
     and do step 3 again with the LIVE device details (or Apply with the certificate folder
     you were given). Check "Tax codes" with the GetConfig support button after registering.

IF SOMETHING GOES WRONG
  * Fiscal page -> the "Why" column says what ZIMRA or the engine answered.
  * Setup -> Support tools: GetStatus, GetConfig, GetCardDetails ... show the raw answers.
  * Fiscal -> Engine journal: every call Pondo made and the full answer.
  * data\fiscal_engine_log.txt: the engine's own log. The engine also writes Logs\ in this folder.
  * If PondoFiscalBridge.exe is missing, Pondo rebuilds it from PondoFiscalBridge.cs with
    the C# compiler that comes with Windows (or double-click build_bridge.bat).
  * Needs .NET Framework 4.8 (built into Windows 10 and 11).

GOOD TO KNOW
  * The receipt is in US$. ZiG cash is counted in US$ at the day's rate, as on the till.
    The engine reports every payment to ZIMRA as "Cash" (EcoCash and card too) – that is how
    this engine works.
  * One fiscal device serves all tills (Till 1, Till 2 ...). Invoice numbers are the slip
    numbers (T1-00012). They may never be used twice on the device.
  * ZIMRA allows a fiscal day of at most 24 hours – close it every night.
  * NLog.config in this folder sends the engine's log to the engine supplier's Seq server
    (axiscontrolhub.co.zw) as well as to the Logs folder. Ask the supplier if you want that off.
