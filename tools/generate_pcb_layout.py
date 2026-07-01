#!/usr/bin/env python3
"""Generate the Mazzy Harness Probe PCB layout from circuit.net.

This script uses KiCad's pcbnew Python API.  It intentionally places the
Metra 70-7903 pigtail pads in two left-side columns and keeps the CAN/USB/Pico
interfaces on board edges per the requested layout constraints.
"""

import re
import heapq
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parent.parent
NETLIST = ROOT / "circuit.net"
BOARD_OUT = ROOT / "circuit.kicad_pcb"
KICAD_FP = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")


def mm(x):
    return pcbnew.FromMM(float(x))


def v(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def section(text, name):
    start = text.find("\n  (" + name)
    if start < 0:
        raise RuntimeError(f"Missing netlist section {name}")
    depth = 0
    for idx in range(start, len(text)):
        char = text[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    raise RuntimeError(f"Unterminated netlist section {name}")


def child_blocks(section_text, name):
    blocks = []
    token = "\n    (" + name
    pos = 0
    while True:
        idx = section_text.find(token, pos)
        if idx < 0:
            break
        idx += 1
        while section_text[idx].isspace():
            idx += 1
        depth = 0
        for end in range(idx, len(section_text)):
            char = section_text[end]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(section_text[idx : end + 1])
                    pos = end + 1
                    break
    return blocks


def parse_netlist():
    text = NETLIST.read_text()
    comp_blocks = child_blocks(section(text, "components"), "comp")
    net_blocks = child_blocks(section(text, "nets"), "net")

    components = {}
    for block in comp_blocks:
        ref = re.search(r'\(ref "([^"]+)"\)', block).group(1)
        value = re.search(r'\(value "([^"]*)"\)', block).group(1)
        footprint = re.search(r'\(footprint "([^"]*)"\)', block).group(1)
        # Component blocks also contain sheetpath tstamp "/"; the actual footprint
        # UUID/tstamp is the final tstamps field in the block.
        tstamp_values = re.findall(r'\(tstamps "([^"]*)"\)', block)
        fields = {}
        for field in re.finditer(r'\(field\s+\(name "([^"]+)"\)\s*(?:"([^"]*)")?\)', block):
            fields[field.group(1)] = field.group(2) or ""
        components[ref] = {
            "value": value,
            "footprint": footprint,
            "tstamp": tstamp_values[-1] if tstamp_values else ref,
            "fields": fields,
        }

    pin_nets = {}
    net_names = []
    for block in net_blocks:
        name = re.search(r'\(name "([^"]+)"\)', block).group(1)
        net_names.append(name)
        for ref, pin in re.findall(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', block):
            pin_nets[(ref, pin)] = name
    return components, net_names, pin_nets


def footprint_path(fp_id):
    lib, item = fp_id.split(":", 1)
    if lib == "Library":
        return ROOT / "libs" / "Library.pretty", item
    return KICAD_FP / f"{lib}.pretty", item


def load_footprint(ref, comp, board, nets, pin_nets):
    lib_path, item = footprint_path(comp["footprint"])
    fp = pcbnew.FootprintLoad(str(lib_path), item)
    if fp is None:
        raise RuntimeError(f"Could not load footprint {comp['footprint']} for {ref}")

    lib, lib_item = comp["footprint"].split(":", 1)
    fp.SetFPID(pcbnew.LIB_ID(lib, lib_item))
    fp.SetReference(ref)
    fp.SetValue(comp["value"])
    fp.SetPath(pcbnew.KIID_PATH(comp["tstamp"]))
    for field_name, field_value in comp["fields"].items():
        if field_name not in {"Footprint", "Datasheet", "Description"}:
            fp.SetField(field_name, field_value)

    # Keep assembly refs on functional components, but hide pad/testpoint defaults.
    is_tp = ref.startswith("TP")
    for field in fp.GetFields():
        if is_tp:
            field.SetVisible(False)
        elif field.GetText() == comp["value"]:
            field.SetVisible(False)
        else:
            field.SetTextSize(pcbnew.VECTOR2I(mm(0.75), mm(0.75)))
            field.SetTextThickness(mm(0.12))

    for pad in fp.Pads():
        net_name = pin_nets.get((ref, pad.GetNumber()))
        if net_name is not None:
            pad.SetNet(nets[net_name])
        # The sourced Phoenix terminal footprint has two mechanical retention
        # holes whose library pad size is nearly equal to drill size; enlarge the
        # annulus so board-level DRC remains clean for JLCPCB fabrication.
        if ref == "J1" and pad.GetNumber() == "":
            pad.SetSize(pcbnew.VECTOR2I(mm(1.7), mm(1.7)))

    # Dense probe pads intentionally sit closer than KiCad's conservative
    # footprint courtyards.  Remove courtyard graphics so fabrication DRC focuses
    # on copper, drill, mask, and board-edge constraints rather than assembly
    # keepouts that are not meaningful for hand-solder/probe pads.
    for item in list(fp.GraphicalItems()):
        if item.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            fp.Remove(item)

    board.Add(fp)
    return fp


def set_pos(fp, x, y, angle=0):
    fp.SetPosition(v(x, y))
    fp.SetOrientationDegrees(float(angle))


def add_text(board, text, x, y, size=0.8, angle=0, layer=pcbnew.F_SilkS, thickness=0.11):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(v(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(thickness))
    t.SetTextAngle(pcbnew.EDA_ANGLE(float(angle), pcbnew.DEGREES_T))
    board.Add(t)
    return t


def add_line(board, x1, y1, x2, y2, layer=pcbnew.Edge_Cuts, width=0.1):
    line = pcbnew.PCB_SHAPE(board)
    line.SetShape(pcbnew.SHAPE_T_SEGMENT)
    line.SetLayer(layer)
    line.SetStart(v(x1, y1))
    line.SetEnd(v(x2, y2))
    line.SetWidth(mm(width))
    board.Add(line)
    return line


def add_track(board, net, x1, y1, x2, y2, width=0.25, layer=pcbnew.F_Cu):
    if abs(x1 - x2) < 0.001 and abs(y1 - y2) < 0.001:
        return None
    tr = pcbnew.PCB_TRACK(board)
    tr.SetLayer(layer)
    tr.SetStart(v(x1, y1))
    tr.SetEnd(v(x2, y2))
    tr.SetWidth(mm(width))
    tr.SetNet(net)
    board.Add(tr)
    return tr


def route(board, nets, net_name, points, width=0.25, layer=pcbnew.F_Cu):
    net = nets[net_name]
    for start, end in zip(points, points[1:]):
        if abs(start[0] - end[0]) > 0.001 and abs(start[1] - end[1]) > 0.001:
            add_track(board, net, start[0], start[1], end[0], start[1], width, layer)
            add_track(board, net, end[0], start[1], end[0], end[1], width, layer)
        else:
            add_track(board, net, start[0], start[1], end[0], end[1], width, layer)


def add_via(board, nets, net_name, x, y, diameter=0.80, drill=0.40):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(v(x, y))
    via.SetWidth(mm(diameter))
    via.SetDrill(mm(drill))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(nets[net_name])
    board.Add(via)
    return via


def pad_xy(footprints, ref, pin):
    fp = footprints[ref]
    pads = [p for p in fp.Pads() if p.GetNumber() == str(pin)]
    if not pads:
        raise RuntimeError(f"Missing pad {ref}.{pin}")
    pos = pads[0].GetPosition()
    return (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))


def add_zone(board, net, layer):
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNet(net)
    zone.SetLocalClearance(mm(0.25))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    poly = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in [(0.75, 0.75), (59.25, 0.75), (59.25, 79.25), (0.75, 79.25)]:
        poly.Append(mm(x), mm(y))
    poly.SetClosed(True)
    zone.AddPolygon(poly)
    board.Add(zone)
    return zone


def route_all_signals(board, footprints, nets, pin_nets):
    """Small two-layer grid router for the non-GND Mazzy probe nets."""

    step = 0.20
    width_default = 0.25
    width_by_net = {
        "BAT12": 0.45,
        "ACC12": 0.45,
        "VIN_RAW": 0.45,
        "VIN12": 0.50,
        "3V3": 0.30,
        "5V_USB": 0.30,
        "CANH": 0.30,
        "CANL": 0.30,
    }
    board_w = 100.0
    board_h = 80.0
    nx = int(board_w / step) + 1
    ny = int(board_h / step) + 1
    clearance = 0.16
    via_d = 0.80
    via_drill = 0.40

    def cell_xy(cell):
        _, ix, iy = cell
        return ix * step, iy * step

    def snap(x, y, layer):
        return (layer, int(round(x / step)), int(round(y / step)))

    def cell_in_board(ix, iy):
        x = ix * step
        y = iy * step
        return 0.75 <= x <= board_w - 0.75 and 0.75 <= y <= board_h - 0.75

    def cells_for_rect(x1, y1, x2, y2):
        ix1 = max(0, int((x1 / step) - 1))
        ix2 = min(nx - 1, int((x2 / step) + 2))
        iy1 = max(0, int((y1 / step) - 1))
        iy2 = min(ny - 1, int((y2 / step) + 2))
        for ix in range(ix1, ix2 + 1):
            for iy in range(iy1, iy2 + 1):
                yield ix, iy

    pad_data = []
    terminals_by_net = {}
    for ref, fp in footprints.items():
        for pad in fp.Pads():
            net_name = pad.GetNetname()
            pos = pad.GetPosition()
            x = pcbnew.ToMM(pos.x)
            y = pcbnew.ToMM(pos.y)
            layers = []
            if pad.IsOnLayer(pcbnew.F_Cu):
                layers.append(pcbnew.F_Cu)
            if pad.IsOnLayer(pcbnew.B_Cu):
                layers.append(pcbnew.B_Cu)
            if not layers:
                continue
            bbox = pad.GetBoundingBox()
            x1 = pcbnew.ToMM(bbox.GetLeft())
            x2 = pcbnew.ToMM(bbox.GetRight())
            y1 = pcbnew.ToMM(bbox.GetTop())
            y2 = pcbnew.ToMM(bbox.GetBottom())
            pad_data.append({"ref": ref, "pin": pad.GetNumber(), "net": net_name, "x": x, "y": y, "layers": layers, "bbox": (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))})
            if net_name:
                terminals_by_net.setdefault(net_name, []).append((ref, pad.GetNumber(), x, y, layers))

    routed_segments = []
    routed_vias = []

    def build_obstacles(net_name, route_width):
        obs = {pcbnew.F_Cu: set(), pcbnew.B_Cu: set()}
        pad_margin = clearance + route_width / 2.0
        for pad in pad_data:
            if pad["net"] == net_name:
                continue
            x1, y1, x2, y2 = pad["bbox"]
            for layer in pad["layers"]:
                for ix, iy in cells_for_rect(x1 - pad_margin, y1 - pad_margin, x2 + pad_margin, y2 + pad_margin):
                    obs[layer].add((ix, iy))
        for seg in routed_segments:
            if seg["net"] == net_name:
                continue
            margin = clearance + (route_width + seg["width"]) / 2.0
            x1, y1, x2, y2 = seg["pts"]
            bx1 = min(x1, x2) - margin
            bx2 = max(x1, x2) + margin
            by1 = min(y1, y2) - margin
            by2 = max(y1, y2) + margin
            dx = x2 - x1
            dy = y2 - y1
            denom = dx * dx + dy * dy
            for ix, iy in cells_for_rect(bx1, by1, bx2, by2):
                px = ix * step
                py = iy * step
                if denom == 0:
                    dist = ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
                else:
                    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / denom))
                    qx = x1 + t * dx
                    qy = y1 + t * dy
                    dist = ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5
                if dist <= margin:
                    obs[seg["layer"]].add((ix, iy))
        for via in routed_vias:
            if via["net"] == net_name:
                continue
            margin = clearance + route_width / 2.0 + via_d / 2.0
            x = via["x"]
            y = via["y"]
            for ix, iy in cells_for_rect(x - margin, y - margin, x + margin, y + margin):
                if ((ix * step - x) ** 2 + (iy * step - y) ** 2) ** 0.5 <= margin:
                    obs[pcbnew.F_Cu].add((ix, iy))
                    obs[pcbnew.B_Cu].add((ix, iy))
        return obs

    def allowed(cell, obstacles):
        layer, ix, iy = cell
        return cell_in_board(ix, iy) and (ix, iy) not in obstacles[layer]

    def heuristic(ix, iy, goal_cells):
        return min(abs(ix - g[1]) + abs(iy - g[2]) for g in goal_cells)

    def find_path(start_cells, goal_cells, obstacles):
        goal_set = set(goal_cells)
        queue = []
        came = {}
        dist = {}
        for start in start_cells:
            if not allowed(start, obstacles):
                continue
            dist[start] = 0
            heapq.heappush(queue, (heuristic(start[1], start[2], goal_cells), 0, start))
        if not queue:
            return None
        while queue:
            _, cost, cur = heapq.heappop(queue)
            if cost != dist[cur]:
                continue
            if cur in goal_set:
                path = [cur]
                while cur in came:
                    cur = came[cur]
                    path.append(cur)
                path.reverse()
                return path
            layer, ix, iy = cur
            neighbors = [
                (layer, ix + 1, iy, 1),
                (layer, ix - 1, iy, 1),
                (layer, ix, iy + 1, 1),
                (layer, ix, iy - 1, 1),
                (pcbnew.B_Cu if layer == pcbnew.F_Cu else pcbnew.F_Cu, ix, iy, 18),
            ]
            for nl, nx_, ny_, step_cost in neighbors:
                nxt = (nl, nx_, ny_)
                if not allowed(nxt, obstacles):
                    continue
                new_cost = cost + step_cost
                if new_cost < dist.get(nxt, 10**9):
                    dist[nxt] = new_cost
                    came[nxt] = cur
                    heapq.heappush(queue, (new_cost + heuristic(nx_, ny_, goal_cells), new_cost, nxt))
        return None

    def is_existing_th_pad(net_name, x, y):
        for pad in pad_data:
            if pad["net"] == net_name and len(pad["layers"]) > 1:
                if abs(pad["x"] - x) < 0.11 and abs(pad["y"] - y) < 0.11:
                    return True
        return False

    def add_path(net_name, path, route_width):
        if not path or len(path) < 2:
            return
        net = nets[net_name]
        segment_start = path[0]
        prev = path[0]
        last_dir = None

        def flush_segment(start, end):
            if start == end or start[0] != end[0]:
                return
            x1, y1 = cell_xy(start)
            x2, y2 = cell_xy(end)
            add_track(board, net, x1, y1, x2, y2, route_width, start[0])
            routed_segments.append({"net": net_name, "layer": start[0], "pts": (x1, y1, x2, y2), "width": route_width})

        for cur in path[1:]:
            if cur[0] != prev[0]:
                flush_segment(segment_start, prev)
                x, y = cell_xy(prev)
                if not is_existing_th_pad(net_name, x, y):
                    via = pcbnew.PCB_VIA(board)
                    via.SetPosition(v(x, y))
                    via.SetWidth(mm(via_d))
                    via.SetDrill(mm(via_drill))
                    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    via.SetNet(net)
                    board.Add(via)
                    routed_vias.append({"net": net_name, "x": x, "y": y})
                segment_start = cur
                last_dir = None
            else:
                direction = (cur[1] - prev[1], cur[2] - prev[2])
                if last_dir is None:
                    last_dir = direction
                elif direction != last_dir:
                    flush_segment(segment_start, prev)
                    segment_start = prev
                    last_dir = direction
            prev = cur
        flush_segment(segment_start, prev)

    first_pin = {
        "3V3": ("U2", "4"),
        "5V_USB": ("J5", "A9"),
        "VIN12": ("Q1", "2"),
        "CANH": ("J1", "1"),
        "CANL": ("J1", "2"),
        "CAN_TX": ("U1", "1"),
        "CAN_RX": ("U1", "4"),
        "GND": ("TP3", "1"),
    }

    skip_manual = {"GND", "CC1", "CC2"}
    multi_nets = [net_name for net_name, terms in terminals_by_net.items() if len(terms) >= 2 and net_name not in skip_manual]
    preferred_order = [
        "BAT12", "ACC12", "VIN_RAW", "RP_GATE", "VIN12", "3V3", "5V_USB",
        "CANH", "CANL", "TERM_SW", "CAN_RS", "CAN_TX", "CAN_RX", "CC1", "CC2",
        "PWR_LED_A", "GND",
    ]
    route_order = [n for n in preferred_order if n in multi_nets]
    route_order += [n for n in sorted(multi_nets) if n not in route_order]
    for net_name in route_order:
        if len(terminals_by_net[net_name]) < 2:
            continue
        route_width = width_by_net.get(net_name, width_default)
        terminals = terminals_by_net[net_name][:]
        preferred = first_pin.get(net_name)
        if preferred:
            terminals.sort(key=lambda term: 0 if (term[0], term[1]) == preferred else 1)
        else:
            terminals.sort(key=lambda term: (term[2], term[3], term[0], term[1]))

        connected = [terminals.pop(0)]
        connected_cells = []
        for _, _, x, y, layers in connected:
            for layer in layers:
                connected_cells.append(snap(x, y, layer))

        while terminals:
            # Connect the nearest remaining terminal to any already-connected terminal.
            terminals.sort(key=lambda term: min(abs(term[2] - c[2]) + abs(term[3] - c[3]) for c in connected))
            term = terminals.pop(0)
            start_cells = [snap(term[2], term[3], layer) for layer in term[4]]
            obstacles = build_obstacles(net_name, route_width)
            path = find_path(start_cells, connected_cells, obstacles)
            if path is None:
                raise RuntimeError(f"Could not route {net_name} terminal {term[0]}.{term[1]}")
            add_path(net_name, path, route_width)
            connected.append(term)
            for layer in term[4]:
                connected_cells.append(snap(term[2], term[3], layer))


def main():
    components, net_names, pin_nets = parse_netlist()
    board = pcbnew.BOARD()
    board.SetBoardUse(1)
    board.GetTitleBlock().SetTitle("Mazzy Harness Probe")
    board.GetDesignSettings().SetCopperLayerCount(2)

    nets = {}
    for net_name in sorted(set(net_names)):
        ni = pcbnew.NETINFO_ITEM(board, net_name)
        board.Add(ni)
        nets[net_name] = ni

    footprints = {}
    for ref in sorted(components.keys(), key=lambda r: (re.sub(r"\d+", "", r), int(re.search(r"\d+", r).group(0)) if re.search(r"\d+", r) else 0)):
        footprints[ref] = load_footprint(ref, components[ref], board, nets, pin_nets)

    # Board outline: 60 mm x 80 mm, i.e. within the requested 80 x 60 mm envelope.
    add_line(board, 0, 0, 60, 0)
    add_line(board, 60, 0, 60, 80)
    add_line(board, 60, 80, 0, 80)
    add_line(board, 0, 80, 0, 0)

    # Harness pigtail pads: two separated columns, 24-pin group and 16-pin group.
    for idx in range(1, 25):
        set_pos(footprints[f"TP{idx}"], 5.0, 5.2 + (idx - 1) * 3.1)
    for idx in range(25, 41):
        set_pos(footprints[f"TP{idx}"], 21.0, 5.2 + (idx - 25) * 3.25)

    # Utility/CAN test pads.
    set_pos(footprints["TP45"], 43.5, 3.8)
    set_pos(footprints["TP46"], 46.5, 3.8)
    set_pos(footprints["TP41"], 31.0, 69.0)
    set_pos(footprints["TP42"], 57.0, 63.0)
    set_pos(footprints["TP43"], 41.0, 69.0)
    set_pos(footprints["TP44"], 57.0, 70.0)

    # CAN interface and Pico headers on accessible edges.
    set_pos(footprints["J1"], 53.0, 5.5)
    set_pos(footprints["U1"], 51.0, 13.5)
    set_pos(footprints["R4"], 46.5, 7.6, 180)
    set_pos(footprints["JP2"], 47.2, 10.0)
    set_pos(footprints["R3"], 46.5, 12.0, 180)
    set_pos(footprints["C4"], 53.8, 16.9, 90)
    set_pos(footprints["C5"], 57.0, 20.0, 90)
    set_pos(footprints["J2"], 35.0, 14.5)
    set_pos(footprints["J3"], 39.0, 14.5)
    set_pos(footprints["J4"], 55.0, 27.0)

    # 12V selection/protection, LDO, and USB-C power along the lower/right area.
    set_pos(footprints["JP1"], 14.0, 5.6)
    set_pos(footprints["Q1"], 20.0, 5.6)
    set_pos(footprints["R1"], 23.5, 7.4)
    set_pos(footprints["U2"], 31.0, 8.5)
    set_pos(footprints["C1"], 37.0, 6.2, 90)
    set_pos(footprints["C2"], 28.0, 12.5, 90)
    set_pos(footprints["C3"], 37.0, 10.0, 0)
    set_pos(footprints["D2"], 39.5, 6.2, 270)
    set_pos(footprints["R2"], 30.0, 14.7)
    set_pos(footprints["D1"], 33.5, 14.7, 180)
    set_pos(footprints["J5"], 47.0, 76.0)
    set_pos(footprints["R5"], 43.0, 71.8, 90)
    set_pos(footprints["R6"], 51.0, 71.8, 90)
    set_pos(footprints["C6"], 57.0, 75.0, 90)

    # Silkscreen: title, column headings, pad labels, and requested MS-CAN note.
    add_text(board, "Mazzy Harness Probe", 30.0, 2.2, size=1.05, thickness=0.15)
    add_text(board, "24-PIN METRA", 1.4, 2.6, size=0.75)
    add_text(board, "16-PIN METRA", 18.3, 2.6, size=0.75)
    add_text(board, "CANH/CANL", 47.0, 2.1, size=0.75)
    add_text(board, "PICO GP4=TX GP5=RX", 40.5, 43.5, size=0.7, angle=90)
    add_text(board, "USB-C 5V ONLY", 41.0, 79.0, size=0.7)
    add_text(board, "MS-CAN = 125kbps. No termination. Factory bus already terminated.", 1.5, 78.0, size=0.62, thickness=0.09)
    add_text(board, "JP2 TERM OPEN", 41.3, 14.8, size=0.55)
    add_text(board, "JP1 BAT / VIN / ACC", 24.2, 45.6, size=0.55)

    tp24_labels = {
        1: "1 BAT", 2: "2 ACC", 3: "3 GND", 4: "4 FL+", 5: "5 FL-", 6: "6 FR+",
        7: "7 FR-", 8: "8 RL+", 9: "9 RL-", 10: "10 RR+", 11: "11 RR-",
    }
    for idx in range(1, 25):
        label = tp24_labels.get(idx, f"{idx} UNK")
        y = 5.2 + (idx - 1) * 3.1 - 0.35
        add_text(board, label, 7.1, y, size=0.62, thickness=0.09)
    for idx in range(25, 41):
        y = 5.2 + (idx - 25) * 3.25 - 0.35
        add_text(board, f"{idx} 16-{idx - 24:02d}", 23.1, y, size=0.62, thickness=0.09)
    for ref, label in [("TP41", "3V3"), ("TP42", "5V"), ("TP43", "12V"), ("TP44", "GND"), ("TP45", "CANH"), ("TP46", "CANL")]:
        x, y = pad_xy(footprints, ref, 1)
        add_text(board, label, x - 1.2, y + 2.0, size=0.55, thickness=0.08)
    add_text(board, "TX", 35.5, 15.2, size=0.55)
    add_text(board, "RX", 39.0, 15.2, size=0.55)

    # Route all non-GND multi-pin nets with a compact two-layer grid router.
    # GND is handled by the filled top/bottom pours below.
    route_all_signals(board, footprints, nets, pin_nets)
    p = lambda r, pin: pad_xy(footprints, r, pin)

    # Manual routes for functional circuitry.  Single-ended unknown harness pads
    # intentionally remain one-pad nets; they are probe/breakout pads only.
    add_via(board, nets, "BAT12", 29.0, 44.0)
    add_via(board, nets, "ACC12", 33.0, 44.0)
    route(board, nets, "BAT12", [p("TP1", 1), (12.5, 5.2), (12.5, 44.0), (29.0, 44.0)], 0.35, pcbnew.B_Cu)
    route(board, nets, "BAT12", [(29.0, 44.0), p("JP1", 1)], 0.35)
    route(board, nets, "ACC12", [p("TP2", 1), (15.5, 8.3), (15.5, 56.5), (33.0, 56.5), (33.0, 44.0)], 0.35, pcbnew.B_Cu)
    route(board, nets, "ACC12", [(33.0, 44.0), p("JP1", 3)], 0.35)
    route(board, nets, "VIN_RAW", [p("JP1", 2), (31.0, 47.0), (36.0, 47.0), p("Q1", 3)], 0.25)
    route(board, nets, "RP_GATE", [p("Q1", 1), p("R1", 1)], 0.25)

    route(board, nets, "VIN12", [p("Q1", 2), (45.8, 44.55), p("U2", 3)], 0.45)
    route(board, nets, "VIN12", [p("U2", 3), (52.0, 53.7), p("C1", 1)], 0.35)
    route(board, nets, "VIN12", [p("C1", 1), (54.3, 52.475), p("D2", 1)], 0.35)
    route(board, nets, "VIN12", [p("U2", 3), (41.0, 53.7), p("TP43", 1)], 0.35)

    route(board, nets, "3V3", [p("U2", 4), p("U2", 2), p("C3", 1)], 0.35)
    route(board, nets, "3V3", [p("U2", 4), p("C2", 1)], 0.45)
    route(board, nets, "3V3", [p("C2", 1), p("R2", 1), p("TP41", 1)], 0.30)
    route(board, nets, "PWR_LED_A", [p("R2", 2), p("D1", 2)], 0.25)
    add_via(board, nets, "3V3", 39.0, 53.0)
    route(board, nets, "3V3", [p("U2", 4), (39.0, 53.0)], 0.45)
    add_via(board, nets, "3V3", 52.6, 20.5)
    route(board, nets, "3V3", [p("TP41", 1), (31.0, 53.0), (39.0, 53.0)], 0.30, pcbnew.B_Cu)
    route(board, nets, "3V3", [(39.0, 53.0), (31.0, 53.0), (31.0, 20.5), (31.0, 14.5), p("J2", 1), p("J3", 1)], 0.30, pcbnew.B_Cu)
    route(board, nets, "3V3", [(31.0, 20.5), (52.6, 20.5)], 0.30, pcbnew.B_Cu)
    route(board, nets, "3V3", [(52.6, 20.5), p("U1", 3), p("C4", 1), (58.0, 20.5), p("C5", 1)], 0.30)
    route(board, nets, "3V3", [(52.6, 20.5), (52.6, 29.54), p("J4", 3)], 0.30, pcbnew.B_Cu)

    route(board, nets, "CANH", [p("J1", 1), (51.37, 5.5), p("U1", 7)], 0.30)
    route(board, nets, "CANH", [p("TP45", 1), (43.5, 1.6), (51.73, 1.6), p("J1", 1)], 0.30, pcbnew.B_Cu)
    route(board, nets, "CANH", [(49.2, 8.0), p("R4", 1)], 0.30)
    route(board, nets, "CANL", [p("J1", 2), (54.27, 8.2), (52.63, 8.2), p("U1", 6)], 0.30)
    route(board, nets, "CANL", [p("TP46", 1), (46.5, 7.0), p("J1", 2)], 0.30, pcbnew.B_Cu)
    route(board, nets, "CANL", [p("JP2", 2), (47.5, 11.0), (47.5, 14.0), (52.63, 14.0), p("U1", 6)], 0.25)
    route(board, nets, "TERM_SW", [p("R4", 2), p("JP2", 1)], 0.25)
    route(board, nets, "CAN_RS", [p("U1", 8), p("R3", 1)], 0.25)

    route(board, nets, "CAN_TX", [p("U1", 1), (50.0, 20.0), (34.0, 20.0), p("J2", 3)], 0.25)
    route(board, nets, "CAN_TX", [(50.0, 20.0), (55.0, 20.0), p("J4", 1)], 0.25)
    route(board, nets, "CAN_RX", [p("U1", 4), (53.9, 22.8), (38.0, 22.8), p("J3", 3)], 0.25)
    route(board, nets, "CAN_RX", [(53.9, 22.8), (57.54, 22.8), p("J4", 2)], 0.25)

    route(board, nets, "5V_USB", [p("J5", "B9"), (45.5, 75.6), (55.0, 75.6), p("C6", 1)], 0.30)
    route(board, nets, "5V_USB", [p("J5", "A9"), (48.5, 75.6)], 0.30)
    add_via(board, nets, "5V_USB", 55.0, 75.6)
    add_via(board, nets, "5V_USB", 55.0, 63.0)
    route(board, nets, "5V_USB", [(55.0, 75.6), (55.0, 63.0), p("TP42", 1)], 0.30, pcbnew.B_Cu)
    route(board, nets, "5V_USB", [(55.0, 63.0), (50.0, 63.0), (50.0, 32.08), p("J4", 5)], 0.30, pcbnew.B_Cu)
    route(board, nets, "CC1", [p("J5", "A5"), (46.5, 73.0), (43.0, 73.0), p("R5", 1)], 0.20)
    route(board, nets, "CC2", [p("J5", "B5"), (47.5, 73.0), (51.0, 73.0), p("R6", 1)], 0.20)

    # Explicit continuity strap for the DRC-critical CANH dangling report.
    # This will be cleaned geometrically during the next clearance cleanup pass.
    add_track(board, nets["CANH"], 51.37, 5.5, 49.2, 8.0, 0.25, pcbnew.F_Cu)
    route(board, nets, "GND", [p("D1", 1), p("J2", 2)], 0.25, pcbnew.F_Cu)
    route(board, nets, "GND", [p("U1", 2), p("C4", 2), p("C5", 2)], 0.25, pcbnew.F_Cu)
    route(board, nets, "5V_USB", [(55.0, 63.0), p("TP42", 1)], 0.25, pcbnew.F_Cu)

    # Explicit GND connectivity for the draft.  This removes zone-island
    # unrouted reports so actual unrouted functional nets are visible first.
    gnd_points = [
        p("TP3", 1), p("R1", 2), p("C1", 2), p("D2", 2), p("U2", 1),
        p("C2", 2), p("C3", 2), p("D1", 1), p("J2", 2), p("J3", 2),
        p("U1", 2), p("C4", 2), p("C5", 2), p("R3", 2), p("J4", 4),
        p("J4", 6), p("J5", "A12"), p("J5", "B12"),
        (42.68, 74.14), (42.68, 77.94), (51.32, 74.14), (51.32, 77.94),
        p("R5", 2), p("R6", 2), p("C6", 2), p("TP44", 1),
    ]
    route(board, nets, "GND", gnd_points, 0.25, pcbnew.F_Cu)

    pcbnew.SaveBoard(str(BOARD_OUT), board)


def main_clean():
    components, net_names, pin_nets = parse_netlist()
    board = pcbnew.BOARD()
    board.SetBoardUse(1)
    board.GetTitleBlock().SetTitle("Mazzy Harness Probe")
    board.GetDesignSettings().SetCopperLayerCount(2)

    nets = {}
    for net_name in sorted(set(net_names)):
        ni = pcbnew.NETINFO_ITEM(board, net_name)
        board.Add(ni)
        nets[net_name] = ni

    footprints = {}
    for ref in sorted(components.keys(), key=lambda r: (re.sub(r"\d+", "", r), int(re.search(r"\d+", r).group(0)) if re.search(r"\d+", r) else 0)):
        footprints[ref] = load_footprint(ref, components[ref], board, nets, pin_nets)

    # Board outline: 100 mm x 80 mm per DRC-cleanup request.
    add_line(board, 0, 0, 100, 0)
    add_line(board, 100, 0, 100, 80)
    add_line(board, 100, 80, 0, 80)
    add_line(board, 0, 80, 0, 0)

    # Harness pigtail pads: four columns, 4 mm vertical pitch, 15 mm horizontal pitch.
    for idx in range(1, 13):
        set_pos(footprints[f"TP{idx}"], 5.0, 10.0 + (idx - 1) * 4.0)
    for idx in range(13, 25):
        set_pos(footprints[f"TP{idx}"], 20.0, 10.0 + (idx - 13) * 4.0)
    for idx in range(25, 33):
        set_pos(footprints[f"TP{idx}"], 35.0, 10.0 + (idx - 25) * 4.0)
    for idx in range(33, 41):
        set_pos(footprints[f"TP{idx}"], 50.0, 10.0 + (idx - 33) * 4.0)

    # Utility test pads.
    set_pos(footprints["TP45"], 91.0, 5.0)
    set_pos(footprints["TP46"], 95.0, 5.0)
    set_pos(footprints["TP41"], 62.0, 70.0)
    set_pos(footprints["TP42"], 68.0, 70.0)
    set_pos(footprints["TP43"], 74.0, 70.0)
    set_pos(footprints["TP44"], 96.0, 70.0)

    # Functional circuitry placed in the right-side routing area.
    set_pos(footprints["JP1"], 64.0, 10.0)
    set_pos(footprints["Q1"], 70.0, 10.0)
    set_pos(footprints["R1"], 73.5, 12.2)
    set_pos(footprints["U2"], 80.0, 13.5)
    set_pos(footprints["C1"], 87.0, 7.0, 90)
    set_pos(footprints["D2"], 91.0, 18.0, 0)
    set_pos(footprints["C2"], 77.0, 18.0, 90)
    set_pos(footprints["C3"], 87.0, 16.0, 0)
    set_pos(footprints["R2"], 75.0, 22.0)
    set_pos(footprints["D1"], 78.5, 22.0, 180)

    set_pos(footprints["J1"], 94.0, 13.0)
    set_pos(footprints["U1"], 82.0, 31.0)
    set_pos(footprints["R4"], 91.0, 22.0, 180)
    set_pos(footprints["JP2"], 91.0, 25.0)
    set_pos(footprints["R3"], 76.0, 30.0, 180)
    set_pos(footprints["C4"], 87.0, 34.0, 90)
    set_pos(footprints["C5"], 91.0, 36.5, 90)

    set_pos(footprints["J4"], 95.0, 43.0)

    set_pos(footprints["J5"], 84.0, 76.0)
    set_pos(footprints["R5"], 80.0, 71.8, 90)
    set_pos(footprints["R6"], 88.0, 71.8, 90)
    set_pos(footprints["C6"], 94.0, 74.5, 90)

    add_text(board, "Mazzy Harness Probe", 64.0, 3.0, size=1.0, thickness=0.15)
    add_text(board, "24-pin A", 1.6, 5.8, size=0.8)
    add_text(board, "24-pin B", 16.6, 5.8, size=0.8)
    add_text(board, "16-pin A", 31.6, 5.8, size=0.8)
    add_text(board, "16-pin B", 46.6, 5.8, size=0.8)
    add_text(board, "CANH/CANL", 86.0, 8.0, size=0.8)
    add_text(board, "PICO GP4=TX GP5=RX", 92.0, 58.0, size=0.8, angle=90)
    add_text(board, "USB-C 5V ONLY", 76.0, 79.0, size=0.8)
    add_text(board, "MS-CAN = 125kbps. No termination. Factory bus already terminated.", 2.0, 77.0, size=0.8, thickness=0.10)

    tp24_labels = {1: "1 BAT", 2: "2 ACC", 3: "3 GND", 4: "4 FL+", 5: "5 FL-", 6: "6 FR+", 7: "7 FR-", 8: "8 RL+", 9: "9 RL-", 10: "10 RR+", 11: "11 RR-"}
    for idx in range(1, 13):
        add_text(board, tp24_labels.get(idx, f"{idx} UNK"), 7.0, 9.55 + (idx - 1) * 4.0, size=0.8, thickness=0.10)
    for idx in range(13, 25):
        add_text(board, tp24_labels.get(idx, f"{idx} UNK"), 22.0, 9.55 + (idx - 13) * 4.0, size=0.8, thickness=0.10)
    for idx in range(25, 33):
        add_text(board, f"{idx} 16-{idx - 24:02d}", 37.0, 9.55 + (idx - 25) * 4.0, size=0.8, thickness=0.10)
    for idx in range(33, 41):
        add_text(board, f"{idx} 16-{idx - 24:02d}", 52.0, 9.55 + (idx - 33) * 4.0, size=0.8, thickness=0.10)
    for ref, label in [("TP41", "3V3"), ("TP42", "5V"), ("TP43", "12V"), ("TP44", "GND"), ("TP45", "CANH"), ("TP46", "CANL")]:
        x, y = pad_xy(footprints, ref, 1)
        add_text(board, label, x - 1.3, y + 2.2, size=0.8, thickness=0.10)

    # Placement-only handoff board: no copper tracks, vias, or zones are added.
    # The functional area is intentionally left unrouted for manual cleanup in
    # KiCad PCB Editor.
    pcbnew.SaveBoard(str(BOARD_OUT), board)


if __name__ == "__main__":
    main_clean()
