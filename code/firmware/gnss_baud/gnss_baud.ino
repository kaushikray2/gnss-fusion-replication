// gnss_baud.ino - Firmware step 1: set the Teseo-LIV3F (AEK-COM-
// GNSST31) NMEA port to 921600 baud, persisted in the module NVM.
//
// Target: Nucleo-H563ZI, GNSS UART on D0=RX(PB7) / D1=TX(PB6) =
// USART1. Console on the ST-LINK VCP (USART3) at 115200.
//
// Why 921600: the owner wants ~1 Mbaud links. CDB-ID 102 (UM2229
// Rev 5, Table 200) has no 1000000 entry - its maximum is
// 0xD = 921600, so the module runs at 921600 and the logger
// console (a free-running USART) runs at exactly 1000000.
//
// The sketch is idempotent: it probes the target rate first, then
// 115200, then the 9600 factory default. From whichever rate the
// module answers at, it issues $PSTMSETPAR,1102,0xD (the block digit
// is ignored on SET - writes Current config), $PSTMSAVEPAR to
// persist, and $PSTMSRR to reboot, then verifies at 460800.
// Checksums are computed in code (NMEA XOR).
//
// Board control lines (AEK schematic; learned live 2026-11-07):
// D7 (PG12) -> SYS_RESETn (J13) -> module RESETn, pulsed;
// D4 (PE14) -> SYS_WAKEUP (J7) -> module Wake-Up, driven HIGH.
// Without both, the module never streams.

#include <Arduino.h>

HardwareSerial gnssSerial(PB7, PB6); // D0=RX, D1=TX (USART1)
static const uint8_t GNSS_RESET_PIN = 7;  // Arduino D7
static const uint8_t GNSS_WAKEUP_PIN = 4; // Arduino D4
static const long TARGET_BAUD = 921600;
static long monitorBaud = TARGET_BAUD;

static void sendCmd(const char *body) {
  uint8_t cs = 0;
  for (const char *p = body; *p; p++) cs ^= (uint8_t)*p;
  char line[96];
  snprintf(line, sizeof(line), "$%s*%02X\r\n", body, cs);
  gnssSerial.print(line);
  Serial.print(F("[step1] sent: "));
  Serial.print(line);
}

// Echo GNSS bytes for ms; returns count of PRINTABLE bytes. A line
// held low delivers endless 0x00 framing bytes - those never count
// as the module answering (75k NULs taught us this, 2026-11-07).
static uint32_t echoFor(uint32_t ms, const char *tag) {
  uint32_t t0 = millis(), n = 0;
  bool lineStart = true;
  while (millis() - t0 < ms) {
    while (gnssSerial.available()) {
      char c = (char)gnssSerial.read();
      if (c >= 0x20 && c < 0x7F) n++;
      if (lineStart) { Serial.print(tag); lineStart = false; }
      Serial.write(c);
      if (c == '\n') lineStart = true;
    }
  }
  return n;
}

// A probe answers YES only on sentence structure: >= 3 '$' bytes in
// the window. Printable-count alone false-positives on a live module
// at the WRONG baud (mis-framed bits decode as printable garbage -
// seen live probing 460800 against a 115200 module). A dead line
// gives pure 0x00, which also fails this test, as it should.
static bool probeAt(long baud) {
  gnssSerial.end();
  gnssSerial.begin(baud);
  sendCmd("PSTMGETPAR,1102");
  uint32_t t0 = millis();
  uint32_t dollars = 0;
  bool lineStart = true;
  while (millis() - t0 < 1800) {
    while (gnssSerial.available()) {
      char c = (char)gnssSerial.read();
      if (c == '$') dollars++;
      if (lineStart) { Serial.print(F("[gnss] ")); lineStart = false; }
      Serial.write(c);
      if (c == '\n') lineStart = true;
    }
  }
  return dollars >= 3;
}

void setup() {
  Serial.begin(115200);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 3000) { }
  Serial.println(F("== gnss_baud: firmware step 1 - Teseo-LIV3F to 921600 =="));

  pinMode(GNSS_WAKEUP_PIN, OUTPUT);
  digitalWrite(GNSS_WAKEUP_PIN, HIGH);
  pinMode(GNSS_RESET_PIN, OUTPUT);
  digitalWrite(GNSS_RESET_PIN, LOW);
  delay(100);
  digitalWrite(GNSS_RESET_PIN, HIGH);
  Serial.println(F("[step1] D4 wakeup HIGH, D7 reset pulsed - module booting"));
  delay(1000);

  if (probeAt(TARGET_BAUD)) {
    Serial.println(F("[step1] module already answers at 921600 - no change needed."));
    return;
  }
  const long others[3] = {460800, 115200, 9600};
  for (int i = 0; i < 3; i++) {
    if (probeAt(others[i])) {
      Serial.print(F("[step1] module found at "));
      Serial.print(others[i]);
      Serial.println(F(" - setting 921600..."));
      sendCmd("PSTMSETPAR,1102,0xD");
      echoFor(1200, "[gnss] ");
      sendCmd("PSTMSAVEPAR");
      echoFor(1200, "[gnss] ");
      sendCmd("PSTMSRR");
      delay(500);
      if (probeAt(TARGET_BAUD)) {
        Serial.println(F("[step1] SUCCESS: module now at 921600, persisted."));
      } else {
        Serial.println(F("[step1] WARNING: no answer at 921600 after reboot."));
        monitorBaud = others[i];
        gnssSerial.end();
        gnssSerial.begin(monitorBaud);
      }
      return;
    }
  }
  Serial.println(F("[step1] module answered at NO baud - check wiring/power/reset."));
}

void loop() {
  echoFor(1000, "[gnss] ");
}
