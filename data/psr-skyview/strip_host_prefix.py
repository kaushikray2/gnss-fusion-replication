#!/usr/bin/env python3
"""Strip the capture host's per-line local-time prefix
('HH:MM:SS.mmm ') from GNSS_Data.txt, producing the native
logger format (IMU rows, # lines, 'G,t_us,$SENTENCE' rows)
that hardware/psr_residue.py and simulation/replay.py read.
The 'G,t_us,' framing is the logger's own and is KEPT.
Usage: strip_host_prefix.py GNSS_Data.txt > GNSS_Data.hostclean.txt
"""
import re
import sys

host = re.compile(r'^\d{2}:\d{2}:\d{2}\.\d{3} ')
data = open(sys.argv[1], 'rb').read().replace(b'\x00', b'')
for ln in data.decode('ascii', 'ignore').splitlines():
    ln = host.sub('', ln.strip())
    if ln:
        print(ln)
