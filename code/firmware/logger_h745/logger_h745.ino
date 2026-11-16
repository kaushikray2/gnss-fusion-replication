// logger_h745.ino - Stage 1 logger, RIG #2 port (Nucleo-H745ZI-Q).
// Forked from the verified logger.ino (70c4e91) the day rig #2 was
// assembled with the same IKS01A3 + AEK stack. Platform deltas:
// core 2.11 has no NUCLEO_H745ZI target, so this builds for the
// GenH7 GENERIC_H745XIHX target; its default Serial is NOT on the
// ST-LINK VCP, so the console is an explicit USART3 object
// (PD8/PD9); Arduino pin numbers are meaningless on the generic
// variant, so D4/D7/LED go through pinNametoDigitalPin (Nucleo-144
// standard: D4=PE14, D7=PG12, LD1=PB0); Wire pins are set
// explicitly (PB9=SDA, PB8=SCL). Flashing is by .bin drag-drop to
// the NOD_H745ZIQ disk (the GenH7 upload method wants
// STM32CubeProgrammer, which is not installed). Everything else -
// format, FIFO pacing, D4-LOW rule, rates - is identical.
//
// Streams ONE unified log on the console (ST-LINK VCP, USART3) at
// 1000000 baud. The recorder is whatever captures the console:
// Serial USB Terminal on the Pixel 7 (owner decision 2026-11-07)
// or a PC capture on the bench. Link rates (owner point: do not
// squeeze into 115200): console 921600, GNSS port 460800
// (CDB 102 = 0xD, set + persisted by gnss_baud; the module table
// tops out at 921600 - no 1000000 entry). The GNSS stream bursts
// ~3 KB per epoch; at 921600 in and 1000000 out, neither side can
// back-pressure the other.
//
// Log format (matches hardware/allan.py exactly):
//   IMU row : t_us,ax,ay,az,gx,gy,gz   (g and dps, plain CSV)
//   GNSS row: G,t_us,$SENTENCE*CS      (verbatim, incl. $PSTMTG
//                                        and $PSTMTS raw lines)
//   Comment : #...                      (headers, #STAT liveness)
// allan.py keys on exactly-7-numeric-field lines, so G/ and #
// rows never pollute the IMU series. t_us is a 64-bit us clock
// (micros() extended across its 71.6-minute wrap) shared by both.
//
// IMU: LSM6DSO (X-NUCLEO-IKS01A3, I2C 0x6B) at 104 Hz, +/-2 g,
// +/-250 dps, paced by its hardware FIFO in continuous mode
// (AN5192: FIFO_CTRL3 BDR 104 Hz = 0x44; FIFO_CTRL4 mode 110).
// Polling output registers re-reads samples (measured 111 Hz vs
// 104 Hz ODR in bring-up); the FIFO is the pacing fix. Sample
// timestamps are back-distributed over each drained batch at the
// exact ODR period, re-anchored every batch.
//
// GNSS: Teseo-LIV3F (AEK-COM-GNSST31), USART1 (D0=PB7 RX,
// D1=PB6 TX) at 921600. Control lines (learned live): D7 (PG12)
// SYS_RESETn pulsed low->HIGH. D4 (PE14) must be driven LOW:
// the i2c_probe phase tests (2026-11-07) showed the LSM6DSO
// answers I2C (0x6B, WHO 0x6C) only while D4 is actively driven
// LOW - HIGH, floating, and even the MCU pull-down all silence
// it (the AEK wake net on the shared D4 header pin drags the
// line; only a hard low wins). The GNSS module streams fine
// with D4 held LOW - the original "D4 HIGH" rule was measured
// before the conflict was understood. The $PSTMTG/$PSTMTS mask
// (CDB 201 bits 8/9) is re-asserted at boot (already saved).

#include <Arduino.h>
#include <Wire.h>

HardwareSerial Console(PD_9, PD_8); // ST-LINK VCP (USART3)
#define Serial Console

HardwareSerial gnssSerial(PB7, PB6); // D0=RX, D1=TX (USART1)
static const uint32_t GNSS_RESET_PIN = pinNametoDigitalPin(PG_12); // D7
static const uint32_t GNSS_WAKEUP_PIN = pinNametoDigitalPin(PE_14); // D4
static uint8_t imuAddr = 0; // LSM6DSO, discovered at boot (0x6A/0x6B)
static const long GNSS_BAUD = 921600;
static const long CONSOLE_BAUD = 1000000;

// ---- 64-bit microsecond clock --------------------------------------
static uint32_t usLast = 0;
static uint64_t usBase = 0;
static uint64_t nowUs() {
  uint32_t m = micros();
  if (m < usLast) usBase += (uint64_t)1 << 32;
  usLast = m;
  return usBase + m;
}

// This core's printf has no %llu (it prints a literal "lu" and
// drops the value - seen live). Format 64-bit timestamps manually.
static void fmtU64(uint64_t v, char *out) {
  char tmp[21]; int i = 0;
  if (v == 0) { out[0] = '0'; out[1] = 0; return; }
  while (v) { tmp[i++] = (char)('0' + (v % 10)); v /= 10; }
  int j = 0; while (i) out[j++] = tmp[--i];
  out[j] = 0;
}

static void fmtFixed(char *out, int32_t scaled, uint8_t decimals) {
  char *o = out;
  uint32_t div = 1;
  for (uint8_t i = 0; i < decimals; i++) div *= 10u;
  uint32_t mag;
  if (scaled < 0) { *o++ = '-'; mag = (uint32_t)(-(scaled + 1)) + 1u; }
  else mag = (uint32_t)scaled;
  uint32_t ip = mag / div;
  char rev[12]; int ri = 0;
  if (ip == 0) rev[ri++] = '0';
  while (ip) { rev[ri++] = (char)('0' + ip % 10); ip /= 10; }
  while (ri) *o++ = rev[--ri];
  *o++ = '.';
  uint32_t fr = mag % div;
  for (int i = (int)decimals - 1; i >= 0; i--) { o[i] = (char)('0' + fr % 10); fr /= 10; }
  o += decimals;
  *o = 0;
}

// ---- LSM6DSO raw I2C -------------------------------------------------
static void imuWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(imuAddr);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}
static void imuRead(uint8_t reg, uint8_t *buf, uint8_t n) {
  Wire.beginTransmission(imuAddr);
  Wire.write(reg);
  Wire.endTransmission(false);
  Wire.requestFrom(imuAddr, n);
  for (uint8_t i = 0; i < n; i++) buf[i] = Wire.available() ? (uint8_t)Wire.read() : 0;
}
static uint8_t imuRead1(uint8_t reg) {
  uint8_t v = 0;
  imuRead(reg, &v, 1);
  return v;
}

static void drainGnss(); // defined below; called from drainFifo

// ---- Logger state ----------------------------------------------------
static const float ACC_G = 0.000061f;   // +/-2 g
static const float GYR_DPS = 0.00875f;  // +/-250 dps
static const uint32_t ODR_PERIOD_US = 9615; // 1e6 / 104
static uint32_t cntImu = 0, cntGnss = 0, cntLong = 0;
static uint32_t gnssBytes = 0; // every byte drainGnss has ever read
static uint16_t fifoHighWater = 0;
static uint64_t lastImuT = 0;

// One FIFO drain: read all pending words, assemble gyro+accel
// pairs, stamp them back from the drain anchor at the ODR period,
// then emit in order. Tag byte >> 3: 0x01 = gyro, 0x02 = accel.
static void drainFifo() {
  if (!imuAddr) return;
  uint16_t diff = imuRead1(0x3A) | ((uint16_t)(imuRead1(0x3B) & 0x03) << 8);
  if (diff > fifoHighWater) fifoHighWater = diff;
  if (diff == 0) return;
  if (diff > 120) diff = 120; // bounded batch; loop() drains the rest
  uint64_t anchor = nowUs();
  static int16_t pg[120][3], pa[120][3];
  int16_t cg[3] = {0, 0, 0}, ca[3] = {0, 0, 0};
  bool hg = false, ha = false;
  uint8_t np = 0;
  for (uint16_t i = 0; i < diff; i++) {
    drainGnss(); // every word: the 921600 UART buffer is shallow
    uint8_t w[7];
    imuRead(0x78, w, 7);
    uint8_t sensor = w[0] >> 3;
    int16_t v0 = (int16_t)(w[1] | (w[2] << 8));
    int16_t v1 = (int16_t)(w[3] | (w[4] << 8));
    int16_t v2 = (int16_t)(w[5] | (w[6] << 8));
    if (sensor == 0x01) { cg[0]=v0; cg[1]=v1; cg[2]=v2; hg = true; }
    else if (sensor == 0x02) { ca[0]=v0; ca[1]=v1; ca[2]=v2; ha = true; }
    else continue;
    if (hg && ha && np < 120) {
      hg = ha = false;
      memcpy(pg[np], cg, sizeof(cg));
      memcpy(pa[np], ca, sizeof(ca));
      np++;
    }
  }
  for (uint8_t i = 0; i < np; i++) {
    uint64_t t = anchor - (uint64_t)(np - 1 - i) * ODR_PERIOD_US;
    if (t <= lastImuT) t = lastImuT + ODR_PERIOD_US;
    lastImuT = t;
    // Exact integer scaling, no float printf: accel LSB = 61 ug
    // (0.061 mg), gyro LSB = 875 x 1e-5 dps (8.75 mdps).
    char tb[24]; fmtU64(t, tb);
    char ax[16], ay[16], az[16], gx[16], gy[16], gz[16];
    fmtFixed(ax, (int32_t)pa[i][0] * 61, 6);
    fmtFixed(ay, (int32_t)pa[i][1] * 61, 6);
    fmtFixed(az, (int32_t)pa[i][2] * 61, 6);
    fmtFixed(gx, (int32_t)pg[i][0] * 875, 5);
    fmtFixed(gy, (int32_t)pg[i][1] * 875, 5);
    fmtFixed(gz, (int32_t)pg[i][2] * 875, 5);
    char b[128];
    int n = snprintf(b, sizeof(b), "%s,%s,%s,%s,%s,%s,%s\r\n",
                     tb, ax, ay, az, gx, gy, gz);
    Serial.write((const uint8_t *)b, n);
    cntImu++;
    drainGnss(); // every row, same reason
  }
}

// GNSS: assemble sentences byte-wise; on LF, emit verbatim with the
// arrival timestamp. Overlong lines are dropped and counted.
static char gLine[640];
static uint16_t gLen = 0;
static void drainGnss() {
  while (gnssSerial.available()) {
    char c = (char)gnssSerial.read();
    gnssBytes++;
    if (c == '\r') continue;
    if (c == '\n') {
      if (gLen > 0) {
        gLine[gLen] = 0;
        char tb[24]; fmtU64(nowUs(), tb);
        char b[720];
        int n = snprintf(b, sizeof(b), "G,%s,%s\r\n", tb, gLine);
        Serial.write((const uint8_t *)b, n);
        cntGnss++;
        gLen = 0;
      }
      continue;
    }
    if (gLen < sizeof(gLine) - 1) gLine[gLen++] = c;
    else { gLen = 0; cntLong++; }
  }
}

static void gnssCmd(const char *body) {
  uint8_t cs = 0;
  for (const char *p = body; *p; p++) cs ^= (uint8_t)*p;
  char line[96];
  snprintf(line, sizeof(line), "$%s*%02X\r\n", body, cs);
  gnssSerial.print(line);
}

void setup() {
  Serial.begin(CONSOLE_BAUD);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 3000) { }
  Serial.println(F("# logger v1 - Stage 1 phone-capture edition"));
  Serial.println(F("# format: t_us,ax,ay,az,gx,gy,gz | G,t_us,$sentence | # comments"));
  pinMode(pinNametoDigitalPin(PB_0), OUTPUT); // LD1
  // D4 (SYS_WAKEUP) LOW from the very top of setup: rig #2's module
  // only ever booted into streaming when its wake pin had been
  // held LOW for seconds before the reset pulse (the staged
  // diagnostic), never when D4 was driven LOW moments before it.
  pinMode(GNSS_WAKEUP_PIN, OUTPUT);
  digitalWrite(GNSS_WAKEUP_PIN, LOW);

  // GNSS module bring-up: open the port, pulse reset, drain
  // through a 4 s boot window and CHECK that bytes arrived; if
  // the module stayed silent, pulse again (max 3 attempts) and
  // report each attempt in the header. Rig #2 (2026-11-07) made
  // this necessary: the identical logger binary both passed and
  // failed against different pre-existing module states, while
  // the minimal diag sketches revived the module every time -
  // the module's boot response depends on state the MCU cannot
  // observe, so the handshake is verified, not assumed. The
  // TG/TS SETPAR goes out only once the module provably streams.
  gnssSerial.begin(GNSS_BAUD);
  bool gnssUp = false;
  for (int att = 1; att <= 3 && !gnssUp; att++) {
    pinMode(GNSS_RESET_PIN, OUTPUT);
    digitalWrite(GNSS_RESET_PIN, HIGH);
    delay(50);
    digitalWrite(GNSS_RESET_PIN, LOW);
    delay(100);
    digitalWrite(GNSS_RESET_PIN, HIGH);
    uint32_t before = gnssBytes;
    uint32_t w0 = millis();
    while (millis() - w0 < 4000) drainGnss();
    gnssUp = (gnssBytes - before) > 200;
    Serial.print(F("# GNSS boot attempt "));
    Serial.print(att);
    Serial.print(F(": "));
    Serial.print(gnssBytes - before);
    Serial.println(F(" bytes"));
  }
  if (gnssUp) {
    gnssCmd("PSTMSETPAR,1201,0x300,1"); // $PSTMTG + $PSTMTS on
    Serial.println(F("# GNSS at 921600, TG/TS mask asserted"));
  } else {
    Serial.println(F("# GNSS SILENT after 3 boot attempts"));
  }
  Serial.println(F("# STREAM START"));
  // IMU: census-style discovery (either strap address), then the
  // FIFO-paced 104 Hz configuration. If the sensor is absent the
  // logger still streams GNSS; the header says so plainly.
  Wire.setSDA(PB_9);
  Wire.setSCL(PB_8);
  Wire.begin();
  Wire.setClock(400000); // LSM6DSO fast mode; shortens FIFO drains
  for (uint8_t a = 0x6A; a <= 0x6B && !imuAddr; a++) {
    Wire.beginTransmission(a);
    Wire.write(0x0F);
    if (Wire.endTransmission(false) != 0) continue;
    if (Wire.requestFrom(a, (uint8_t)1) == 1 && Wire.read() == 0x6C) imuAddr = a;
  }
  if (imuAddr) {
    Serial.print(F("# LSM6DSO found at 0x"));
    Serial.println(imuAddr, HEX);
  } else {
    Serial.println(F("# LSM6DSO NOT FOUND on I2C - GNSS-only logging"));
  }
  if (imuAddr) {
  imuWrite(0x0A, 0x00);       // FIFO_CTRL4: bypass (flush)
  imuWrite(0x12, 0x44);       // CTRL3_C: BDU + IF_INC
  imuWrite(0x10, 0x40);       // CTRL1_XL: 104 Hz, +/-2 g
  imuWrite(0x11, 0x40);       // CTRL2_G: 104 Hz, +/-250 dps
  imuWrite(0x09, 0x44);       // FIFO_CTRL3: BDR gyro+accel 104 Hz
  imuWrite(0x0A, 0x06);       // FIFO_CTRL4: continuous FIFO mode
  Serial.println(F("# IMU configured: FIFO continuous, 104 Hz"));
  }
  Serial.println(F("# STREAM START"));
}

void loop() {
  static uint32_t lastStat = 0;
  drainGnss();
  drainFifo();
  if (millis() - lastStat >= 10000) {
    lastStat = millis();
    digitalWrite(pinNametoDigitalPin(PB_0), !digitalRead(pinNametoDigitalPin(PB_0)));
    char b[128];
    int n = snprintf(b, sizeof(b),
                     "#STAT t_s=%lu imu=%lu gnss=%lu long=%lu fifomax=%u\r\n",
                     (unsigned long)(nowUs() / 1000000ULL),
                     (unsigned long)cntImu, (unsigned long)cntGnss,
                     (unsigned long)cntLong, fifoHighWater);
    Serial.write((const uint8_t *)b, n);
  }
}
