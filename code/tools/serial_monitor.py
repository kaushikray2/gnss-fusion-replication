#!/usr/bin/env python3
"""Serial monitor for the GNSS/IMU logger rigs (Nucleo +
AEK-COM-GNSST31 / Teseo-LIV3F).

- Connects to the ST-LINK VCP (console baud 1000000) or
  replays an existing capture file.
- Logs every received line to a file in the established
  capture format - 'HH:MM:SS.mmm <raw line>' - so files
  stay compatible with strip_host_prefix.py and the
  analysis tools.
- Decodes live: GGA fix quality / satellites / HDOP /
  position, RMC speed / course / date, $PSTMTS tracked
  SVs and CN0 (rolling 3 s median), $PSTMTG TOW and
  receiver clock NCO, IMU sample rate and latest values.
- Big FIX and TS-FLOW lamps: the field check for a real
  blockage (a proper cover kills the fix within seconds;
  a leaking shield only drops CN0 - see experiment 4
  phase B run 1, 2026-11-08).
- Event marker buttons (COVER / UNCOVER / note) write
  '#MARK ...' lines into the log carrying the elapsed
  time and the fix / CN0 state at that moment, so event
  windows are recoverable from the file alone - no paper
  time sheet needed.

Headless check:  serial_monitor.py --selftest CAPTURE.txt
Requires: pyserial (GUI + serial), tkinter (GUI only).
"""
import argparse
import math
import os
import queue
import re
import sys
import threading
import time
from collections import deque

HOST_PREFIX = re.compile(r'^\d{2}:\d{2}:\d{2}\.\d{3} ')
QUAL_TXT = {0: 'NO FIX', 1: 'GPS FIX', 2: 'DGPS FIX', 4: 'RTK FIXED',
            5: 'RTK FLOAT', 6: 'ESTIMATED'}


def wall_stamp(t=None):
    t = time.localtime(t)
    return time.strftime('%H:%M:%S', t) + f'.{int((time.time() % 1) * 1000):03d}'


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return float('nan')
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def ddmm_to_deg(v, hemi):
    try:
        x = float(v)
    except ValueError:
        return float('nan')
    deg = int(x // 100)
    out = deg + (x - 100 * deg) / 60.0
    return -out if hemi in ('S', 'W') else out


class Decoder:
    """State machine for one logger stream. feed() takes a
    raw capture line (with or without host prefix, G-framed
    or bare) plus a monotonic timestamp; all decoded state
    is read back off the instance."""

    def __init__(self):
        self.lines = 0
        self.imu_rows = 0
        self.imu_last = None          # (ax, ay, az, gx, gy, gz) in g / dps
        self.imu_times = deque()      # monotonic times of recent IMU rows
        self.logger_t_us = None
        self.fix_qual = None
        self.fix_time = 0.0           # monotonic time of last qual>=1 GGA
        self.any_gga_time = 0.0
        self.nsat = None
        self.hdop = None
        self.lat = float('nan')
        self.lon = float('nan')
        self.alt = float('nan')
        self.utc = '--:--:--'
        self.date = '--/--/--'
        self.speed_kmh = float('nan')
        self.course = float('nan')
        self.ts_rows = deque()        # (t, satid, cn0), dsp=1 & satdat=1 only
        self.ts_last = 0.0
        self.tg_tow = None
        self.tg_totsat = None
        self.nco = None
        self.stat = ''

    # -- derived values -------------------------------------------------
    def cn0_window(self, now, span=3.0):
        while self.ts_rows and self.ts_rows[0][0] < now - span:
            self.ts_rows.popleft()
        return self.ts_rows

    def cn0_median(self, now):
        w = self.cn0_window(now)
        return median([c for _, _, c in w]) if w else float('nan')

    def sv_count(self, now):
        return len({s for _, s, _ in self.cn0_window(now)})

    def imu_rate(self, now, span=2.0):
        while self.imu_times and self.imu_times[0] < now - span:
            self.imu_times.popleft()
        return len(self.imu_times) / span if self.imu_times else 0.0

    def fix_alive(self, now):
        return self.fix_qual is not None and self.fix_qual >= 1 and now - self.fix_time <= 3.0

    def ts_flowing(self, now):
        return now - self.ts_last <= 3.0 if self.ts_last else False

    # -- feeding ---------------------------------------------------------
    def feed(self, raw, now):
        line = raw.replace('\x00', '').strip()
        line = HOST_PREFIX.sub('', line)
        if not line:
            return
        self.lines += 1
        if line.startswith('#'):
            self.stat = line
            return
        # IMU row: t_us + 6 numeric fields, no framing
        if line[0].isdigit() and ',' in line and '$' not in line:
            f = line.split(',')
            if len(f) == 7:
                try:
                    vals = [float(x) for x in f]
                except ValueError:
                    return
                self.imu_rows += 1
                self.logger_t_us = int(vals[0])
                self.imu_last = tuple(vals[1:])
                self.imu_times.append(now)
            return
        # GNSS: possibly several spliced sentences per line
        starts = [i for i, ch in enumerate(line) if ch == '$']
        for i, st in enumerate(starts):
            en = starts[i + 1] if i + 1 < len(starts) else len(line)
            self._sentence(line[st:en], now)

    def _sentence(self, seg, now):
        body = seg.split('*')[0]
        f = body.split(',')
        tag = f[0]
        if tag in ('$GPGGA', '$GNGGA') and len(f) >= 10:
            self.any_gga_time = now
            try:
                self.fix_qual = int(f[6])
                self.nsat = int(f[7])
                self.hdop = float(f[8])
                self.alt = float(f[9])
            except ValueError:
                pass
            if f[2] and f[4]:
                self.lat = ddmm_to_deg(f[2], f[3])
                self.lon = ddmm_to_deg(f[4], f[5])
            if f[1]:
                self.utc = f'{f[1][0:2]}:{f[1][2:4]}:{f[1][4:6]}'
            if self.fix_qual is not None and self.fix_qual >= 1:
                self.fix_time = now
        elif tag in ('$GPRMC', '$GNRMC') and len(f) >= 10:
            if f[1]:
                self.utc = f'{f[1][0:2]}:{f[1][2:4]}:{f[1][4:6]}'
            if f[2] == 'A':
                if f[3] and f[5]:
                    self.lat = ddmm_to_deg(f[3], f[4])
                    self.lon = ddmm_to_deg(f[5], f[6])
                try:
                    self.speed_kmh = float(f[7]) * 1.852
                    self.course = float(f[8])
                except ValueError:
                    pass
            if len(f) >= 10 and f[9]:
                self.date = f'{f[9][0:2]}/{f[9][2:4]}/20{f[9][4:6]}'
        elif tag == '$PSTMTS' and len(f) >= 9:
            try:
                dsp, satid, cn0, satdat = int(f[1]), int(f[2]), float(f[6]), int(f[8])
            except ValueError:
                return
            if dsp == 1 and satdat == 1:
                self.ts_rows.append((now, satid, cn0))
                self.ts_last = now
        elif tag == '$PSTMTG' and len(f) >= 7:
            try:
                self.tg_tow = float(f[2])
                self.tg_totsat = int(f[3])
                self.nco = float(f[6])
            except ValueError:
                pass


def selftest(path):
    """Headless decode check on a capture file. Uses the
    host-prefix wall clock as 'now' when present, else the
    logger t_us, so the rolling windows behave as live."""
    dec = Decoder()
    cn0_all = []
    bins = {}
    ncos = []
    quals = {}
    ts_prev = fix_prev = None
    ts_gap = fix_gap = 0.0
    t_first = t_last = None
    clk = re.compile(r'^(\d{2}):(\d{2}):(\d{2})\.(\d{3}) ')
    with open(path, errors='replace') as fh:
        for raw in fh:
            m = clk.match(raw)
            now = (int(m.group(1)) * 3600 + int(m.group(2)) * 60 +
                   int(m.group(3)) + int(m.group(4)) / 1000.0) if m else None
            before_ts = len(dec.ts_rows)
            dec.feed(raw, now if now is not None else 0.0)
            if now is None:
                continue
            if t_first is None:
                t_first = now
            t_last = now
            if len(dec.ts_rows) > before_ts:
                _, _, c = dec.ts_rows[-1]
                cn0_all.append(c)
                bins.setdefault(int(now // 30), []).append(c)
                if ts_prev is not None:
                    ts_gap = max(ts_gap, now - ts_prev)
                ts_prev = now
            if dec.any_gga_time and dec.fix_qual is not None:
                pass
            if '$PSTMTG' in raw and dec.nco is not None:
                ncos.append(dec.nco)
    # fix-gap scan needs per-GGA times; redo cheaply from decoder state is
    # not possible, so report qual histogram via a second light pass
    with open(path, errors='replace') as fh:
        last_fix = None
        for raw in fh:
            m = clk.match(raw)
            if not m or 'GGA' not in raw:
                continue
            now = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            f = raw[raw.index('$'):].split('*')[0].split(',')
            try:
                q = int(f[6])
            except (ValueError, IndexError):
                continue
            quals[q] = quals.get(q, 0) + 1
            if q >= 1:
                if last_fix is not None:
                    fix_gap = max(fix_gap, now - last_fix)
                last_fix = now
    span = (t_last - t_first) if t_first is not None else 0.0
    bin_meds = [median(v) for v in bins.values() if v]
    print(f'file span (host clock): {span:.1f} s')
    print(f'lines fed: {dec.lines}, IMU rows: {dec.imu_rows}')
    print(f'GGA quality histogram: {dict(sorted(quals.items()))}')
    print(f'longest gap between fixes: {fix_gap:.1f} s; between TS rows: {ts_gap:.2f} s')
    if cn0_all:
        print(f'CN0 overall median: {median(cn0_all):.1f} dB-Hz; '
              f'30 s-bin medians min {min(bin_meds):.1f}, max {max(bin_meds):.1f}')
    else:
        print('CN0: no usable $PSTMTS rows in file (no fix / antenna off)')
    print(f'TG NCO median: {median(ncos):.0f} Hz over {len(ncos)} TG lines')
    print(f'final fix: qual {dec.fix_qual}, sats {dec.nsat}, HDOP {dec.hdop}, '
          f'lat {dec.lat:.6f}, lon {dec.lon:.6f}')
    return 0


class MonitorApp:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root = root
        root.title('GNSS Logger Monitor')
        self.dec = Decoder()
        self.q = queue.Queue()
        self.ser = None
        self.reader = None
        self.stop_flag = threading.Event()
        self.log_fh = None
        self.log_lock = threading.Lock()
        self.t0 = None               # monotonic connect/replay start
        self.capture_start = None    # wall time logging started
        self.capture_stop = None
        self.events = []
        self._build()
        for w in self._all_widgets(self.root):
            if w.winfo_class() in ('Button', 'TButton'):
                # Buttons must never keep keyboard focus: a
                # focused button eats the space bar (it re-fires
                # on key release), which double-marked every
                # checkpoint in the 2026-11-14 walk capture.
                w.config(takefocus=0)
        self.root.after(100, self._poll)

    # ------------------------------------------------------------ UI --
    @staticmethod
    def _all_widgets(w):
        yield w
        for c in w.winfo_children():
            yield from MonitorApp._all_widgets(c)

    def _build(self):
        tk, ttk = self.tk, self.ttk
        top = ttk.Frame(self.root, padding=6)
        top.grid(row=0, column=0, sticky='ew')
        ttk.Label(top, text='Port').grid(row=0, column=0)
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(top, textvariable=self.port_var, width=22)
        self.port_box.grid(row=0, column=1, padx=2)
        ttk.Button(top, text='Refresh', command=self._refresh_ports).grid(row=0, column=2)
        ttk.Label(top, text='Baud').grid(row=0, column=3)
        self.baud_var = tk.StringVar(value='1000000')
        ttk.Entry(top, textvariable=self.baud_var, width=9).grid(row=0, column=4, padx=2)
        self.conn_btn = ttk.Button(top, text='Connect', command=self._toggle_connect)
        self.conn_btn.grid(row=0, column=5, padx=2)
        ttk.Button(top, text='Replay file...', command=self._replay).grid(row=0, column=6, padx=2)
        self._refresh_ports()

        log = ttk.LabelFrame(self.root, text='Capture', padding=6)
        log.grid(row=1, column=0, sticky='ew', padx=6)
        self.file_var = tk.StringVar(value=self._default_name())
        ttk.Entry(log, textvariable=self.file_var, width=44).grid(row=0, column=0, columnspan=3, sticky='ew')
        self.cap_btn = ttk.Button(log, text='Start capture', command=self._toggle_capture)
        self.cap_btn.grid(row=0, column=3, padx=4)
        self.cap_lbl = ttk.Label(log, text='not capturing')
        self.cap_lbl.grid(row=1, column=0, columnspan=4, sticky='w')

        lamps = ttk.Frame(self.root, padding=6)
        lamps.grid(row=2, column=0, sticky='ew')
        self.fix_lamp = tk.Label(lamps, text='NO FIX', font=('Helvetica', 20, 'bold'),
                                 bg='#8b0000', fg='white', width=12)
        self.fix_lamp.grid(row=0, column=0, padx=4)
        self.ts_lamp = tk.Label(lamps, text='TS IDLE', font=('Helvetica', 14, 'bold'),
                                bg='#555555', fg='white', width=12)
        self.ts_lamp.grid(row=0, column=1, padx=4)
        self.elapsed_lbl = tk.Label(lamps, text='00:00:00', font=('Helvetica', 16))
        self.elapsed_lbl.grid(row=0, column=2, padx=8)

        grid = ttk.Frame(self.root, padding=6)
        grid.grid(row=3, column=0, sticky='nsew')
        self.tiles = {}
        specs = [
            ('Signal CN0 (dB-Hz)', 'cn0', 16), ('Tracked SVs', 'svs', 8),
            ('Fix', 'fix', 10), ('Sats used', 'nsat', 8),
            ('HDOP', 'hdop', 8), ('UTC / date', 'utc', 20),
            ('Latitude', 'lat', 14), ('Longitude', 'lon', 14),
            ('Altitude (m)', 'alt', 10), ('Speed (km/h)', 'spd', 10),
            ('Clock NCO (Hz)', 'nco', 12), ('TOW (s)', 'tow', 12),
            ('IMU rate (Hz)', 'imu', 10), ('Lines', 'lines', 10),
        ]
        for i, (label, key, w) in enumerate(specs):
            lf = ttk.LabelFrame(grid, text=label, padding=4)
            lf.grid(row=i // 4, column=i % 4, sticky='ew', padx=3, pady=3)
            var = tk.StringVar(value='-')
            tk.Label(lf, textvariable=var, font=('Helvetica', 13, 'bold'), width=w).grid()
            self.tiles[key] = var
        self.imu_lbl = ttk.Label(grid, text='IMU: -')
        self.imu_lbl.grid(row=4, column=0, columnspan=4, sticky='w')

        ev = ttk.LabelFrame(self.root, text='Event markers (written into the log)', padding=6)
        ev.grid(row=4, column=0, sticky='ew', padx=6)
        for i, name in enumerate(('EXPERIMENT START', 'EXPERIMENT STOP', 'COVER', 'COVER OFF')):
            ttk.Button(ev, text=name, command=lambda n=name: self._mark(n)).grid(row=0, column=i, padx=3, pady=2)
        self.note_var = tk.StringVar()
        ttk.Entry(ev, textvariable=self.note_var, width=28).grid(row=1, column=0, columnspan=3, sticky='ew', pady=2)
        ttk.Button(ev, text='NOTE', command=self._note).grid(row=1, column=3, padx=3)
        self.ev_list = tk.Listbox(self.root, height=5)
        self.ev_list.grid(row=5, column=0, sticky='ew', padx=6, pady=4)
        self.tail = tk.Text(self.root, height=6, font=('Courier', 8))
        self.tail.grid(row=6, column=0, sticky='ew', padx=6, pady=4)

    @staticmethod
    def _default_name():
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(here, time.strftime('capture-%Y%m%d-%H%M%S.txt'))

    def _refresh_ports(self):
        try:
            from serial.tools import list_ports
            ports = [p.device for p in list_ports.comports()]
        except Exception:
            ports = []
        self.port_box['values'] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    # ---------------------------------------------------------- logic --
    def _toggle_connect(self):
        if self.ser is not None:
            self.stop_flag.set()
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
            self.conn_btn.config(text='Connect')
            return
        import serial
        try:
            self.ser = serial.Serial(self.port_var.get(),
                                     int(self.baud_var.get()), timeout=0.2)
        except Exception as e:
            self.cap_lbl.config(text=f'connect failed: {e}')
            self.ser = None
            return
        self.stop_flag.clear()
        self.t0 = time.monotonic()
        self.reader = threading.Thread(target=self._serial_reader, daemon=True)
        self.reader.start()
        self.conn_btn.config(text='Disconnect')

    def _serial_reader(self):
        while not self.stop_flag.is_set() and self.ser is not None:
            try:
                raw = self.ser.readline()
            except Exception:
                break
            if raw:
                self.q.put(('live', raw.decode('ascii', 'ignore')))

    def _replay(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title='Replay capture file')
        if not path:
            return
        self.stop_flag.clear()
        self.t0 = time.monotonic()
        threading.Thread(target=self._replay_reader, args=(path,), daemon=True).start()

    def _replay_reader(self, path):
        with open(path, errors='replace') as fh:
            for i, raw in enumerate(fh):
                if self.stop_flag.is_set():
                    break
                self.q.put(('replay', raw))
                if i % 200 == 0:
                    time.sleep(0.05)

    def _write_log(self, payload):
        if self.log_fh is None:
            return
        with self.log_lock:
            self.log_fh.write(f'{wall_stamp()} {payload}\n')
            self.log_fh.flush()

    def _elapsed(self):
        if self.t0 is None:
            return '00:00:00'
        s = int(time.monotonic() - self.t0)
        return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'

    def _toggle_capture(self):
        if self.log_fh is not None:
            self._mark('CAPTURE STOP')
            with self.log_lock:
                self.log_fh.close()
            self.log_fh = None
            self.capture_stop = wall_stamp()
            self.cap_btn.config(text='Start capture')
            self.cap_lbl.config(
                text=f'started {self.capture_start}  ->  stopped {self.capture_stop}')
            return
        path = self.file_var.get()
        self.log_fh = open(path, 'a', buffering=1)
        self.capture_start = wall_stamp()
        self.capture_stop = None
        self.cap_btn.config(text='Stop capture')
        self.cap_lbl.config(text=f'capturing since {self.capture_start}  ->  {path}')
        self._mark('CAPTURE START')

    def _mark(self, name):
        if self.log_fh is None:
            # A marker press means an experiment is running:
            # never let it (or the data) vanish silently
            # because Start capture was not pressed first.
            self._toggle_capture()
        now = time.monotonic()
        med = self.dec.cn0_median(now)
        cn0 = f'{med:.0f}' if med == med else '-'
        payload = (f'#MARK,{name},elapsed={self._elapsed()},'
                   f'fix={self.dec.fix_qual},cn0={cn0},svs={self.dec.sv_count(now)}')
        self._write_log(payload)
        entry = f'{wall_stamp()}  {name}  (elapsed {self._elapsed()}, fix {self.dec.fix_qual}, CN0 {cn0})'
        self.events.append(entry)
        self.ev_list.insert(0, entry)

    def _note(self):
        txt = self.note_var.get().strip()
        if txt:
            self._mark('NOTE: ' + txt)
            self.note_var.set('')

    def _poll(self):
        now = time.monotonic()
        tail_lines = []
        while True:
            try:
                src, raw = self.q.get_nowait()
            except queue.Empty:
                break
            line = raw.replace('\x00', '').rstrip('\r\n')
            if not line.strip():
                continue
            self.dec.feed(line, now)
            if src == 'live':
                self._write_log(HOST_PREFIX.sub('', line.strip()))
            tail_lines.append(line.strip()[:110])
        if tail_lines:
            self.tail.insert('end', '\n'.join(tail_lines) + '\n')
            n = int(self.tail.index('end-1c').split('.')[0])
            if n > 220:
                self.tail.delete('1.0', f'{n - 200}.0')
            self.tail.see('end')
        self._refresh(now)
        self.root.after(100, self._poll)

    def _refresh(self, now):
        d = self.dec
        if d.fix_alive(now):
            self.fix_lamp.config(bg='#006400', text='FIX OK')
        else:
            self.fix_lamp.config(bg='#8b0000', text='NO FIX')
        if d.ts_flowing(now):
            self.ts_lamp.config(bg='#006400', text='TS FLOWING')
        else:
            self.ts_lamp.config(bg='#555555', text='TS IDLE')
        self.elapsed_lbl.config(text=self._elapsed())
        med = d.cn0_median(now)
        self.tiles['cn0'].set(f'{med:.1f}' if med == med else '-')
        self.tiles['svs'].set(str(d.sv_count(now)))
        self.tiles['fix'].set(QUAL_TXT.get(d.fix_qual, '-') if d.fix_qual is not None else '-')
        self.tiles['nsat'].set(str(d.nsat) if d.nsat is not None else '-')
        self.tiles['hdop'].set(f'{d.hdop:.2f}' if d.hdop is not None else '-')
        self.tiles['utc'].set(f'{d.utc} / {d.date}')
        self.tiles['lat'].set(f'{d.lat:.6f}' if d.lat == d.lat else '-')
        self.tiles['lon'].set(f'{d.lon:.6f}' if d.lon == d.lon else '-')
        self.tiles['alt'].set(f'{d.alt:.1f}' if d.alt == d.alt else '-')
        self.tiles['spd'].set(f'{d.speed_kmh:.1f}' if d.speed_kmh == d.speed_kmh else '-')
        self.tiles['nco'].set(f'{d.nco:.0f}' if d.nco is not None else '-')
        self.tiles['tow'].set(f'{d.tg_tow:.1f}' if d.tg_tow is not None else '-')
        self.tiles['imu'].set(f'{d.imu_rate(now):.0f}')
        self.tiles['lines'].set(str(d.lines))
        if d.imu_last:
            a, g = d.imu_last[:3], d.imu_last[3:]
            self.imu_lbl.config(
                text='IMU  accel g: ' + ' '.join(f'{x:+.3f}' for x in a) +
                     '   gyro dps: ' + ' '.join(f'{x:+.2f}' for x in g))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--selftest', metavar='FILE',
                    help='headless decode check on a capture file, then exit')
    args = ap.parse_args()
    if args.selftest:
        return selftest(args.selftest)
    import tkinter as tk
    root = tk.Tk()
    MonitorApp(root)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
