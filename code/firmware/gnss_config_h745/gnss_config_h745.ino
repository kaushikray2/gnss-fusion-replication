// gnss_config_h745.ino - rig #2 firmware step 2: enable the raw
// $PSTMTG/$PSTMTS sentences on the Teseo-LIV3F (CDB-ID 201 list
// mask, OR-in bits 8/9 = 0x300), persist with $PSTMSAVEPAR, and
// verify by listening. Written for rig #2's module, which reached
// 921600 via gnss_baud_h745 but whose logger boot-time SETPAR was
// sent while the module was still booting and got dropped - this
// sketch waits a full 4 s after the reset pulse before sending.
// SETPAR SYNTAX (learned the hard way, 2026-11-07): the format is
// $PSTMSETPAR,<id>,0x<value>,<mode> - hex value SECOND, mode LAST,
// exactly as the verified logger sends it (the module echoes it
// back verbatim). The first version of this sketch sent
// ,1201,1,300 (mode/value swapped): the module accepted it and
// set the CDB-201 list mask to 0x1, silencing everything except
// $GNGNS. Recovery below ORs the full factory mask 0x00980056
// plus the TG/TS bits 0x300 back in (0x00980356), saves, and
// reboots the module so the verification sees the applied list.
// D4 is held LOW throughout (the module streams regardless, and
// LOW keeps the stacked LSM6DSO in I2C mode). Nucleo-H745ZI-Q:
// console = explicit USART3 (PD8/PD9); drag-drop flashing.
#include <Arduino.h>

HardwareSerial Console(PD_9, PD_8); // ST-LINK VCP (USART3)
#define Serial Console
HardwareSerial gnssSerial(PB_7, PB_6); // RX, TX (USART1, D0/D1)

static const uint32_t GNSS_RESET_PIN = pinNametoDigitalPin(PG_12);  // D7
static const uint32_t GNSS_WAKEUP_PIN = pinNametoDigitalPin(PE_14); // D4

static uint8_t nmeaChecksum(const char *s) {
  uint8_t c = 0;
  while (*s) { c ^= (uint8_t)*s; s++; }
  return c;
}

static void sendCmd(const char *body) {
  char line[96];
  snprintf(line, sizeof(line), "$%s*%02X\r\n", body, nmeaChecksum(body));
  gnssSerial.print(line);
  Serial.print("[cfg] sent: ");
  Serial.print(line);
}

static void drainPrint(uint32_t ms, uint32_t &tg, uint32_t &ts) {
  uint32_t start = millis();
  String cur;
  while (millis() - start < ms) {
    while (gnssSerial.available()) {
      char ch = (char)gnssSerial.read();
      if (ch == '\n') {
        if (cur.indexOf("SETPAROK") >= 0 || cur.indexOf("SAVEPAROK") >= 0)
          Serial.println(cur);
        if (cur.startsWith("$PSTMTG")) tg++;
        if (cur.startsWith("$PSTMTS")) ts++;
        cur = "";
      } else if (ch != '\r') {
        cur += ch;
      }
    }
  }
}

void setup() {
  Serial.begin(115200);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 3000) {}
  Serial.println("== gnss_config_h745: TG/TS mask for rig #2 ==");
  pinMode(GNSS_WAKEUP_PIN, OUTPUT);
  digitalWrite(GNSS_WAKEUP_PIN, LOW);
  pinMode(GNSS_RESET_PIN, OUTPUT);
  digitalWrite(GNSS_RESET_PIN, HIGH);
  delay(50);
  digitalWrite(GNSS_RESET_PIN, LOW);
  delay(100);
  digitalWrite(GNSS_RESET_PIN, HIGH);
  gnssSerial.begin(921600);
  Serial.println("[cfg] module booting - waiting 4 s before SETPAR");
  delay(4000);
  uint32_t tg = 0, ts = 0;
  sendCmd("PSTMSETPAR,1201,0x00980356,1"); // factory list | TG/TS, OR mode
  drainPrint(2500, tg, ts);
  sendCmd("PSTMSAVEPAR");
  drainPrint(2500, tg, ts);
  sendCmd("PSTMSRR"); // reboot: the saved list applies from this boot
  Serial.println("[cfg] module rebooting - listening 12 s for TG/TS...");
  delay(500);
  drainPrint(12000, tg, ts);
  Serial.print("[cfg] TG lines: ");
  Serial.print(tg);
  Serial.print(" | TS lines: ");
  Serial.println(ts);
  Serial.println(tg > 0 && ts > 0 ? "[cfg] RESULT: TG/TS FLOWING"
                                  : "[cfg] RESULT: TG/TS STILL ABSENT");
}

void loop() {}
