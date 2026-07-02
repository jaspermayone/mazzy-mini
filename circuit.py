from skidl import *


@requirement("Metra 70-7903 pigtail approach: TP1-TP24 are the 24-pin-side solder/probe pads and TP25-TP40 are the 16-pin-side solder/probe pads.")
@requirement("Every factory-harness pigtail wire must land on one through-hole solder/test pad, TP1 through TP40, with the known function or UNKNOWN in the value label.")
@requirement("U1 SN65HVD230 CAN transceiver must run from 3.3V, expose CAN_TX/CAN_RX for Raspberry Pi Pico 2 W GP4/GP5, and keep CAN termination disabled by default.")
@requirement("U1", "SN65HVD230 pin 2 GND must connect to GND and pin 3 VCC must connect to 3V3; these pins must not be swapped.")
@requirement("Onboard 3.3V must be generated from selectable BAT12 or ACC12 through reverse-polarity P-channel MOSFET protection before the AMS1117-3.3 regulator.")
@requirement("D2", "12V rail transient clamp must be a unidirectional SMBJ15A-class 15V TVS with cathode to VIN12 and anode to GND.")
@requirement("D3", "Q1 gate-source voltage must be clamped by a 15V zener from source/cathode to gate/anode, with R1 gate pull-down sized so continuous dissipation stays within its package rating at 14.4V while the zener self-limits transient VGS.")
@requirement("JP3", "Pico-facing 3.3V header pins must be isolated from the onboard 3V3 rail by a normally-open jumper to prevent regulator backfeed by default.")
@requirement("D4", "USB-C VBUS must have local 5V ESD protection to GND at the connector side of the EMI bead.")
@requirement("FB1", "USB-C VBUS must pass through a ferrite bead before becoming the board 5V_USB rail.")
def build_circuit():
    gnd = Ground("GND")
    bat12 = Power("BAT12", voltage_domain=12.0)
    acc12 = Power("ACC12", voltage_domain=12.0)
    # VIN_RAW/VIN12 are nominally automotive 12V rails, but are intentionally left
    # unannotated because the series MOSFET model uses signed terminal-voltage
    # limits that otherwise produce false voltage-domain ERC errors.
    vin_raw = Net("VIN_RAW")
    vin12 = Net("VIN12")
    v3v3 = Power("3V3", voltage_domain=3.3, current=1.0)
    vbus = Power("VBUS", voltage_domain=5.0)
    v5usb = Power("5V_USB", voltage_domain=5.0)

    can_tx = Net("CAN_TX", voltage_domain=3.3)
    can_rx = Net("CAN_RX", voltage_domain=3.3)
    canh = Net("CANH")
    canl = Net("CANL")
    rp_gate = Net("RP_GATE")
    led_a = Net("PWR_LED_A")
    pico_3v3 = Net("PICO_3V3", voltage_domain=3.3)
    cc1 = Net("CC1")
    cc2 = Net("CC2")
    can_rs = Net("CAN_RS")

    # TP1-TP40 are both the Metra 70-7903 pigtail solder pads and the probe pads.
    # KiCad-side PWR_FLAG markers: these rails are legitimately driven by
    # off-board sources (harness wires, USB-C VBUS) or through passive elements
    # (Q1, FB1), so no schematic symbol has a power-output pin on them. PWR_FLAG
    # satisfies KiCad ERC power_pin_not_driven without changing connectivity.
    pwr_flag_rails = [
        (1, gnd, "Ground enters via the Metra black harness wire (TP3) and USB-C shell/GND pins."),
        (2, bat12, "Constant 12V enters via the Metra green harness wire on TP1."),
        (3, acc12, "Switched 12V enters via the Metra gray harness wire on TP2."),
        (4, vin12, "Protected 12V rail driven through Q1 reverse-polarity MOSFET (passive path)."),
        (5, vbus, "5V enters from the USB-C connector J5 VBUS pins."),
        (6, v5usb, "Filtered 5V rail driven through FB1 ferrite bead (passive path)."),
    ]
    for flag_num, flag_net, flag_reason in pwr_flag_rails:
        pwr_flag = Part("power", "PWR_FLAG", ref="FLG" + str(flag_num))
        pwr_flag.lcsc = "NONE"
        pwr_flag.info = "KiCad ERC power flag; virtual symbol, no physical part. " + flag_reason
        design_intent(
            pwr_flag,
            "KiCad ERC power flag; no physical part. " + flag_reason,
            group="Power flags",
            placement="Virtual symbol; place at the rail entry point on the schematic.",
        )
        flag_net += pwr_flag[1]

    # The supplied community documentation gives functions/wire colors, but not a verified
    # OEM cavity-number map. Keep the physical labels tied to the pigtail wire colors.
    harness_pads = [
        (1, "24-01 GREEN BAT12", bat12, "24-pin Metra pigtail pad for green battery constant 12V+ wire."),
        (2, "24-02 GRAY ACC12", acc12, "24-pin Metra pigtail pad for gray accessory switched 12V+ wire."),
        (3, "24-03 BLACK GND", gnd, "24-pin Metra pigtail pad for black ground wire."),
        (4, "24-04 WHITE FL+", Net("FL_SPK_P"), "24-pin Metra pigtail pad for front-left speaker positive, white wire."),
        (5, "24-05 YELLOW FL-", Net("FL_SPK_N"), "24-pin Metra pigtail pad for front-left speaker negative, yellow wire."),
        (6, "24-06 RED FR+", Net("FR_SPK_P"), "24-pin Metra pigtail pad for front-right speaker positive, red wire."),
        (7, "24-07 BLUE FR-", Net("FR_SPK_N"), "24-pin Metra pigtail pad for front-right speaker negative, blue wire."),
        (8, "24-08 WHITE RL+", Net("RL_SPK_P"), "24-pin Metra pigtail pad for rear-left speaker positive, white wire."),
        (9, "24-09 LTGRN RL-", Net("RL_SPK_N"), "24-pin Metra pigtail pad for rear-left speaker negative, light-green wire."),
        (10, "24-10 BLUE RR+", Net("RR_SPK_P"), "24-pin Metra pigtail pad for rear-right speaker positive, blue wire."),
        (11, "24-11 BROWN RR-", Net("RR_SPK_N"), "24-pin Metra pigtail pad for rear-right speaker negative, brown wire."),
        (12, "24-12 UNKNOWN", Net("H24_12"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (13, "24-13 UNKNOWN", Net("H24_13"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (14, "24-14 UNKNOWN", Net("H24_14"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (15, "24-15 UNKNOWN", Net("H24_15"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (16, "24-16 UNKNOWN", Net("H24_16"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (17, "24-17 UNKNOWN", Net("H24_17"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (18, "24-18 UNKNOWN", Net("H24_18"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (19, "24-19 UNKNOWN", Net("H24_19"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (20, "24-20 UNKNOWN", Net("H24_20"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (21, "24-21 UNKNOWN", Net("H24_21"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (22, "24-22 UNKNOWN", Net("H24_22"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (23, "24-23 UNKNOWN", Net("H24_23"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (24, "24-24 UNKNOWN", Net("H24_24"), "24-pin Metra pigtail pad for an unmapped wire; candidate vehicle signal to identify."),
        (25, "16-01 UNKNOWN", Net("H16_01"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (26, "16-02 UNKNOWN", Net("H16_02"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (27, "16-03 UNKNOWN", Net("H16_03"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (28, "16-04 UNKNOWN", Net("H16_04"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (29, "16-05 UNKNOWN", Net("H16_05"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (30, "16-06 UNKNOWN", Net("H16_06"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (31, "16-07 UNKNOWN", Net("H16_07"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (32, "16-08 UNKNOWN", Net("H16_08"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (33, "16-09 UNKNOWN", Net("H16_09"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (34, "16-10 UNKNOWN", Net("H16_10"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (35, "16-11 UNKNOWN", Net("H16_11"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (36, "16-12 UNKNOWN", Net("H16_12"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (37, "16-13 UNKNOWN", Net("H16_13"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (38, "16-14 UNKNOWN", Net("H16_14"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (39, "16-15 UNKNOWN", Net("H16_15"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
        (40, "16-16 UNKNOWN", Net("H16_16"), "16-pin Metra pigtail pad for an unmapped wire; map during harness probing."),
    ]
    for pad_num, pad_label, pad_net, pad_intent in harness_pads:
        pad = Part(
            "Connector",
            "TestPoint",
            value=pad_label,
            ref="TP" + str(pad_num),
            footprint="TestPoint:TestPoint_THTPad_D2.5mm_Drill1.2mm",
        )
        pad.lcsc = "NONE"
        pad.info = pad_intent
        design_intent(
            pad,
            pad_intent,
            group="Metra 70-7903 harness solder/probe pads",
            placement="Arrange TP1-TP24 as the 24-pin pigtail group and TP25-TP40 as the 16-pin pigtail group with generous probe spacing.",
        )
        pad_net += pad[1]

    # User-selectable 12V source. Leave open until the desired BAT12 or ACC12 source is bridged.
    jp1 = Part(
        "Jumper",
        "SolderJumper_3_Open",
        value="BAT/ACC SELECT",
        ref="JP1",
        footprint="Jumper:SolderJumper-3_P2.0mm_Open_TrianglePad1.0x1.5mm",
    )
    jp1.lcsc = "NONE"
    jp1.info = "Open 3-pad solder jumper used to select BAT12 or ACC12 as the source for the onboard 3.3V regulator; leave open while mapping unknown harness pins."
    design_intent(
        jp1,
        "Selects whether the onboard 3.3V regulator is fed from BAT12 constant power or ACC12 switched power; no bridge by default for safe harness mapping.",
        group="12V input selection and protection",
        placement="Place next to TP1/TP2 and label center pad VIN, side pads BAT and ACC.",
    )
    bat12 += jp1[1]
    vin_raw += jp1[2]
    acc12 += jp1[3]

    q1 = Part(
        "Transistor_FET",
        "Q_PMOS_GSD",
        value="PMV100EPAR",
        ref="Q1",
        footprint="Library:SOT-23-3_L2.9-W1.3-P1.90-LS2.3-BR",
    )
    q1.lcsc = "C3290636"
    q1.info = "PMV100EPAR P-channel MOSFET: pin 1 G, pin 2 S, pin 3 D; -60V VDS and +/-20V VGS from datasheet. Drain=input, source=protected load for high-side reverse-polarity protection. D3 clamps VGS during positive input transients."
    design_intent(
        q1,
        "High-side P-channel MOSFET reverse-polarity protection for the selected 12V source before the LDO and CAN circuitry.",
        group="12V input selection and protection",
        placement="Place close to JP1 and VIN12 protection TVS; keep BAT/ACC input path short and wide.",
    )
    vin_raw += q1[3]
    vin12 += q1[2]
    rp_gate += q1[1]

    r1 = Part("Device", "R_Small", value="10kΩ", ref="R1", footprint="Resistor_SMD:R_0603_1608Metric")
    r1.lcsc = "NONE"
    r1.info = "10kΩ gate-to-ground resistor for Q1 reverse-polarity P-channel MOSFET. Dissipates ~21mW at 14.4V (safe for 0603); D3 15V zener self-limits and clamps VGS below the +/-20V absolute maximum during source transients."
    design_intent(
        r1,
        "Gate-to-ground bias for Q1 with D3 zener VGS clamp; turns the P-channel reverse-protection MOSFET on only when the selected 12V source has normal polarity. 10kΩ keeps continuous dissipation ~21mW at 14.4V within the 0603 rating.",
        group="12V input selection and protection",
        placement="Place adjacent to Q1 gate.",
    )
    rp_gate += r1[1]
    gnd += r1[2]

    d3 = Part(
        "Library",
        "MMSZ5245BT1G",
        value="15V",
        ref="D3",
        footprint="Library:SOD-123_L2.7-W1.6-LS3.7-RD",
    )
    d3.lcsc = "C129730"
    d3.info = "onsemi MMSZ5245BT1G 15V 500mW zener, SOD-123. Pin 1 cathode to Q1 source/VIN12, pin 2 anode to Q1 gate/RP_GATE; clamps PMOS VGS around -15V and below the +/-20V rating."
    design_intent(
        d3,
        "Gate-source zener clamp for Q1 so positive VIN12/source spikes cannot overdrive the PMOS gate oxide.",
        group="12V input selection and protection",
        placement="Place directly between Q1 source pin 2 and gate pin 1 with very short traces.",
    )
    vin12 += d3[1]
    rp_gate += d3[2]

    d2 = Part("Library", "SMBJ15A_C83846", value="SMBJ15A", ref="D2", footprint="Library:SMB_L4.6-W3.6-LS5.3-RD")
    d2.lcsc = "C83846"
    d2.info = "Littelfuse SMBJ15A unidirectional TVS: pin 1 cathode/banded side to VIN12, pin 2 anode to GND; 15V VRWM, 16.7V min breakdown, 24.4V clamp at 24.6A. This is transient suppression, not full ISO automotive load-dump qualification for AMS1117."
    design_intent(
        d2,
        "Unidirectional 15V TVS clamp across the protected 12V rail to shunt positive harness spikes without clamping normal positive polarity.",
        group="12V input selection and protection",
        placement="Place close to VIN12 entry and give the GND side a short low-impedance return.",
    )
    vin12 += d2[1]
    gnd += d2[2]

    u2 = Part(
        "Library",
        "AMS1117-3.3_C347222",
        ref="U2",
        footprint="Library:SOT-223-4_L6.5-W3.5-P2.30-LS7.0-BR",
    )
    u2.lcsc = "C347222"
    u2.info = "AMS1117-3.3 fixed LDO: pin1 GND, pin2 VOUT, pin3 VIN, tab/pin4 VOUT; 1A IC rating but thermally limited from 12V. Intended for CAN transceiver/probe logic, not for powering a Pico W radio continuously."
    design_intent(
        u2,
        "Local 3.3V regulator for the SN65HVD230 CAN transceiver and low-current probe headers.",
        group="3.3V regulator",
        placement="Put input/output capacitors tight to U2; connect SOT-223 tab to the 3V3 copper pour for heat spreading.",
    )
    gnd += u2[1]
    v3v3 += u2[2]
    vin12 += u2[3]
    v3v3 += u2[4]
    # UMW AMS1117-3.3 product evidence: 1A output current rating; thermal margin from 12V is much lower.
    u2[2].set_current_source(1.0)

    c1 = Part("Device", "C_Small", value="10uF 25V", ref="C1", footprint="Capacitor_SMD:C_1206_3216Metric")
    c1.lcsc = "NONE"
    c1.info = "10uF 25V input capacitor for AMS1117-3.3 VIN; voltage rating selected for nominal 12V automotive rail margin."
    design_intent(
        c1,
        "AMS1117 input capacitor; 25V rating gives margin over nominal automotive 12V/14.4V charging voltage.",
        group="3.3V regulator",
        placement="Place at U2 VIN/GND pins.",
    )
    vin12 += c1[1]
    gnd += c1[2]

    c2 = Part(
        "Device",
        "C_Small",
        value="22uF 10V Tant",
        ref="C2",
        footprint="Capacitor_Tantalum_SMD:CP_EIA-3528-21_Kemet-B_HandSolder",
    )
    c2.lcsc = "NONE"
    c2.info = "AMS1117 output capacitor: datasheet guidance calls for tantalum or ESR in the stable range; use 10V or higher rating on 3.3V rail."
    design_intent(
        c2,
        "AMS1117 stable output capacitor using tantalum/ESR style required by AMS1117-family regulators.",
        group="3.3V regulator",
        placement="Place directly at U2 VOUT/GND pins; polarity positive to 3V3.",
    )
    v3v3 += c2[1]
    gnd += c2[2]

    c3 = Part("Device", "C_Small", value="100nF 10V", ref="C3", footprint="Capacitor_SMD:C_0603_1608Metric")
    c3.lcsc = "NONE"
    c3.info = "100nF 10V high-frequency bypass capacitor on the 3.3V regulator output."
    design_intent(
        c3,
        "High-frequency bypass for the 3.3V rail at the LDO output.",
        group="3.3V regulator",
        placement="Place near U2 VOUT/GND.",
    )
    v3v3 += c3[1]
    gnd += c3[2]

    r2 = Part("Device", "R_Small", value="2.2kΩ", ref="R2", footprint="Resistor_SMD:R_0603_1608Metric")
    r2.lcsc = "NONE"
    r2.info = "2.2kΩ current-limiting resistor for low-current 3.3V power LED indicator."
    design_intent(
        r2,
        "Power LED current limiter; approximately 0.4mA with the selected 0603 green LED at 3.3V.",
        group="Power indication",
        placement="Place next to D1 and label PWR.",
    )
    d1 = Part("Library", "LED_Small", value="GREEN", ref="D1", footprint="LED_SMD:LED_0603_1608Metric")
    d1.lcsc = "C20433785"
    d1.info = "Vishay TLMG1100-GS15 green 0603 LED, 2.4V Vf and 20mA rated forward current from product evidence."
    design_intent(
        d1,
        "3.3V-present indicator LED for quick confirmation that JP1 and the 12V input path are powering the regulator.",
        group="Power indication",
        placement="Place on board edge or near the notes area where it is visible during probing.",
    )
    v3v3 += r2[1]
    led_a += r2[2]
    led_a += d1[2]
    gnd += d1[1]

    u1 = Part(
        "Library",
        "SN65HVD230DR",
        ref="U1",
        footprint="Library:SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL",
    )
    u1.lcsc = "C12084"
    u1.info = "TI SN65HVD230DR: pin1 D/TXD, pin2 GND, pin3 VCC, pin4 R/RXD, pin5 VREF may float if unused, pin6 CANL, pin7 CANH, pin8 RS. ICC max 17mA dominant; RS low selects high-speed mode."
    design_intent(
        u1,
        "3.3V CAN transceiver used with Raspberry Pi Pico 2 W GP4/GP5 to identify Mazda MS-CAN H/L by jumper-probing unknown harness pads.",
        group="CAN transceiver and probe headers",
        placement="Place near CANH/CANL terminal and termination jumper; keep CANH/CANL routed as a short pair.",
    )
    can_tx += u1[1]
    gnd += u1[2]
    v3v3 += u1[3]
    can_rx += u1[4]
    u1[5] += NC
    canl += u1[6]
    canh += u1[7]
    can_rs += u1[8]
    # TI SN65HVD230DR datasheet/product evidence: dominant ICC max 17mA at 3.3V.
    u1[3].set_current_sink(0.017)

    c4 = Part("Device", "C_Small", value="100nF 10V", ref="C4", footprint="Capacitor_SMD:C_0603_1608Metric")
    c4.lcsc = "NONE"
    c4.info = "100nF 10V local bypass capacitor for SN65HVD230 VCC to GND."
    design_intent(
        c4,
        "Local high-frequency VCC bypass for U1 SN65HVD230.",
        group="CAN transceiver and probe headers",
        placement="Place as close as possible to U1 pins 3 and 2.",
    )
    v3v3 += c4[1]
    gnd += c4[2]

    c5 = Part("Device", "C_Small", value="4.7uF 10V", ref="C5", footprint="Capacitor_SMD:C_0805_2012Metric")
    c5.lcsc = "NONE"
    c5.info = "4.7uF 10V local bulk capacitor for the SN65HVD230 3.3V supply."
    design_intent(
        c5,
        "Small local bulk capacitor for the CAN transceiver 3.3V rail.",
        group="CAN transceiver and probe headers",
        placement="Place near U1 and C4.",
    )
    v3v3 += c5[1]
    gnd += c5[2]

    r3 = Part("Device", "R_Small", value="0Ω", ref="R3", footprint="Resistor_SMD:R_0603_1608Metric")
    r3.lcsc = "NONE"
    r3.info = "0Ω link pulling SN65HVD230 RS low for high-speed mode; can be changed to slope-control resistor if needed."
    design_intent(
        r3,
        "RS pull-down for U1 high-speed CAN mode; stuff as 0Ω, change to slope-control resistor only if EMI testing requires it.",
        group="CAN transceiver and probe headers",
        placement="Place next to U1 pin 8.",
    )
    can_rs += r3[1]
    gnd += r3[2]

    r4 = Part("Device", "R_Small", value="120Ω", ref="R4", footprint="Resistor_SMD:R_0805_2012Metric")
    r4.lcsc = "NONE"
    r4.info = "Optional 120Ω CAN termination footprint directly across CANH/CANL. DNP by default; do not populate on the already-terminated Mazda factory MS-CAN bus."
    r4.dnp = True
    design_intent(
        r4,
        "DNP optional CAN termination resistor across CANH/CANL. Populate only for standalone bench/end-node testing, not for the factory bus.",
        group="CAN transceiver and probe headers",
        placement="Place directly between the CANH/CANL pair near U1/J1 with very short, symmetric stubs; no series jumper in the CAN pair.",
    )
    canh += r4[1]
    canl += r4[2]

    jp3 = Part(
        "Jumper",
        "SolderJumper_2_Open",
        value="PICO 3V3 ISO",
        ref="JP3",
        footprint="Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
    )
    jp3.lcsc = "NONE"
    jp3.info = "Normally-open solder jumper between onboard 3V3 and Pico-facing PICO_3V3 header pins. Leave open by default to avoid backfeeding/fighting the Pico 3.3V regulator; bridge only when one 3.3V source is intentionally selected."
    design_intent(
        jp3,
        "Optional bridge from onboard 3V3 to Pico-facing 3.3V header pins; open by default for backfeed protection.",
        group="Pico power and logic headers",
        placement="Place beside J4 3V3 pin and silk label OPEN=NO BACKFEED.",
    )
    v3v3 += jp3[1]
    pico_3v3 += jp3[2]

    j1 = Part(
        "Library",
        "1725656",
        ref="J1",
        footprint="Library:CONN-TH_2P-P2.54_1725656",
    )
    j1.lcsc = "C3029316"
    j1.info = "2-position Phoenix Contact 1725656 2.54mm screw terminal exposing CANH and CANL."
    design_intent(
        j1,
        "2-pin screw terminal exposing CANH and CANL for jumper wires to unknown harness pads or for using an external Waveshare SN65HVD230 module instead of U1.",
        group="CAN transceiver and probe headers",
        placement="Put on board edge, label pin 1 CANH and pin 2 CANL.",
    )
    canh += j1[1]
    canl += j1[2]

    j4 = Part(
        "Library",
        "10897101",
        value="PICO GP4/GP5 CAN",
        ref="J4",
        footprint="Library:HDR-TH_10P-P2.54-V-M-R2-C5-S2.54",
    )
    j4.lcsc = "C586266"
    j4.info = "10-pin 2.54mm Pico utility header exposing GP4/CAN_TX, GP5/CAN_RX, isolated PICO_3V3, GND, and USB 5V. PICO_3V3 is not tied to onboard 3V3 unless JP3 is bridged."
    design_intent(
        j4,
        "10-pin Pico utility header exposing CAN_TX for GP4, CAN_RX for GP5, isolated PICO_3V3, GND, and USB 5V for direct Pico 2 W jumper access.",
        group="Pico power and logic headers",
        placement="Place near board edge with silk: 1 GP4/TX, 2 GP5/RX, 3 P3V3, 4 GND, 5 5V_USB, 6 GND.",
    )
    can_tx += j4[1]
    can_rx += j4[2]
    pico_3v3 += j4[3]
    gnd += j4[4]
    v5usb += j4[5]
    gnd += j4[6]
    j4[7] += NC
    j4[8] += NC
    j4[9] += NC
    j4[10] += NC

    j5 = Part(
        "Library",
        "2171750001",
        ref="J5",
        footprint="Library:TYPE-C-SMD_TYPE-C-6P_USB4125-GF-A-0190",
    )
    j5.lcsc = "C3197922"
    j5.info = "Molex 2171750001 USB-C power-only receptacle providing raw VBUS for optional Pico bench power. VBUS is ESD-protected by D4 and EMI-filtered by FB1 before becoming 5V_USB."
    design_intent(
        j5,
        "USB-C power-only input for optional Pico bench power; data pins are not present on this 6-pin power connector.",
        group="Pico power and logic headers",
        placement="Place on board edge; put D4 at the connector VBUS/GND pins and FB1 immediately after D4 before the 5V_USB fanout.",
    )
    vbus += j5.p["A9"]
    vbus += j5.p["B9"]
    gnd += j5.p["A12"]
    gnd += j5.p["B12"]
    cc1 += j5.p["A5"]
    cc2 += j5.p["B5"]
    gnd += j5[7]

    d4 = Part(
        "Device",
        "D_TVS",
        value="PESD5V0V1BB",
        ref="D4",
        footprint="Library:SOD-523_L1.2-W0.8-LS1.6-RD",
    )
    d4.lcsc = "C477993"
    d4.info = "Nexperia PESD5V0V1BB,115 single-line bidirectional 5V ESD diode, SC-79/SOD-523; 5V VRWM, 5.8V breakdown, 12.5V clamp at 4.8A 8/20us. Place from raw USB-C VBUS to GND at J5."
    design_intent(
        d4,
        "Local ESD clamp for USB-C VBUS before the ferrite bead; protects the bench-power input from cable/contact discharge.",
        group="Pico power and logic headers",
        placement="Place immediately adjacent to J5 VBUS and GND pins, before FB1, with a short ground return.",
    )
    vbus += d4[1]
    gnd += d4[2]

    fb1 = Part(
        "Library",
        "R_Small",
        value="600Ω@100MHz 1A",
        ref="FB1",
        footprint="Resistor_SMD:R_0603_1608Metric",
    )
    fb1.lcsc = "C404396"
    fb1.info = "TDK KPZ1608SHR601ATD25 ferrite bead: 600Ω at 100MHz, 1A current rating, 150mΩ DCR, 0603. Series EMI bead from raw USB-C VBUS to filtered 5V_USB rail. Pico/USB load current budget is not yet specified."
    design_intent(
        fb1,
        "Series ferrite bead forming the USB-C VBUS EMI filter with C6 on the filtered 5V_USB side.",
        group="Pico power and logic headers",
        placement="Place directly after J5/D4 on VBUS; route J5 VBUS -> D4/FB1 -> C6/5V_USB as a short power path.",
    )
    vbus += fb1[1]
    v5usb += fb1[2]

    r5 = Part("Device", "R_Small", value="5.1kΩ", ref="R5", footprint="Resistor_SMD:R_0603_1608Metric")
    r5.lcsc = "NONE"
    r5.info = "5.1kΩ USB-C CC1 Rd pull-down for sink/power-only operation."
    design_intent(
        r5,
        "USB-C CC1 Rd pull-down for sink/power-only operation.",
        group="Pico power and logic headers",
        placement="Place close to J5 CC1.",
    )
    cc1 += r5[1]
    gnd += r5[2]

    r6 = Part("Device", "R_Small", value="5.1kΩ", ref="R6", footprint="Resistor_SMD:R_0603_1608Metric")
    r6.lcsc = "NONE"
    r6.info = "5.1kΩ USB-C CC2 Rd pull-down for sink/power-only operation."
    design_intent(
        r6,
        "USB-C CC2 Rd pull-down for sink/power-only operation.",
        group="Pico power and logic headers",
        placement="Place close to J5 CC2.",
    )
    cc2 += r6[1]
    gnd += r6[2]

    c6 = Part("Device", "C_Small", value="1uF 10V", ref="C6", footprint="Capacitor_SMD:C_0603_1608Metric")
    c6.lcsc = "NONE"
    c6.info = "1uF 10V local bypass capacitor on the USB-C 5V rail."
    design_intent(
        c6,
        "Small local bypass for the USB 5V rail used by the Pico header.",
        group="Pico power and logic headers",
        placement="Place near J5 VBUS pins.",
    )
    v5usb += c6[1]
    gnd += c6[2]

    rail_points = [
        (41, "3V3", v3v3, "3.3V LDO output probe pad."),
        (42, "5V_USB", v5usb, "USB-C 5V probe/header rail; not generated from vehicle 12V."),
        (43, "VIN12", vin12, "Protected selected 12V rail after Q1 reverse-polarity MOSFET."),
        (44, "GND", gnd, "Ground probe pad tied to the Metra black ground wire and USB-C ground."),
        (45, "CANH", canh, "CANH probe pad tied to U1 and J1 pin 1; jumper candidate harness wires here while identifying MS-CAN."),
        (46, "CANL", canl, "CANL probe pad tied to U1 and J1 pin 2; jumper candidate harness wires here while identifying MS-CAN."),
    ]
    for rail_num, rail_label, rail_net, rail_intent in rail_points:
        rail_tp = Part(
            "Connector",
            "TestPoint",
            value=rail_label,
            ref="TP" + str(rail_num),
            footprint="TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm",
        )
        rail_tp.lcsc = "NONE"
        rail_tp.info = rail_intent
        design_intent(
            rail_tp,
            rail_intent,
            group="Utility probe pads",
            placement="Place near the related power/CAN circuit and keep labels clear.",
        )
        rail_net += rail_tp[1]
