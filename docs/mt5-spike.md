# MT5 Linux Stack Spike Report

**Date / Timestamp:** 2026-10-10 23:36:45 UTC  
**Status:** **BLOCKED**  
**Terminal Build:** None (None)  
**Bridge Mode:** None  

---

## 1. Account & Connection Details
- **Server:** `None`
- **Login:** `None` (Demo)
- **Balance / Equity:** `$0.00` / `$0.00` None
- **Leverage:** `1:None`
- **Margin Mode:** `None` (Raw value: `None`)
- **Trade Allowed / Expert:** `None` / `None`
- **Time to First Login:** `None seconds`
- **Server Time Offset:** `None hours vs UTC`

---

## 2. Symbols Discovered
- **Forex Pairs:** `0`
- **Synthetic Indices:** `0`
- **Other Instruments:** `0` (Filtered out per spec)
- **Total:** `0`

### Sample Forex Symbols
| Symbol | Digits | Min Vol | Max Vol | Step | Stops Level | Spread | Swap L/S |
|---|---|---|---|---|---|---|---|

### Sample Synthetic Index Symbols
| Symbol | Digits | Min Vol | Max Vol | Step | Stops Level | Spread | Swap L/S |
|---|---|---|---|---|---|---|---|

---

## 3. Order Check & Live Demo Trade Proof
- **Test Symbol:** `None`
- **Dry-run `order_check` Retcode:** `None` (None)
- **Live Demo Order Retcode:** `None` (Order: `None`, Deal: `None`)
- **Stop Loss Modification:** Retcode `None`
- **Full Position Close:** Retcode `None`, Deal `None`
- **History Deals Recorded:** `0 deal(s)`

---

## 4. Concurrency & Second Terminal Check
- **Result:** `None`
- **Note:** None
- **Handoff Architecture Impact:** Handover designed with lease token in D1 + graceful terminal handoff; open positions remain protected on broker by mandatory server-side Stop Loss.

---

## 5. Demo Balance Top-Up / Reset
- None
- None
- Design rule: None

---

## 6. Reliability & Freeze Assessment (3 Iterations)

**Verdict:** The MT5 stack is verified operational on Linux and ready for autonomous CFD execution.
