# FiscalStackZW — ZIMRA Fiscalisation Integration Guide

**Engine:** `FiscalStackZW.dll` (.NET Framework 4.8, x86/x64 via AnyCPU)
**Reference consumer:** `FiscalStackZWTest.exe` (interactive test harness in this package)
**Reference POS integration:** `FiscalStackZWPOS.App` (a WPF POS that wired this engine end-to-end)
**Document revision:** v2 — rewritten against the actual engine source (2026-10-07)

> This file serves **two** purposes:
> 1. A complete reference manual for **human integrators** wiring `FiscalStackZW.dll` into a POS.
> 2. A self-contained **agent prompt** — an AI coding agent can read this document and produce a
>    compliant integration without any other context. The agent-facing instructions are
>    delimited in [Section 23](#23-agent-prompt-integrate-the-dll-into-a-client-pos).

---

## Table of contents

1. [What the engine is — and is not](#1-what-the-engine-is--and-is-not)
2. [Runtime layout](#2-runtime-layout)
3. [Configuration keys](#3-configuration-keys)
4. [The response envelope](#4-the-response-envelope)
5. [Threading and instance rules](#5-threading-and-instance-rules)
6. [Licensing](#6-licensing)
7. [TEST vs PRODUCTION](#7-test-vs-production)
8. [Device lifecycle (onboarding)](#8-device-lifecycle-onboarding)
9. [Fiscal day lifecycle](#9-fiscal-day-lifecycle)
10. [Submitting a sale (Transact/TransactM/TransactMExt/SubmitReceipt)](#10-submitting-a-sale)
11. [Items XML](#11-items-xml)
12. [Currencies XML](#12-currencies-xml)
13. [Buyer data rules](#13-buyer-data-rules)
14. [VAT computation rules](#14-vat-computation-rules)
15. [The receipt JSON sent to ZIMRA](#15-the-receipt-json-sent-to-zimra)
16. [Validation & error-handling contract](#16-validation--error-handling-contract)
17. [Signature hash chain](#17-signature-hash-chain)
18. [QR verification link](#18-qr-verification-link)
19. [FDMS transport (ZimraGateway)](#19-fdms-transport-zimagateway)
20. [Offline behaviour, queue and recovery](#20-offline-behaviour-queue-and-recovery)
21. [Lookups and reporting](#21-lookups-and-reporting)
22. [Reference integration (how FiscalStackZWPOS.App does it)](#22-reference-integration-how-fiscalstackzwposapp-does-it)
23. [Agent prompt: integrate the DLL into a client POS](#23-agent-prompt-integrate-the-dll-into-a-client-pos)
24. [Deployment into your POS](#24-deployment-into-your-pos)
25. [Package contents](#25-package-contents)
26. [Gotchas checklist](#26-gotchas-checklist)

---

## 1. What the engine is — and is not

FiscalStackZW is a **server-side, offline-first fiscal engine** for ZIMRA-compliant
invoicing in Zimbabwe:

- Your C# POS calls a plain method. The engine takes care of everything fiscal:
  RSA device signing, FDMS (ZIMRA) submission, the ZIMRA QR deep link, the local
  receipt store, the offline queue, fiscal-day state and reconnection.
- **There is no UI.** All methods return a JSON envelope string (Section 4).
- **There is no UI branding** to copy. The POS keeps its own look; the engine only
  produces data (XML/JSON) plus the receipt/card payloads a POS prints or shows.
- It is **not a standalone server** — it is a callable DLL class
  (`FiscalStackZW.FiscalStackZW`).
- It never stops the POS: transport failures, an unreachable FDMS, or a missing
  certificate degrade to **local fiscalisation + a pending queue**, never a fatal error.

### Golden rules (the engine enforces these; your integration must respect them)

1. **One engine instance, serialised calls.** The engine is not internally
   thread-safe for concurrent business calls — use a single instance and a gate
   (Section 5). The reference POS enforces a 15 s gate timeout.
2. **FDMS counters only advance on FDMS confirmation.** A receipt that FDMS
   rejects (or Red-flags) never becomes the chain head and never advances the
   global number locally for re-acceptance purposes (except Red, which consumed
   the number on the server — the engine then steps the local global forward but
   keeps the chain on the last *accepted* receipt).
3. **Read `Data` twice.** `Data` in the envelope is a JSON or XML **string**,
   never an object. Indexing `o["Data"]["field"]` yields null; parse it first
   (Section 4, Section 22).
4. **The caller's amounts are advisory.** Item prices × quantities and the
   device tax config are authoritative; VAT is recomputed from them and any
   disagreement is surfaced as *warnings*, not errors.
5. **Never fabricate FDMS state.** When FDMS is unreachable the engine says so
   (status `zimraReachable:false`, message "offline - local snapshot only")
   rather than pretending the server accepted anything.

---

## 2. Runtime layout

The engine keeps three things on disk:

| Item | Location | Purpose |
|------|----------|---------|
| `config.ini` | `%ProgramData%\FiscalStackZW\config.ini` first, else next to the calling EXE | Identity, tax, environment, licence, mode |
| Certificates | `C:\FiscalStackZW certificates\<deviceID>\` (config `CERTIFICATEFOLDER`; a legacy non-device subfolder is honoured) | Device key pair + CA/server chain + `manifest.json` used for signing and mTLS |
| `FiscalStackZW.sqlite` | `%ProgramData%\FiscalStackZW\` | Local store: every sale, day state, counters, offline queue, counter-change audit log |

All are created automatically with working defaults on first use.

Logs go to the engine's log folder via `EngineLog` (see `%ProgramData%\FiscalStackZW\logs`
or the engine config). The engine logs the *effective* decision for every FDMS call —
these logs are the first place to look when diagnosing RED/reject behaviour.

### Certificate folder contents (per device)

- `device.pfx` + `device.crt` — the device key pair (mTLS client auth).
- `ca.crt`, `server.crt`, `intermediate-ca.crt`, `intermediate-ca-1.crt` — the chain presented for mTLS.
- `manifest.json` — serial, deviceID, taxpayer name/TIN/VAT, valid-till, thumbprints.
  `GetCertificateDetails` / `VerifyCertificateDetails` read **this file**, not cached config.

---

## 3. Configuration keys

All identity, tax, environment, licence and mode settings live in `config.ini`.
`GetConfig()` (`Code:"1"`) returns the full effective snapshot; `GetDeviceStatus()`
reports the applied state. Keys an integrator may set:

| Key | Meaning |
|-----|---------|
| `SERIALNUMBER`, `DEVICEID` | Device identity (used on the certificate claim) |
| `TAXPAYERNAME` (alias `COMPANYNAME`), `TAXPAYERTIN`, `VATNUMBER` | The trader (your customer) |
| `DEVICEBRANCHNAME`, `DEVICEPROVINCE`, `DEVICESTREET`, `DEVICEHOUSENO`, `DEVICECITY` | Shop name/address printed on the receipt |
| `VATFLAG` | `1` = item prices **include** VAT (default). `0` = tax-exclusive |
| `VATA` | Standard VAT fraction (default `0.155`); `VATB`..`VATF` secondary rates (used in `GetConfig` snapshot and Z-report counters) |
| `TAXIDSTANDARDRATED`, `TAXIDZERORATED`, `TAXIDEXEMPTED` | ZIMRA tax-bucket IDs. Engine defaults: standard `517`, zero `2`, exempt `3` (`GetConfig`)/`1` (compliance fallback). **Set these per environment and confirm with `GetConfig()`** |
| `ZIMRASERVER` | FDMS API base (default `https://fdmsapi.zimra.co.zw`) |
| `VERIFICATIONSERVER`, `QRURL` | Base of the QR deep link (default `https://fdms.zimra.co.zw`) |
| `POSENVIRONMENT` | `TEST` or `PROD` (display/logging; server choice is `ZIMRASERVER`) |
| `LICENSEKEY`, `LICENSEMODE`, `LICENSEGRACE` | Licence (Section 6) |
| `CERTIFICATEFOLDER`, `CERTIFICATEVALIDTILL` | Where certs live / claim validity |
| `DEVICEOPERATINGMODE` | `ONLINE` or `OFFLINE` (drives `SubmitClient` mode) |
| `DEVICEMODELNAME` | FDMS header; default `Virtual Server` |
| `DEVICEMODELVERSIONNO`, `APIVERSION` | FDMS header; default `v1` |
| `TIMEOUT` | HTTP timeout seconds; default `90`, clamped to `300` |
| `WALKINBUYERNAME`, `WALKINBUYERTIN`, `WALKINBUYERTRADENAME` | Anonymous-buyer defaults (`Walk In Customer`, `0000000000`, `Walk In`) |
| `DEFAULTITEMNAME` | Item display-name fallback (default `Item`) |
| `RECEIPTPRINTFORM` | Receipt print form id (default `Receipt48`) |

Environment transitions are guarded: the engine records `ENVIRONMENT_TRANSITION` /
`LAST_ENVIRONMENT`; `CheckEnvironmentTransition()` tells you whether a TEST⇄PROD
change requires **re-registration**, and `ClearEnvironmentTransitionFlag()` acknowledges
it (administrator action).

> `GetConfig()` while online refreshes from the FDMS `getConfig` endpoint and returns
> a failure (`ZIMRA getConfig unavailable: device configuration could not be verified`)
> if FDMS cannot be reached. Offline it returns the local snapshot with
> `zimraSource: "ZIMRA offline / no certificate - local snapshot only"`.

---

## 4. The response envelope

Every public method returns exactly one JSON string:

```json
{ "Code": "1", "Message": "human readable", "Data": "string-or-" }
```

- `Code == "1"` ⇒ success. Anything else ⇒ failure; `Message` explains (verbatim texts
  catalogued in Section 16).
- `Data` is a **string**. It may be:
  - an XML document string (receipt `ReceiptData`/`FDMSData`, `DeviceStatus`, card details, Z-report, `<License>`, `<Summary>`…),
  - a JSON document string (GetStatus, GetConfig, SubmitPendingQueue batch, OpenDay, SubmitReceipt payload, CheckLicense…),
  - `""` or `"{}"` when there is nothing.
- There is **no `Code:"1"` with structured failure inside `Data`**: success is success.

### Parsing rule (critical)

Because `Data` is a string, parse twice:

```csharp
var o = JObject.Parse(raw);                 // 1. envelope
if (o["Code"]?.ToString() != "1") return null;
string data = o["Data"]?.ToString() ?? "";  // 2. payload string
if (data.TrimStart().StartsWith("{"))
    return JObject.Parse(data);             // JSON payload
// else: XML payload — parse with XDocument/XElement
```

Indexing `o["Data"]["field"]` directly silently yields `null` and every field read
fails. (The reference POS wrapper `EnvelopePayload` bakes this in — Section 22.)

### Success-shape summary by method

| Method | `Data` type | Payload contents |
|--------|-------------|------------------|
| `Transact*`, `SubmitReceipt` | XML | `ReceiptData` (incl. `FDMSData` with the QR) — Section 10 |
| `GetStatus` | JSON | `FiscalDayStatusResponse` — Section 9 |
| `GetConfig` | JSON | full configuration snapshot — Section 3 |
| `GetDeviceStatus` | XML | `DeviceStatus` — Section 21 |
| `GetCardDetails` | XML | card/trader XML — Sections 21/22 |
| `GetLicense` | XML | `<License><Status>…` — Section 6 |
| `SetLicense` | XML | `<License><Status>…` — Section 6 |
| `CheckLicense` | JSON | `{allowed,inGrace,graceDaysLeft,state,mode,serial,message}` — Section 6 |
| `OpenDay` | JSON | `{operationID,fiscalDayNo,fiscalDayOpened,zimraStatus}` — Section 9 |
| `SubmitPendingQueue` | JSON | `{total,submitted,failed,stillPending,mode,items[]}` — Section 20 |
| `GetTransaction(s)` | JSON | queued/processed transaction row — Section 21 |

---

## 5. Threading and instance rules

- **One engine instance per process**, created once: `new FiscalStackZW.FiscalStackZW()`.
- Engine calls are **not internally re-entrant** for business operations. Serialise them.
- Wrap every call with a gate. The reference POS uses `SemaphoreSlim(1,1)` with a
  **15 second** timeout and returns a friendly envelope on timeout — never call the
  engine on the UI thread (see Section 22 for the exact wrapper).

```csharp
private readonly SemaphoreSlim gate = new SemaphoreSlim(1, 1);
private string Call(Func<string> fn)
{
    if (!gate.Wait(15000)) return "{\"Code\":\"0\",\"Message\":\"Engine busy (timeout). Try again.\",\"Data\":\"\"}";
    try { return fn(); }
    catch (Exception ex) { return "{\"Code\":\"0\",\"Message\":\"Engine exception: " + ex.Message + "\",\"Data\":\"\"}"; }
    finally { gate.Release(); }
}
```

The engine itself already serialises the critical counter/chain section with its own
fiscal lock (a 10 s wait; on timeout it returns
`Transaction error: engine busy (counter lock timeout). Try again.`), so your gate
protects your POS UI, not the engine’s internals.

---

## 6. Licensing

FiscalStackZW is licensed **per serial number** (per till/device).

- Licence keys are issued by the **FiscalStackZW team**; the generator is never shipped.
  Never generate or infer a key.
- Without a valid key every fiscal method returns a licence gate error such as
  `License required: activation service is unavailable. Check the LICENSEMODE setting.`
- Apply a key in code with `SetLicense(key)` or in `config.ini` (`LICENSEKEY=`).
  The shipped `config.ini` deliberately contains **no** `LICENSEKEY`, so fiscal calls
  stay locked until a real key is applied.
- The engine verifies the key **locally** with an embedded public key; it never phones
  home. A valid licence keeps working offline.

### Licence API

| Method | Returns |
|--------|---------|
| `SetLicense(string key)` | Envelope; `Data` = `<License><Status>License Status: Active|Inactive</Status><CompanyName>…</CompanyName><Message>…</Message></License>`. Empty key ⇒ `Failed to set license: License key is empty`. Missing activation service ⇒ `License service unavailable. Restart the application and try again.` |
| `CheckLicense()` | JSON `{"allowed","inGrace","graceDaysLeft","state","mode","serial","message"}`. Callers gate the till on `allowed==true`. |
| `GetLicense()` | Envelope; `Data` = same `<License>` XML with status/company/expiry used by the reference POS to show the till’s licence. |

### POS pattern (from the reference app)

- Gate the whole UI: `LicenseAllowed()` (wraps `CheckLicense`; till usable only when
  `allowed == true`). Show a blocking onboarding/licence screen otherwise.
- Show a loud, non-blocking banner while inside grace:
  `LicenseGraceNotice()` → “LICENSE GRACE: your license has expired and this till will
  stop working. N days remaining. Renew now.”
- Provide a Settings field to paste the customer’s licence key and apply via `SetLicense`.

---

## 7. TEST vs PRODUCTION

| | TEST | PRODUCTION |
|---|---|---|
| `ZIMRASERVER` | `https://fdmsapitest.zimra.co.zw` | `https://fdmsapi.zimra.co.zw` |
| `POSENVIRONMENT` | `TEST` | `PROD` |
| Standard-rate tax id | `517` | `515` |
| Zero-rate tax id | `2` | `2` |
| Exempt tax id | `3` | `1` |
| Effect | Demo invoices, no tax obligation | Real fiscal invoices |

Mechanics and rules:

- Switch by writing `ZIMRASERVER` / `POSENVIRONMENT` (and the tax ids) into
  `config.ini` and then **creating a fresh engine instance** (and, after
  registration/apply, invalidating the gateway certificate cache — the engine does
  this automatically inside `GenerateDeviceCertificates`/`ApplyDeviceSettings`).
- Changing a **live till** between environments is guarded by ZIMRA: after a switch,
  `CheckEnvironmentTransition()` returns `needsReregistration:true`; clearing
  `ENVIRONMENT_TRANSITION` is an administrator action.
- **Developer rule:** build against TEST first, generate device certificates,
  run a full open-day → sales → close-day cycle, then flip to PROD and re-register.

---

## 8. Device lifecycle (onboarding)

Onboarding is **once per till**. The reference POS drives it with a wizard
(`CertificateWizardFlow`) and a Settings “Device” tab.

### Step 1 — Generate device certificates (TEST)

```csharp
public string GenerateDeviceCertificates(string serialNumber, string activationKey, string deviceID)
```

- Creates the device folder `C:\FiscalStackZW certificates\<deviceID>\` with
  device/CA/server certificates + `manifest.json`, then writes `SERIALNUMBER`,
  `DEVICEID`, `TAXPAYERNAME`, `TAXPAYERTIN`, `VATNUMBER`, `CERTIFICATEFOLDER` into
  config and re-initialises the gateway for the new identity.
- Refuses to regenerate an existing folder:
  `Certificates already generated for device '<id>' at '<folder>'. Delete that folder before regenerating.`
- Always pass a **fresh** key/serial for TEST vs PROD.

### Step 1b — Verify (optional, before/after import)

```csharp
public string VerifyCertificateDetails(string serialNumber, string activationKey, string deviceID, string certificateFolder = "")
```

Reads **only** the `manifest.json` on disk (never cached config) and cross-checks the
entered serial/deviceID. Returns `valid`, taxpayer details, thumbprints, `certificateValidTill`
and a warning when the entered identity does not match the manifest.

### Step 2 — Register with ZIMRA FDMS

```csharp
public string RegisterDeviceWithZimra(string activationKey, string serialNumber, string deviceID)
```

Full flow: `verifyTaxpayerInformation` → local CSR → `registerDevice` → `getConfig` →
`getServerCertificate` → store the FDMS-issued certificate. Online `submitReceipt` only
fires once certificates are available, so a receipt’s QR deep link only verifies after
this completes.

> **Argument-order gotcha:** the engine signature is `(activationKey, serialNumber, deviceID)`.
> The reference POS exposes a user-friendly `RegisterDeviceWithZimra(serial, key, deviceId)`
> wrapper that **remaps** the arguments before calling the engine. Keep the engine order correct.

### Step 3 — Apply device settings

```csharp
public string ApplyDeviceSettings(string certificateFolder, string deviceID = "", string serialNumber = "", string activationKey = "")
```

Points the engine at an existing certificate folder, syncs device identity/taxpayer
details from its `manifest.json` into config, and re-initialises the gateway, device
config, per-device DB and licence. This is the step used when installing a **new device**
or pointing an app at a pre-made PROD certificate.

### Step 4 — Confirm

`GetCertificateDetails()` → envelope; `Data` is the `manifest.json` object, or a
`{generated:false, certificateFolder, serialNumber, deviceID, documentation}` hint when
nothing is generated yet.

---

## 9. Fiscal day lifecycle

### GetStatus — what the day looks like

```csharp
public string GetStatus()
```

- **Online** (`ZIMRASERVER` reachable + certificate present): calls FDMS `getStatus`.
  On failure returns `ZIMRA fiscal status unavailable: <code>: <message>` (never a
  fabricated snapshot). On success `Data` is JSON:
  `{ FiscalDayStatus, FiscalDayReconciliationMode, LastReceiptGlobalNo, LastFiscalDayNo,
     zimraReachable:true, zimraSource:"ZIMRA FDS verified live",
     fiscalDayServerSignature:{ certificateThumbprint, hash, signature } }`.
  The engine also reconciles local counters forward-only from the server values.
- **Offline / no certificate**: returns local state labelled
  `zimraReachable:false, zimraSource:"no ZIMRA certificate installed - local snapshot only"`.
- Fiscal day statuses you will see: `FiscalDayOpened`, `FiscalDayClosed`,
  `FiscalDayCloseFailed`, `FiscalDayCloseInitiated` (closing in progress).

### OpenDay

```csharp
public string OpenDay()
```

- Computes the next day number (`lastFiscalDayNo + 1`) after aligning with FDMS
  (via `getStatus`), calls FDMS `openDay`, confirms via `getStatus`, refreshes counters.
- **Recovery:** if the server day is stuck in `FiscalDayCloseFailed`, the engine first
  attempts a best-effort `closeDay` + `ConfirmDayClosed` against the *server’s* day number,
  and only advances to `serverDay + 1` after the close is **confirmed**. If that close
  fails it returns
  `OpenDay failed: ZIMRA fiscal day N is stuck (FiscalDayCloseFailed) and the best-effort closeDay <outcome>. Fix the day before opening the next one.`
- **Reject vs offline:** a genuine FDMS rejection (`IsZimraRejection`) returns
  `OpenDay failed: …`. A transport fault / 5xx / missing certificate **degrades to a
  local open** so the POS keeps working (`zimraStatus: "ZIMRA unreachable; fiscal day
  opened locally (offline fallback): …"`).
- On success `Data` JSON: `{ operationID, fiscalDayNo, fiscalDayOpened, zimraStatus }`.

### CloseDay / ZReport

```csharp
public string CloseDay()
public string ZReport()
```

- `CloseDay` transmits the day’s counters + `fiscalDayDeviceSignature` to FDMS. ZIMRA
  close is **asynchronous** — a 200 only means “accepted”. The engine polls
  `getStatus` until the day is `FiscalDayClosed` (budget ~90 s at 3 s intervals).
  Outcomes: success, `CLOSEFAILED` (with `MapFiscalCode` text; see Section 19), or
  `CLOSETIMEOUT` (`ZIMRA has not confirmed fiscal day closure within 90s … Day remains open - do NOT open a new day yet.`).
- `ZReport` in online mode **first closes the day** via `CloseDay` (honest failure:
  `ZReport failed: fiscal day could not be closed on ZIMRA FDMS. …`), then emits the
  Z-report XML (`<ZREPORT>` with counters + `Signature{CurrentHash, PreviousHash, Signature}`)
  and returns `Data` = `<FiscalDayReport>` with the day’s counters. It resets the receipt
  counter to 0 for the next day but **does not open the next day**.

### DiscardCounters

```csharp
public string DiscardCounters()
```

Resets the local day/global/hash/status to a closed day “0” (`allowRegression`).
Use to void an empty/unused open day **before** any sale. It only affects local
counters; it cannot un-close a day already confirmed on FDMS.

### Day-state machine the POS should follow

1. Start of day: if `GetStatus` shows closed, `OpenDay()`. (The reference POS also does
   this **automatically when a sale is attempted** on a closed day — Section 22.)
2. All day: every sale → `TransactM`/`SubmitReceipt` (Section 10).
3. Close: `CloseDay()` (or `ZReport()` which closes and prints) at end of day.
4. After reconnect: `SubmitPendingQueue(200)` then `SubmitFile(day, date)` (Section 20).

---

## 10. Submitting a sale

### Method comparison (exact signatures)

```csharp
// Recommended full fiscal sale (multi-currency aware)
public string TransactM(string Currency, string CustomerEmail, string InvoiceNumber,
    string CustomerRegisteredName, string CustomerVATNumber, string CustomerFullAddress,
    string CustomerTelephoneNumber, string CustomerTIN, string InvoiceAmount,
    string InvoiceTaxAmount, string InvoiceFlag, string InvoiceComment,
    string OriginalInvoiceNumber, string ItemsXML, string Currencies)

// Extended: structured buyer address + trade name + linked-returns reference
public string TransactMExt(string Currency, string InvoiceNumber, string InvoiceAmount,
    string InvoiceTaxAmount, string InvoiceFlag, string InvoiceComment,
    string OriginalInvoiceNumber, string ItemsXML, string Currencies, string CustomerEmail,
    string CustomerRegisteredName, string CustomerTradeName, string CustomerVATNumber,
    string CustomerTIN, string CustomerTelephoneNumber, string CustomerFullAddress,
    string buyerProvince, string buyerStreet, string buyerHouseNo, string buyerCity,
    string refDeviceId, string refReceiptGlobalnumber, string refFiscalDay)

// Legacy (no currency/TIN): currency is forced to ZWL
public string Transact(string BranchName, string InvoiceNumber, string CustomerRegisteredName,
    string CustomerVATNumber, string CustomerFullAddress, string CustomerTelephoneNumber,
    string CustomerBPN, string InvoiceAmount, string InvoiceTaxAmount, string InvoiceFlag,
    string InvoiceComment, string OriginalInvoiceNumber, string ItemsXML)

// Thin online-FDMS wrapper (equivalent fiscal build; response additionally reports
// fiscalCloudStatus / receiptID / operationID / message)
public string SubmitReceipt(string Currency, string InvoiceNumber, string CustomerRegisteredName,
    string CustomerVATNumber, string CustomerFullAddress, string CustomerTelephoneNumber,
    string CustomerTIN, string CustomerEmail, string InvoiceAmount, string InvoiceTaxAmount,
    string InvoiceFlag, string InvoiceComment, string OriginalInvoiceNumber, string ItemsXML,
    string Currencies)
```

All four run the same `TransactInternal` pipeline. Use `TransactM` (as the reference POS
does) unless you need structured addresses/linked returns (`TransactMExt`).

### Invoice flag

| `InvoiceFlag` | Meaning | Sign of amounts | `DefaultReceiptNotes` if empty |
|---------------|---------|-----------------|-------------------------------|
| `"01"` | Fiscal invoice (sale) | + | (none) |
| `"02"` | **Credit note** | **negative** (price, line total, tax, total) | `Credit note` |
| `"03"` | Debit note | + | `Debit note` |

Anything else, or empty, is rejected:
`Transaction error: Internal validation - Missing Information, InvoiceFlag is required. Valid options 01 for Invoice 02 for Credit Note and 03 for Debit Note`

Credit/debit notes **must** reference the original receipt. When
`OriginalInvoiceNumber` is supplied the engine looks the original up and fills
`creditDebitNote.{deviceID, receiptGlobalNo, fiscalDayNo}`; a reference that cannot be
resolved is rejected pre-submission with `RCPT015`.

### Pre-validation (verbatim error strings)

The engine rejects early — before any queueing, storing or transmission — with:

- Missing invoice number: `Transaction error: Internal validation - Missing Information, Invoice number is required`
- Non-numeric `InvoiceAmount`: `Transaction error: Internal validation - Invalid Invoice Amount. Verify if InvoiceAmount is present on the invoice is a valid number and is being supplied to the Device`
- Non-numeric `InvoiceTaxAmount`: `Transaction error: Internal validation - Invalid InvoiceTaxAmount. Verify if InvoiceTaxAmount is present on the invoice is a valid number and is being supplied to the Device`
- No items: `Transaction error: Internal validation - at least one item line is required`
- Items XML > 100 KB: `Items XML exceeds maximum size (100KB)`
- Duplicate invoice number (checked **inside** the engine’s fiscal lock, so
  concurrent duplicates are caught):
  `Transaction error: Internal validation - invoice number '<n>' was already used on this device. The POS generates timestamp-based numbers; a collision means this invoice was already processed or attempted. (internal duplicate check, NOT submitted to ZIMRA FDMS)`

> **Duplicate-invoice rule for integrators:** reuse an invoice number across days or
> retries is impossible by design — generate timestamp-based numbers (the reference POS
> does `DateTime`-based numbering) and persist+reuse the returned receipt on retry
> instead of retransmitting.

### Why the POS can always keep selling

Inside the pipeline the engine decides, from the **live FDMS probe** at transact time
(`TryAlignDayWithZimra`): if FDMS is reachable with a certificate the receipt is
numbered from the **FDMS sequence** and submitted immediately; otherwise it is numbered
from the **local sequence**, stored as `pending`, and renumbered onto the FDMS sequence
at sync (`SubmitPendingQueue`). Only an FDMS **confirmation** advances the FDMS counters
and chain head.

The success `Data` XML for a sale (all four methods):

```xml
<ReceiptData>
  <DeviceID>...</DeviceID>
  <SerialNumber>...</SerialNumber>
  <FiscalDayNumber>...</FiscalDayNumber>
  <ReceiptCounter>...</ReceiptCounter>
  <ReceiptGlobalNumber>...</ReceiptGlobalNumber>
  <InvoiceNumber>...</InvoiceNumber>
  <InvoiceAmount>...</InvoiceAmount>
  <InvoiceTaxAmount>...</InvoiceTaxAmount>
  <ReceiptCurrency>...</ReceiptCurrency>
  <ReceiptHash>HEX-SHA256...</ReceiptHash>
  <ReceiptSignature>base64-device-signature...</ReceiptSignature>
  <FDMSData>
    <DeviceID>...</DeviceID>
    <FiscalDayNo>...</FiscalDayNo>
    <ReceiptGlobalNo>...</ReceiptGlobalNo>
    <QRCode>https://verification/…</QRCode>       <!-- the deep link, Section 18 -->
    <SyncState>submitted|pending</SyncState>
    <ValidationWarnings>[optional, pipe-joined]</ValidationWarnings>
  </FDMSData>
</ReceiptData>
```

- `<SyncState>submitted` ⇒ FDMS accepted right now; `pending` ⇒ stored locally, will be
  renumbered+submitted at sync.
- `GetCardDetails`-style audit: the engine logs the full receipt JSON and the full ZIMRA
  response for every receipt (`FULL ZIMRA SubmitReceipt RESPONSE …`) in its logs.

`SubmitReceipt` returns a JSON payload in `Data` (instead of the XML) which additionally
tells you the fiscal-cloud status:

```json
{
  "deviceID": "...",
  "receipt": { "...full receipt object..." },
  "fiscalCloudStatus": "synced|pending",
  "receiptID": "<zimra receiptID>",
  "operationID": "<zimra operationID>",
  "message": "ZIMRA receiptID=… operationID=…" | "Submitted locally; awaiting ZIMRA (no FDMS certificate installed)"
}
```

`fiscalCloudStatus` is `synced` when the FDMS acknowledgement is fresh (≤ 5 minutes);
otherwise `pending` with the last FDMS error in `message`.

---

## 11. Items XML

Shape (what the reference POS builds; all numeric fields in `InvariantCulture`):

```xml
<ITEMS>
  <ITEM>
    <HH>1</HH>                <!-- HS code (any digits; engine normalises to 8) -->
    <ITEMCODE>A001</ITEMCODE> <!-- item code -->
    <ITEMNAME1>Test Product</ITEMNAME1>
    <ITEMNAME2>Test Product</ITEMNAME2>
    <QTY>1</QTY>
    <PRICE>10.00</PRICE>
    <AMT>10.00</AMT>          <!-- line amount the customer pays -->
    <TAX>1.34</TAX>           <!-- VAT on the line -->
    <TAXR>0.155</TAXR>        <!-- VAT rate fraction or percent -->
    <TAXID>517</TAXID>        <!-- optional; engine derives taxID from TAXR otherwise -->
  </ITEM>
  ...
</ITEMS>
```

### How the engine heals each item (pre-submission, with warnings)

| Input problem | Healed value | Warning |
|---------------|--------------|---------|
| Missing/invalid HS code | `00000000` (digits only, pad/truncate to 8) | `Item N: no HS code supplied, defaulted to '00000000'.` / `Item N: HS code '<x>' invalid, normalised to '<y>'.` |
| `Quantity <= 0` | `1` | `Item N: quantity <x> is not acceptable, set to 1.` |
| `Price <= 0` | derived from `Amount/Quantity`, else `0.01` | `Item N: unit price invalid, set to 0.01.` |
| No item name | `DEFAULTITEMNAME` (default `Item`) | `Item N: no item name supplied, defaulted to '<x>'.` |

### Tax derivation per line

- `TAXR` is normalised to percent (fraction `< 1` is ×100: `0.155 → 15.5`).
- `taxCode`: `"A"` when rate > 0 (Standard), `"B"` when 0 (Zero-rated).
- `taxID` (`QualityTaxId`):
  - rate 0 ⇒ the device-config zero-rated bucket (prefer a config entry named `*zero*`,
    else any 0% entry, else `TAXIDZERORATED`);
  - rate > 0 ⇒ exact match against the device `applicableTaxes` (fraction or percent
    form), else the configured zero id when rate < 10, else a ±0.01 percent match, else `4`;
  - if the product carries an explicit `TAXID` the engine keeps the *rate*-derived bucket
    and reports any conflict via the compliance guard (`RCPT025`).
- Line total: `price × qty` when VAT-inclusive; `qty × (Amount/qty)` (net unit price)
  when tax-exclusive — credit notes negate price and total.

---

## 12. Currencies XML

```xml
<CurrenciesReceived>
  <Currency>
    <Name>USD</Name>
    <Amount>10.00</Amount>
    <Rate>1</Rate>
  </Currency>
</CurrenciesReceived>
```

- `Amount` should match the invoice total and the currency of `InvoiceAmount`.
- The engine maps payments to `receiptPayment{moneyTypeCode:"Cash", paymentAmount:<signed sum>}`
  for every currency line. When Currencies is empty a single `Cash` payment equal to the
  invoice total is emitted.
- `receiptCurrency` is normalised: `ZIG/ZIG$/ZWG/ZWG$/ZWD/ZW$/ZG$ → ZWG`; `US$ → USD`;
  `ZW/ZWL/Z$ → ZWL`; everything else uppercase pass-through.

---

## 13. Buyer data rules

- If buyer data is supplied, **both** `buyerRegisterName` **and** `buyerTIN` must be
  present, else the engine heals to the walk-in default and warns (`RCPT043`).
- Empty/bogus buyer data is healed to:
  `WALKINBUYERNAME` (default `Walk In Customer`), `WALKINBUYERTIN` (default `0000000000`),
  trade name `Walk In`, and empty contacts/address. Warnings:
  `No buyer details supplied; using default Walk In Customer (RCPT043).` or
  `Incomplete buyer details; name/TIN healed to Walk In Customer (RCPT043).`
- `CustomerFullAddress` (single string) is split/validated via
  `ValidateCustomerFullAddressEx(fullAddress, province, street, houseNo, city)` into the
  structured `buyerAddress {province, street, houseNo, city}` (public helper — see Section 21).

---

## 14. VAT computation rules

- `VATFLAG=1` (default): prices include VAT. Line total = `price × qty`.
  Tax-included tax per bucket: `taxAmount = groupTotal × pct / (100 + pct)`.
- `VATFLAG=0`: prices exclude VAT. Line totals are net; tax per bucket:
  `taxAmount = groupTotal × pct / 100`; `salesAmountWithTax = groupTotal + taxAmount`.
- The **product’s** `TAXR` is the source of truth for the rate; the device config is only
  a fallback when the product has no rate (`ResolveConfigPercent`). Rates are normalised
  to percent for ZIMRA’s `decimal(5,2)` `TaxPercent`.
- The engine **recomputes authoritatively** from the same receipt lines that get
  serialised, so RCPT019/RCPT025/RCPT026/RCPT027 hold by construction. If the caller’s
  `InvoiceAmount`/`InvoiceTaxAmount` disagree, the receipt uses the recomputed values and
  a warning is added (not an error):
  - `InvoiceAmount <x> differed from computed total <y>; VAT recomputed by device.`
  - `InvoiceTaxAmount <x> differed from computed VAT <y>; VAT recomputed by device.`
- Receipt date is built **monotonically increasing** within the fiscal day: if the last
  receipt’s date is not strictly before now, +1 s is injected (avoids ZIMRA
  "date not sequential" Red — RCPT030).

---

## 15. The receipt JSON sent to ZIMRA

`TransactInternal` serialises a `receipt` object (`Data` of `SubmitReceipt` also embeds
it under `receipt`). This is the exact schema (field names are the JSON property names):

```json
{
  "receiptType": "FiscalInvoice|CreditNote|DebitNote",
  "receiptCurrency": "ZWG",
  "receiptCounter": 7,
  "receiptGlobalNo": 17042,
  "invoiceNo": "INV-2026-…",
  "buyerData": {
    "buyerRegisterName": "Walk In Customer",
    "buyerTradeName": "Walk In",
    "buyerTIN": "0000000000",
    "VATNumber": "",
    "buyerContacts": { "phoneNo": "", "email": "" },
    "buyerAddress": { "province": "", "street": "", "houseNo": "", "city": "" }
  },
  "receiptNotes": "",
  "receiptDate": "2026-10-07T14:31:22",
  "creditDebitNote": null | { "receiptID": null, "deviceID": 18084, "receiptGlobalNo": 17041, "fiscalDayNo": 66 },
  "receiptLinesTaxInclusive": true,
  "receiptLines": [
    {
      "receiptLineName": "Test Product",
      "receiptLineNo": 1,
      "receiptLineQuantity": 1,
      "receiptLineType": "Sale",
      "receiptLineTotal": 10.00,
      "taxID": 517,
      "receiptLineHSCode": "00000000",
      "receiptLinePrice": 10.00,
      "taxCode": "A",
      "taxPercent": 15.50
    }
  ],
  "receiptTaxes": [
    {
      "salesAmountWithTax": 10.00,
      "taxAmount": 1.34,
      "taxID": 517,
      "taxCode": "A",
      "taxPercent": 15.50
    }
  ],
  "receiptPayments": [
    { "moneyTypeCode": "Cash", "paymentAmount": 10.00 }
  ],
  "receiptTotal": 10.00,
  "receiptPrintForm": "Receipt48",
  "receiptDeviceSignature": { "hash": "b64-SHA256(input)", "signature": "b64-device-signature" }
}
```

### Field glossary

| Field | Type | Notes |
|-------|------|-------|
| `receiptType` | string | `FiscalInvoice`="01", `CreditNote`="02", `DebitNote`="03" |
| `receiptCurrency` | string | normalised (Section 12) |
| `receiptCounter` | int | per-day receipt serial from the FDMS (or local) sequence |
| `receiptGlobalNo` | int | FDMS global receipt number (renumbered at sync for queued receipts) |
| `invoiceNo` | string | POS invoice number — must be globally unique per device |
| `buyerData` | object | `buyerData` schema; healed to walk-in per Section 13 |
| `receiptNotes` | string/object | `InvoiceComment`, else `Credit note`/`Debit note`/`""` by flag |
| `receiptDate` | string | `yyyy-MM-ddTHH:mm:ss`, monotonic within the day |
| `creditDebitNote` | object/null | only for flags 02/03; reference to the original receipt |
| `receiptLinesTaxInclusive` | bool | from `VATFLAG` |
| `receiptLines` | array | `receiptLine[]` |
| `receiptTaxes` | array | `receiptTax[]`, grouped by taxID, ordered taxID asc |
| `receiptPayments` | array | `receiptPayment[]` — always `moneyTypeCode:"Cash"` |
| `receiptTotal` | decimal | authoritative total (lines, or lines+tax when VAT-exclusive) |
| `receiptPrintForm` | string | from `RECEIPTPRINTFORM` |
| `receiptDeviceSignature` | object | `{hash: base64(SHA256(signature-input)), signature: base64}` — Section 17 |

`receiptLine`: `receiptLineName, receiptLineNo, receiptLineQuantity, receiptLineType("Sale"),
receiptLineTotal, taxID, receiptLineHSCode, receiptLinePrice, taxCode("A"/"B"), taxPercent`.

`receiptTax`: `salesAmountWithTax, taxAmount, taxID, taxCode, taxPercent`.

`receiptPayment`: `moneyTypeCode, paymentAmount`.

---

## 16. Validation & error-handling contract

### 16.1 Two guard layers

1. **Healing + early validation** in `TransactInternal` (Section 10): jumps straight to a
   `Failure` envelope for missing/non-numeric inputs, empty items, oversized XML,
   duplicate invoice numbers, licence, database.
2. **Pre-submission compliance guard** (`ValidateReceiptCompliance`): recomputes every
   RCPT rule against the **exact JSON about to be transmitted**. Any error aborts the
   submission before anything is queued or transmitted:

```
Transaction error: Internal validation - pre-submission compliance check rejected receipt <inv>.
The receipt was NOT submitted to ZIMRA FDMS and was NOT stored. <…space-joined RCPT errors…>
```

### 16.2 Engine-side validation codes (RCPT*)

These appear in the compliance-guard error message above and/or in FDMS
`validationErrors` Red items. The engine blocks cases it can prove:

| Code | Meaning (engine check) |
|------|------------------------|
| `RCPT011` | Receipt counter not assigned (`receiptCounter <= 0`) |
| `RCPT012` | Receipt global number not assigned; hard rejection when FDMS reports “global number is not sequential” |
| `RCPT013` | Invoice number missing |
| `RCPT015` | Credit/debit note must reference the original receipt (deviceID + receiptGlobalNo + fiscalDayNo all required) |
| `RCPT016` | At least one receipt line required |
| `RCPT019` | VAT-inclusive: `receiptTotal == Σ receiptLines` |
| `RCPT020` | Device signature missing, or its hash does not verify against the transmitted fields (recomputed by the engine) |
| `RCPT022` | Line total / unit price sign violates the flag (credit must be negative; sales positive) |
| `RCPT023` | Line quantity must be > 0 |
| `RCPT024` | `lineTotal == price × quantity` (within 0.005) |
| `RCPT025` | Tax percent on the line/tax bucket does not match device config; or an un-configured taxID |
| `RCPT026` | Computed tax amount inconsistent with `salesAmountWithTax` / submitted taxes |
| `RCPT030` | Receipt date missing / not strictly sequential within the day |
| `RCPT034` | `receiptNotes` required on credit/debit notes |
| `RCPT037` | Tax-exclusive: `receiptTotal == Σ lines + Σ tax` |
| `RCPT038` | `Σ salesAmountWithTax == receiptTotal` |
| `RCPT039` | At least one payment; `Σ payments == receiptTotal` |
| `RCPT040` | Credit note total ≤ 0; sale total ≥ 0 |
| `RCPT043` | Buyer name and TIN must both be present when buyer data is submitted |
| `RCPT047` | HS code required on every line |
| `RCPT048` | HS code ≤ 8 digits |

> Because the engine heals first and checks last, in practice RCPT errors surface only
> when the caller supplies data that cannot sensibly be healed (bad sign on credit lines,
> invalid tax bucket, unresolvable credit-note reference, …). They mean “fix the data —
> nothing was stored or sent.”

### 16.3 FDMS-facing error classification (what the POS sees)

The engine classifies every FDMS outcome and never lets a transport fault stop the POS:

| Class | How detected | Engine behaviour |
|-------|--------------|------------------|
| **Accepted** | HTTP 2xx + success code (`"00"`,`"001"`,`"0"`,`"000"`,`"00000"`,`"success"`) + no `errorCode` + no Red | Advance counters, chain head, mark `synced`, `Data: submitted` |
| **Red validation** | HTTP 200 but `validationErrors[]` entries flagged `validationErrorColor:"Red"` (or flat `validationErrorCode`) | Receipt **stored by ZIMRA but INVALID**; not chained, not synced; local global steps forward (server consumed it). Returns failure: `Transaction error: ZIMRA FDMS error - invoice <inv> was stored by ZIMRA but flagged with RED validation errors; the receipt is INVALID and will not be chained. ZIMRA response: <details>` |
| **Data reject** | `validationErrors[]` present, `validationErrorCode` present, or code starts with `RCPT` | Genuine data error — not stored as pending, returned as failure with `ExtractValidationErrors` details: `Transaction error: ZIMRA FDMS error - invoice <inv> was rejected by ZIMRA [<code>] <msg>\n - [RCPT…] …` |
| **Offline / no cert** | `Zimra.OfflineMode` or no certificate | Stored locally as `pending`; success envelope with `SyncState:pending` |
| **Transport fault** | no cert (`NOCERT`), no client (`NOCLIENT`), `NET`, HTTP ≥ 500, unreachable | **Not a rejection** — stored locally as `pending`; kept selling |

### 16.4 ZimraGateway hard codes

`ZimraResponse` carries `Success`, `HttpStatus`, `Code`, `ErrorCode`, `Message`,
`Raw` (≤ 8000 chars), `Json`, `RedValidation`. Codes the gateway itself emits:

| `Code` | Meaning |
|--------|---------|
| `NOCERT` | ZIMRA device certificate not installed |
| `NOCLIENT` | HttpClient not initialised (should never happen) |
| `NET` | Transport-level exception |
| `RATELIMIT` | HTTP 429; `Message` includes the server `Retry-After` |
| `RED` | HTTP 200 with Red validation entries (downgraded to a rejection) |
| `CLOSEFAILED` | close confirmed failed; `ErrorCode` = server closing-error code |
| `CLOSETIMEOUT` | close not confirmed within the poll budget (90 s) |

### 16.5 FDMS business error-code text (`MapFiscalCode`)

| `ErrorCode` | Meaning surfaced to the operator |
|-------------|----------------------------------|
| `DEV01` | Device not found or not active |
| `FISC01` | Open day not allowed (a day is already open, or previous day not fully closed on FDMS) |
| `FISC02` | Invalid fiscal day number (device day counter does not match the FDMS sequence) |
| `FISC03` | Closing not allowed (close already in progress) |
| `FISC04` | Closing not allowed (fiscal day is not opened) |
| `BadCertificateSignature` | Operation rejected — invalid certificate signature |
| `MissingReceipts` | Closure rejected — receipts missing (Grey error) |
| `ReceiptsWithValidationErrors` | Closure rejected — receipts with validation errors exist (Red error) |
| `CountersMismatch` | Closure rejected — device counters do not match submitted FDMS totals |

---

## 17. Signature hash chain

Each receipt is chained to the previous **accepted** receipt of the fiscal day.

### Canonical signature input (`BuildReceiptSignatureFields`)

Concatenated (in this exact order):

```
DeviceID
+ receiptType (uppercase)
+ normalized currency
+ globalReceiptNo            (InvariantCulture digits)
+ receiptDate (yyyy-MM-ddTHH:mm:ss)
+ Cents(receiptTotal)        (rounded ×100, truncated to long cents)
+ for each tax bucket ordered by (taxID asc, taxCode alpha, empty last):
      taxCode                (empty string when none; empty sorts first)
      + taxPercent in "0.00" format   — OMITTED entirely for taxID == 1 (exempt)
      + Cents(taxAmount)
      + Cents(salesAmountWithTax)
+ previousBase64Hash         (omitted for the FIRST receipt of the day — chain head)
```

Notes from the spec §13.2.1/§13.3.1: totals are always in cents; tax percent is always
two decimals; the exempt bucket (`taxID 1`) omits the percent; the previous receipt’s
**hash** (hex or base64, per `ExtractSignatureHashFromReceiptJson`) is appended from the
last *accepted* receipt.

### Hash / signature

- `hash` (hex, uppercase) = SHA-256 of the input above → this is what is signed and what
  FDMS verifies (server side re-derives the same string from the transmitted fields,
  hence RCPT020 equivalence).
- `receiptDeviceSignature.hash` = **base64** of the same SHA-256 input (what travels in
  the JSON).
- `signature` = device private-key signature over the hex hash — performed with the
  installed device certificate (`CertificateUtility.DeviceSignHashHex`); if no device
  certificates are installed it falls back to an HMACSHA256 demo signature keyed by
  `DeviceID|SerialNumber|FISCALSTACKZW-S2S` (so offline TEST receipts still verify
  offline).
- Chain rule: counters and the stored `previousHash` **only** advance when FDMS confirms
  acceptance (or consumes a Red-flagged number). This is what keeps
  RCPT012-sequential / RCPT020-signature valid even after offline periods.

---

## 18. QR verification link

Every receipt carries a deep link that verifies on the ZIMRA verification portal.
Composition (both at transact time and at renumber-at-sync):

```
verificationLink = <QRURL> + "/" + <deviceId10> + <receiptDate8> + <rgn10> + <qrData16>
```

- `QRURL` — configured (`QRURL`, default `VERIFICATIONSERVER`).
- `deviceId10` — the numeric part of `DEVICEID`, zero-padded to 10 digits (`ToString("D10")`).
- `receiptDate8` — fiscal date as `ddMMyyyy`.
- `rgn10` — `receiptGlobalNo` zero-padded to 10 digits.
- `qrData16` — the first 16 hex chars (uppercase) of the **MD5 over the RAW signature
  bytes** — i.e. the base64-decoded `signature`, NOT the base64 text — computed and
  truncated as `BitConverter.ToString(md5.ComputeHash(signatureBytes)).Replace("-","").Substring(0,16)`.

The link is embedded in the `FDMSData/QRCode` XML of the success payload and also
exposed as `ReceiptQRCode` in stored transaction rows. The reference POS prints this
URL as the ZIMRA QR for the cashier/customer.

---

## 19. FDMS transport (ZimraGateway)

- **Base URLs:** device endpoints `https://fdmsapi.zimra.co.zw/Device/v1/<DeviceID>/<Segment>`;
  public (no-cert) endpoints `https://fdmsapi.zimra.co.zw/Public/v1/<DeviceID>/<Segment>`.
- **mTLS:** the HttpClient presents the device pfx + CA/server/intermediate certs
  loaded from the device certificate folder (cache invalidated on identity change).
- **Mandatory headers:** `DeviceModelName` (default `Virtual Server`),
  `DeviceModelVersion` (`DEVICEMODELVERSIONNO` else `APIVERSION` = `v1`),
  `Accept: application/json`; bodies are UTF-8 JSON.
- **Timeout:** `TIMEOUT` seconds (default 90, clamped ≤ 300).

### Endpoint map (segment → purpose)

| Segment | Method | Body | Purpose |
|---------|--------|------|---------|
| `GetStatus` | GET | — | fiscal-day status + last global/day |
| `GetConfig` | GET | — | authoritative device configuration |
| `Ping` | POST | `{"deviceID"}` | liveness |
| `OpenDay` | POST | `{deviceID, fiscalDayOpened, fiscalDayNo}` | open fiscal day |
| `SubmitReceipt` | POST | `{deviceID, receipt}` | submit one receipt (Red-aware: HTTP 200 + Red ⇒ rejection) |
| `CloseDay` | POST | `{deviceID, fiscalDayNo, fiscalDayCounters, fiscalDayDeviceSignature, receiptCounter}` | async close request |
| `SubmitFile` | POST | multipart `deviceID` + `file` (base64 day-file JSON) | transmit an entire day file |
| `GetFileStatus` | POST | `{deviceID, operationID, fileUploadedFrom, fileUploadedTill}` | poll file processing |
| `VerifyTaxpayerInformation` (public) | POST | `{activationKey, deviceSerialNo}` | onboarding |
| `RegisterDevice` (public) | POST | `{activationKey, certificateRequest}` | onboarding |
| `GetServerCertificate` (public) | GET | `?thumbprint=` | fetch the FDMS server cert |

### Response parsing nuances

- `Success = httpOk && !looksLikeProblem`, where `looksLikeProblem` = non-empty
  `errorCode`, or a `code` not in `{"00","001","0","000","00000","success"}`.
- Message enrichment: the gateway prefers nested `issue` / `detail` / `description` /
  `validationError` over a bare `Unprocessable Entity`; known DEV/FISC codes are mapped
  to readable text (Section 16.5).
- **Red detection** (SubmitReceipt only): scans `validationErrors[]` (top-level or under
  `data`) for `validationErrorColor == "Red"` (Gray/Amber ignored). This is what turns an
  HTTP-200 “stored” receipt into a `RED` rejection with the offending codes+messages.

---

## 20. Offline behaviour, queue and recovery

### What accumulates when offline

- Receipts fiscalised while FDMS is unreachable (or certificateless) are stored
  **locally**, get a QR + device signature, and are queued with
  `FiscalCloudStatus = pending`. FDMS counters are untouched.
- `GetUnProcessedTransactions(day, page, pageSize)`,
  `GetUnProcessedTransactionsByDate(date, page, pageSize)` and
  `GetUnProcessedTransactionsSummary(day, date)` show exactly what is queued.

### SubmitPendingQueue — online catch-up

```csharp
public string SubmitPendingQueue(int limit)   // limit <= 0 ⇒ 200
```

For each pending receipt (in ascending global number order):

1. **Renumber onto the FDMS sequence** (`serverGlobal + 1`, `serverCounter + 1`) so
   RCPT012 stays sequential;
2. **Recompute signature + QR** against the real chain head
   (`GetLastSyncedReceiptHash`) so RCPT020 stays valid;
3. `SubmitReceipt` to FDMS;
4. Only on **confirmation** do the FDMS counters advance (`SetCounters`) and the row
   flip to `synced`; the chain head is the last-confirmed hash.

`Data` JSON on success:

```json
{ "total": n, "submitted": n, "failed": n, "stillPending": n,
  "mode": "online|offline", "items": [ { "invoiceNumber","flag","globalReceiptNo",
  "status","receiptID","message" } ] }
```

Per-item `status`: `queued` (initial), `synced`, `red`, `rejected-data` (with validation
errors), `failed`, `no-payload`, `offline`, `error`.

### SubmitFile — whole-day transmission

```csharp
public string SubmitFile(string fiscalDayNumber, string fiscalDate)
```

Builds and transmits the signed fiscal-day file:

- `header`: `{deviceID, fiscalDayNo, fiscalDayOpened, fileSequence}`;
- `content` → `receipts[]` (every queued receipt JSON for the day);
- `footer`: `fiscalCounters` (per-tax `BalanceByMoneyType` rows),
  `fiscalDayDeviceSignature {hash, signature}` (SHA-256 over the day signature fields,
  signed with the device key), `fiscalDayClosed`.
- Submits via the FDMS `submitFile` endpoint; on success returns the `operationID` and
  (best-effort) the `fileProcessingStatus` via `GetFileStatus`.

### POS-level fallback (what the reference POS does when the engine cannot reach FDMS)

`SubmissionService.SubmitPending(fiscalDayNo, fiscalDate)`:

1. Try `SubmitPendingQueue(200)` first; on success mark the journal and stop.
2. Otherwise snapshot the queue summary, call `SubmitFile(day, date)`, take the signed
   payload **from the response**, archive it to disk, and **directly POST** it to
   `<ZIMRASERVER>/api/v1/fiscal/device/submitFile` as multipart (`file` = base64 JSON).
3. Only when that direct POST returns `Code:"1"` → mark journal entries submitted and
   `ClearUnprocessedTransactions(day)`.

This guarantees an archived, replayable FDMS payload is never lost even in OFFLINE mode.

### Keeping the queue honest

- `ClearUnprocessedTransactions(day)` / `ClearUnprocessedTransactionsByDate(date)` —
  mark queued vouchers as submitted **only after** FDMS acknowledgement (the engine does
  this automatically when the queue is synced; the POS does it after a successful direct
  POST).
- `GetUnProcessedTransactions*` uses pagination (`page`, `pageSize`) — poll with a
  sensible page size.

---

## 21. Lookups and reporting

| Method | Returns |
|--------|---------|
| `GetTransaction(invoiceNo)` / `GetTransaction1(invoiceNo)` | Envelope; `Data` = serialised transaction row (JSON) with `JsonData` (the receipt), `ReceiptQRCode`, `FiscalCloudStatus`, counters, day. Self-heals via `GetTransactionByInvoiceNumberFromDetails` fallback. Not found ⇒ `Transaction not found for invoice number: <n>`. |
| `GetCardDetails()` | XML `<CardDetails>`: `TaxPayerName, TaxPayerTIN, VatNumber, DeviceSerialNo, DeviceBranchName, DeviceBranchAddress{province,street,houseNo,city}, …`. Online it refreshes from FDMS `getConfig` first (fail ⇒ `ZIMRA getConfig unavailable: card details could not be verified`); offline it returns the local snapshot with message `Card details (ZIMRA offline - device configuration is a local snapshot)`. **Call it after every sale / open / close / reconnect** to keep the cashier screen and printed trader block accurate. |
| `GetDeviceStatus()` | XML `<DeviceStatus>`: `Status` (`Online`, a real `FiscalDayOpened/…`, `Offline`, or `FDMS Unreachable`), `DeviceID`, `SerialNumber`, `CompanyName`, `FiscalDay`, `LastReceiptGlobalNo`, `Note`, `Revision:ServerToServer`. Message mirrors the `Note` when unreachable. |
| `GetConfig()` | Full JSON config snapshot (Section 3) |
| `ValidateCustomerFullAddressEx(fullAddress, province, street, houseNo, city)` | Returns a typed `Address {province,street,houseNo,city}` (public helper — feed the individual fields from your own address entry; the engine uses it to populate `buyerAddress`). |
| `GetUnProcessedTransactions*`, `ClearUnprocessedTransactions*` | Queue inspection/cleanup (Section 20) |

---

## 22. Reference integration (how FiscalStackZWPOS.App does it)

The shipped WPF POS is the canonical consumer. Its integration pattern is reproduced
here so you can mirror it exactly.

### 22.1 Single wrapper class, thread gate, envelope parsing

`FiscalStackZWDevice` wraps `lib` (created once), routes every call through
`Call(fn)` (Section 5 gate), and parses envelopes:

```csharp
// 1) Unwrap envelope; Data is a STRING — parse it again.
static JObject EnvelopePayload(string json)
{
    if (string.IsNullOrEmpty(json)) return null;
    var o = JObject.Parse(json);
    if (o["Code"]?.ToString() != "1") return null;
    var d = o["Data"]; if (d == null) return null;
    if (d.Type == JTokenType.Object) return (JObject)d;   // already object
    string inner = d.ToString();
    return string.IsNullOrWhiteSpace(inner) ? null : JObject.Parse(inner);
}

// 2) Sale: rich typed result from the ReceiptData XML.
static FiscalResult ParseResult(string raw)
{
    var o = JObject.Parse(raw);
    r.Ok = o["Code"]?.ToString() == "1";
    r.Message = o["Message"]?.ToString() ?? "";
    string data = o["Data"]?.ToString() ?? "";
    if (data.TrimStart().StartsWith("<")) {
        var x = XElement.Parse(data);
        r.QrUrl           = El(x, "QRCode");          // print this QR
        r.FiscalDayNo     = El(x, "FiscalDayNo");
        r.ReceiptGlobalNo = El(x, "ReceiptGlobalNo");
        r.SerialNumber    = El(x, "DeviceID");
        r.PendingSync     = El(x, "SyncState") == "pending";
        r.DeviceHash      = El(sigEl, "hash");
    }
}
```

`ReadCard(GetCardDetails())` parses the `<CardDetails>` XML and **writes the registered
company back into config** (`SyncCardToConfig` → `TAXPAYERNAME`, `TAXPAYERTIN`,
`VATNUMBER`, `SERIALNUMBER`, `DEVICEBRANCHNAME`, address keys into both
`%ProgramData%\FiscalStackZW\config.ini` and the app-dir copy) so receipts print and
report under the real registered company.

### 22.2 Sale flow (CheckoutWindow)

- Engine calls run on a background thread; the UI never blocks.
- Before fiscalising: `DayClosed = Device.IsFiscalDayClosed(Device.GetStatus())`.
  If the day is closed, the POS prompts **“Open a new fiscal day now and then retry the
  sale?”** and calls `Device.ReadOpenDay(Device.OpenDay())` inline — a test/real sale can
  be fiscalised without the cashier leaving checkout.
- `FiscalizeSale(sale, companyAddress)` builds the Items XML + Currencies XML (Sections
  11–12) and calls `TransactM(currency, email, invNo, name, vat, address, phone, tin,
  subtotal, vatTotal, flag, comment, originalInvNo, itemsXml, currenciesXml)`.
- Non-`Ok` results show `Fiscalise failed: <Message>` and are journaled; since a
  transport/NOCERT/NET failure already stored the receipt as **pending**, the sale itself
  is not lost — the queue sync later renumbers and submits it.
- `CompleteLocalSale` is the explicit “Local mode” path (unprovisioned/unlicensed
  devices) that never touches the engine — used only when the till is *not* in fiscal mode.

### 22.3 Day cycle (MainWindow / Settings)

- Startup/licence screen gates the app on `LicenseAllowed()` / `LicenseGraceNotice()`.
- Dashboard calls `GetStatus()` (day number, closed check), `OpenDay()` from the
  day-open button, `ZReport()` at close.
- Settings “Fiscal Ops” tab exposes the raw SDK buttons for support:
  `GetCardDetails`, `GetDeviceConfig`, `GetStatus`, `OpenDay`, `CloseDay`, `ZReport`,
  `SubmitPendingQueue(200)`, `GenerateDeviceCertificates`, `RegisterDeviceWithZimra`,
  `ApplyDeviceSettings`, `SetLicense`.

### 22.4 Onboarding wizard (OnboardingWindow + CertificateWizardFlow)

Order: licence key entry/validation → (TEST) `GenerateDeviceCertificates` →
`VerifyCertificateDetails` → `RegisterDeviceWithZimra` (argument-remapped) →
`ApplyDeviceSettings(certFolder, deviceId, serial, key)` → refresh
`GetCardDetails()`→`ReadCard`, `GetStatus()` → unlock.

### 22.5 Reconnection (SubmissionService)

Implemented in the SubmissionService pattern (Section 20): online → `SubmitPendingQueue`,
offline → `SubmitFile` payload → archive → direct multipart POST → `ClearUnprocessedTransactions`
→ mark journal. `IsOnline()` probes `<ZIMRASERVER>` with a 4 s HEAD/GET.

---

## 23. Agent prompt: integrate the DLL into a client POS

> **Role.** You are wiring ZIMRA fiscal functionality into a **client’s POS application**
> using `FiscalStackZW.dll`. The DLL is a *server-side* engine: it signs, submits, stores
> and recalls. **Your POS keeps its own look and feel, checkout logic, and reports** — you
> do not copy any fiscal UI, branding or receipt wording from elsewhere into the client
> app beyond the engine’s returned payloads.
>
> **Constraints (never break these):**
> - One engine instance per process; serialise every call with a gate (15 s timeout).
> - Never call the engine on the UI thread.
> - Never generate, infer or buy a licence key; the customer’s key is applied via
>   `SetLicense`/`LICENSEKEY` only.
> - Parse `Data` as a string (Section 4) — never index `o["Data"]["x"]` directly.
> - A `NOCERT`, `NET`, HTTP 5xx, or “unreachable” outcome on a sale is **not a failure to
>   report to the cashier as a data error** — the receipt is stored pending and must be
>   synced later. Only `Code:"0"` envelopes, Red validation, and RCPT/DEV/FISC rejections
>   are genuine failures to surface.
> - Build everything on the ZIMRA **TEST** FDMS first (`fdmsapitest.zimra.co.zw`), then
>   PROD. Never ship PROD config by default.
> - Do not re-implement or bypass engine behaviour (renumber-at-sync, chain, counters,
>   QR). The engine does all of that.
>
> **Implement, wired into the client POS’s normal screens and flow:**
>
> 1. **Wrapper (do this first).** One class wrapping the engine (create it once,
>    dispose at app exit) with the thread gate of Section 5, envelope unwrap
>    (`EnvelopePayload`), `ParseResult` for the `ReceiptData` XML (extract `QRCode`,
>    `FiscalDayNo`, `ReceiptGlobalNo`, `DeviceID`, `SyncState`, signature `hash`) and a
>    `ReadCard` for `GetCardDetails` XML that also syncs registered company into config.
> 2. **Licence gate.** Screen the app on `CheckLicense().allowed`; show
>   `LicenseGraceNotice()` while in grace; provide a Settings field that calls
>   `SetLicense(customerKey)`.
> 3. **Onboarding wizard (once per till).** TEST: `GenerateDeviceCertificates(serial,key,deviceId)`
>    → `VerifyCertificateDetails(...)` → `RegisterDeviceWithZimra` — remember the engine
>    argument order `(activationKey, serialNumber, deviceID)` — → `ApplyDeviceSettings(certFolder, deviceId, serial, key)` → refresh `GetCardDetails` + `GetStatus` and unlock.
>    PROD: import the ZIMRA-issued certificate folder with `ApplyDeviceSettings`.
> 4. **Open day.** Call `OpenDay()` when the cashier starts the day. Detect a closed day
>    via `GetStatus()` and **auto-offer to open the day** when a sale is attempted on a
>    closed day (mirror the reference flow). Surface the returned `fiscalDayNo` /
>    `zimraStatus`.
> 5. **Sale (core).** From the client’s existing cart totals build the Items XML and
>    Currencies XML (Sections 11–12; HS code, quantity, price, `TAXR` rate, amount, tax
>    per line) and call `TransactM(...)` (or `SubmitReceipt` when the client wants the
>    fiscal-cloud status payload). Pass the buyer name + TIN if known — otherwise omit
>    and the engine heals to “Walk In Customer”. Use the returned receipt (`InvoiceNumber`,
>    `ReceiptGlobalNo`, `QRCode`, `SyncState`) for the client’s receipt print/ticketing.
>    Journal every attempt and its `Message`.
> 6. **Cashier screen.** Call `GetCardDetails()` at log-in and after every
>    sale/open/close/reconnect; bind the returned trader name/address and the day’s
>    status to the relevant dashboard lines. Keep raw envelopes visible in a debug view.
> 7. **Close day.** `CloseDay()` then `ZReport()` at cashier close; surface close
>    failures (`CLOSEFAILED`/`CLOSETIMEOUT`, FISC codes) honestly and do NOT open a new
>    day while a close is unconfirmed.
> 8. **Reconnect/queue.** Provide (or auto-run) a reconnection routine: `SubmitPendingQueue(200)`
>    when online; when the engine cannot reach FDMS, `SubmitFile(day, date)` → archive the
>    signed payload → direct-POST it to `<ZIMRASERVER>/api/v1/fiscal/device/submitFile`
>    (multipart, `file` = base64 JSON) → on success `ClearUnprocessedTransactions(day)`.
>    Show `GetUnProcessedTransactionsSummary` counts in the UI.
> 9. **Support surface.** Add Settings buttons for: `GetCertificateDetails`,
>    `VerifyCertificateDetails`, `GenerateDeviceCertificates` (TEST),
>    `RegisterDeviceWithZimra`, `ApplyDeviceSettings`, `SubmitPendingQueue(limit)`,
>    `SubmitFile(day,date)`, `GetTransaction(invoiceNo)`, `GetUnProcessedTransactions*`,
>    `ClearUnprocessedTransactions*`, `ZReport`, `GetDeviceStatus`.
> 10. **TEST/PROD.** Read/present `POSENVIRONMENT`; let an authorised admin flip it
>     (ZIMRASERVER + tax ids + re-register). Test everything on TEST first.
>
> **Acceptance criteria.** (a) A full TEST day cycle — open day, N sales (some offline),
> reconnect, `SubmitPendingQueue`, close day — completes with every receipt
> `FiscalCloudStatus:synced` and correct global numbers; (b) no sale is ever lost or
> reported “failed” purely because the network was down; (c) licence gate blocks
> fiscalisation when unlicensed and shows the grace banner; (d) the wrapper compiles
> against .NET Framework 4.8 and the engine DLL + SQLite interop folders are deployed.

---

## 24. Deployment into your POS

1. Ship the engine folder contents next to your EXE: `FiscalStackZW.dll`,
   `System.Data.SQLite.dll`, `SQLite.Interop.dll` (**keep the `x64/` and `x86/`
   subfolders** — SQLite loads the right native interop at runtime),
   `Newtonsoft.Json.dll`, `BouncyCastle.Crypto.dll`, `NLog.dll`, `NLog.Targets.Seq.dll`,
   `AutoUpdater.NET.dll`, `NLog.config`, `FiscalStackZW.dll.config`.
2. Reference `FiscalStackZW.dll`; create the engine at startup
   (`new FiscalStackZW.FiscalStackZW()`), run the onboarding sequence
   (certificates → register → apply settings → licence only for TEST; apply existing
   certs for PROD), then poll with `GetStatus()`.
3. `config.ini` may ship without a `LICENSEKEY` — fiscal functions stay locked until the
   customer’s key is applied (Section 6). Do not ship PROD `ZIMRASERVER` by default.
4. Keep `%ProgramData%\FiscalStackZW\config.ini` as the canonical config once written;
   prefer it over the app-dir copy when both exist.

---

## 25. Package contents

```
Deploy\
x64\SQLite.Interop.dll
x86\SQLite.Interop.dll
FiscalStackZW.dll                 the engine
FiscalStackZWTest.exe             reference/troubleshooting tool (interactive harness)
FiscalStackZW.dll.config          engine defaults
FiscalStackZWCertificateGenerator.exe  standalone certificate tool
AutoUpdater.NET.dll, BouncyCastle.Crypto.dll, Newtonsoft.Json.dll,
NLog.dll, NLog.Targets.Seq.dll, System.Data.SQLite.dll, SmokeTest.exe,
NLog.config, config.ini           runtime support + local test config
```

---

## 26. Gotchas checklist

- [ ] `Data` is always a string — parse it again (JSON) or as XML. Never
      `o["Data"]["field"]`.
- [ ] One engine instance + a serialising gate; never call it on the UI thread.
- [ ] `RegisterDeviceWithZimra(activationKey, serialNumber, deviceID)` — argument order
      `(key, serial, device)`.
- [ ] Invoice numbers must be unique per device forever; generate timestamp-based
      numbers, reuse persisted receipts on retry, never retransmit.
- [ ] Credit notes (flag `02`) require `OriginalInvoiceNumber` for a valid `RCPT015`
      reference and mandatory `receiptNotes` (`RCPT034`); their amounts must be negative.
- [ ] HS codes are required on every line (`RCPT047/048`) — provide or accept the
      engine default `00000000`.
- [ ] `TAXR` may be a fraction (`0.155`) or percent (`15.5`) — both work.
- [ ] Do not treat transport/`NOCERT`/5xx as a sale failure; the receipt is stored
      pending and synced later.
- [ ] Red validation is a REAL rejection (`fiscalCloudStatus` stays non-`synced`; the
      receipt was stored by ZIMRA but is INVALID).
- [ ] Close is async — poll status; never open a new day until `FiscalDayClosed` is
      confirmed.
- [ ] Environment switches require re-registration on the new `ZIMRASERVER`.
- [ ] Confirm tax ids with `GetConfig()` after registration (ZIMRA may rewrite them).
- [ ] First receipt of each day starts a fresh signature chain (no previous hash).
- [ ] The QR’s MD5 is computed over the **decoded signature bytes**, not the base64 text.

---
*End of guide. When in doubt, sit in front of `FiscalStackZWTest.exe` with the same
`config.ini` as your POS and observe the verbatim envelopes before wiring the engine
into your own code.*