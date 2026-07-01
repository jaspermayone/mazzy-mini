# mazzy mini

A small KiCad PCB for probing and mapping the factory wiring harness of a Mazda vehicle using a Metra 70-7903 pigtail adapter.

## What it does

The board plugs into the factory harness via Metra 70-7903 pigtail (24-pin + 16-pin connectors) and provides:

- **40 through-hole solder/probe pads** (TP1–TP24 for the 24-pin side, TP25–TP40 for the 16-pin side) — one pad per Metra pigtail wire, labeled with known wire color/function or UNKNOWN for unidentified signals. These pads are intended to be soldered to the pigtail wires, not mated as removable connectors.
- **SN65HVD230 CAN transceiver** on 3.3V, wired to CAN_TX/CAN_RX for a Raspberry Pi Pico 2 W (GP4/GP5) to sniff and identify the Mazda MS-CAN bus by jumper-probing the unknown pads.
- **Onboard 3.3V LDO** (AMS1117-3.3) fed from a user-selectable BAT12 (constant) or ACC12 (switched) source via JP1 solder jumper.
- **P-channel MOSFET reverse-polarity protection** (PMV100EPAR, Q1) with a 15V gate-source zener clamp, plus a unidirectional SMBJ15A TVS clamp on the 12V input before the regulator.
- **Optional CAN termination** (120Ω R4 behind JP2) — leave open on the already-terminated Mazda factory MS-CAN bus.
- **3.3V power LED** (D1) for quick confirmation that JP1 and the 12V input path are live.
- **USB-C 5V input rail** (5V_USB) exposed to the Pico header for bench Pico power. It does **not** currently feed the AMS1117/onboard 3V3 rail.
- **Pico 3V3 isolation jumper** (JP3) keeps Pico-facing 3.3V header pins isolated from onboard 3V3 by default to avoid regulator backfeed/fighting.

## Known wires (24-pin side)

| Pad | Wire | Function |
|-----|------|----------|
| TP1 | Green | BAT12 — constant 12V+ |
| TP2 | Gray | ACC12 — switched 12V+ |
| TP3 | Black | Ground |
| TP4 | White | Front-left speaker + |
| TP5 | Yellow | Front-left speaker − |
| TP6 | Red | Front-right speaker + |
| TP7 | Blue | Front-right speaker − |
| TP8 | White | Rear-left speaker + |
| TP9 | Light green | Rear-left speaker − |
| TP10 | Blue | Rear-right speaker + |
| TP11 | Brown | Rear-right speaker − |
| TP12–TP24 | — | UNKNOWN — map during probing |

TP25–TP40 are the 16-pin pigtail side; all currently UNKNOWN.

## Schematic source

The schematic is defined in Python using [SKiDL](https://github.com/devbisme/skidl) in `circuit.py`. Running it generates the netlist used by KiCad.

```
pip install skidl
python circuit.py
```

The KiCad project files (`circuit.kicad_sch`, `circuit.kicad_pcb`, etc.) are the primary design artifacts and are checked in alongside the source.

## JP1 — power source selection

Solder jumper JP1 selects whether the onboard 3.3V regulator is fed from BAT12 (always on) or ACC12 (ignition-switched). Leave it **open** while mapping unknown harness pins so the board is only powered intentionally.

## JP2 — CAN termination

Leave **open** when connected to the Mazda factory MS-CAN bus — it is already terminated at both ends. Only bridge JP2 if you are running a standalone bench test with no other termination present.

## JP3 — Pico 3V3 isolation

Leave **open** by default. J4's 3.3V pin is on `PICO_3V3`, isolated from the onboard AMS1117 `3V3` rail unless JP3 is bridged. This prevents the Pico regulator and onboard regulator from backfeeding each other. Bridge JP3 only when you intentionally want one selected 3.3V source to power both sides.

## USB-C power limitation

`5V_USB` is routed to the Pico-facing header and its probe pad only. It does not diode-OR into the AMS1117 input, so USB-C alone will not power U1/the onboard CAN transceiver unless a future power-OR stage is added.
