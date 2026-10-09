// Base para ESP32 clásico (Dev Module). Ajustar pines al modelo real.
// 3 LEDs con resistencias: verde GPIO16, ámbar GPIO17, rojo GPIO18.
// Recibe H,<nivel>,<secuencia> por Serial a 115200 baudios.
// No lee RAM/disco del PC: vigila el latido y muestra el estado recibido.
// Hardware no validado en el entorno de desarrollo de este prototipo.
#include <Arduino.h>

constexpr int GREEN_PIN = 16;
constexpr int AMBER_PIN = 17;
constexpr int RED_PIN = 18;
constexpr unsigned long TIMEOUT_MS = 15000;
char buffer[80];
size_t used = 0;
unsigned long lastHeartbeat = 0;
bool receivedHeartbeat = false;
unsigned int level = 3;

void showLights(bool green, bool amber, bool red) {
  digitalWrite(GREEN_PIN, green ? HIGH : LOW);
  digitalWrite(AMBER_PIN, amber ? HIGH : LOW);
  digitalWrite(RED_PIN, red ? HIGH : LOW);
}

void setup() {
  Serial.begin(115200);
  pinMode(GREEN_PIN, OUTPUT);
  pinMode(AMBER_PIN, OUTPUT);
  pinMode(RED_PIN, OUTPUT);
}

void loop() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n') {
      buffer[used] = '\0';
      unsigned int incomingLevel;
      unsigned long sequence;
      if (sscanf(buffer, "H,%u,%lu", &incomingLevel, &sequence) == 2 && incomingLevel <= 3) {
        level = incomingLevel;
        lastHeartbeat = millis();
        receivedHeartbeat = true;
      }
      used = 0;
    } else if (ch != '\r') {
      if (used < sizeof(buffer) - 1) buffer[used++] = ch;
      else used = 0;
    }
  }
  bool stale = receivedHeartbeat && (millis() - lastHeartbeat > TIMEOUT_MS);
  if (stale) showLights(false, false, (millis() / 300) % 2);
  else if (!receivedHeartbeat || level == 3) showLights(false, (millis() / 700) % 2, false);
  else showLights(level == 0, level == 1, level == 2);
  delay(10);
}
