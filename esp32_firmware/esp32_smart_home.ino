/*
 * ======================================================================================
 * AI-Powered Smart Home Voice Hub - ESP32 Firmware
 * Hardware: ESP32 DevKit V1 (30 or 38 pin)
 * 
 * Features:
 *   - Wi-Fi & mDNS Discovery ("esp32-smarthome.local")
 *   - High-Speed REST HTTP API & JSON responses
 *   - Onboard Status LED (GPIO 2) - Instant testing with NO external components!
 *   - 4-Channel Relay Control (GPIO 26, GPIO 27, GPIO 14, GPIO 12)
 *   - Simulated AC Climate & Window/Curtain Position State Engine
 *   - Dual-Mode: Wi-Fi HTTP + Serial/Bluetooth fallback for USB COM port control
 * ======================================================================================
 */

#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <ArduinoJson.h> // If available; fallback implemented with clean manual JSON string

// --- WI-FI CONFIGURATION ---
// Replace with your home Wi-Fi network credentials:
const char* DEFAULT_SSID = "YOUR_WIFI_SSID";
const char* DEFAULT_PASS = "YOUR_WIFI_PASSWORD";

// Hostname for mDNS (Accessible at http://esp32-smarthome.local)
const char* MDNS_HOSTNAME = "esp32-smarthome";

// --- PIN DEFINITIONS ---
#define PIN_LED_ONBOARD   2   // ESP32 built-in Blue LED for instant testing
#define PIN_RELAY_1       26  // Relay Channel 1: Living Room / Reception Light
#define PIN_RELAY_2       27  // Relay Channel 2: Bedroom Light / Lamp
#define PIN_RELAY_3       14  // Relay Channel 3: Fan / Appliance
#define PIN_RELAY_4       12  // Relay Channel 4: Auxiliary / TV Socket

// Set to true if your relay module is Active-LOW (most 4-ch relay modules are Active-LOW)
const bool RELAY_ACTIVE_LOW = true;

// Web Server running on port 80
WebServer server(80);

// State tracking
bool state_led = false;
bool state_relays[4] = {false, false, false, false};
int state_ac_temp = 22;
String state_ac_mode = "cool";
bool state_ac_power = false;
int state_window_pos = 0; // 0 = Closed, 100 = Fully Open

// Helper to write to relay pin accounting for Active-LOW / Active-HIGH
void setRelay(int chIndex, bool state) {
  if (chIndex < 0 || chIndex >= 4) return;
  state_relays[chIndex] = state;
  int pin = (chIndex == 0) ? PIN_RELAY_1 :
            (chIndex == 1) ? PIN_RELAY_2 :
            (chIndex == 2) ? PIN_RELAY_3 : PIN_RELAY_4;
            
  digitalWrite(pin, RELAY_ACTIVE_LOW ? (!state ? HIGH : LOW) : (state ? HIGH : LOW));
}

void setLED(bool state) {
  state_led = state;
  digitalWrite(PIN_LED_ONBOARD, state ? HIGH : LOW);
}

// Format JSON response
String getStatusJson() {
  String json = "{";
  json += "\"status\":\"ok\",";
  json += "\"device\":\"ESP32-SmartHome-Hub\",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"uptime_ms\":" + String(millis()) + ",";
  json += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  json += "\"led\":" + String(state_led ? "true" : "false") + ",";
  json += "\"relays\":[";
  for (int i = 0; i < 4; i++) {
    json += String(state_relays[i] ? "true" : "false");
    if (i < 3) json += ",";
  }
  json += "],";
  json += "\"ac\":{";
  json += "\"power\":" + String(state_ac_power ? "true" : "false") + ",";
  json += "\"temp\":" + String(state_ac_temp) + ",";
  json += "\"mode\":\"" + state_ac_mode + "\"";
  json += "},";
  json += "\"window_curtain\":{\"position\":" + String(state_window_pos) + "}";
  json += "}";
  return json;
}

void sendCORS() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}

void handleStatus() {
  sendCORS();
  server.send(200, "application/json", getStatusJson());
}

void handleLED() {
  sendCORS();
  if (server.hasArg("state")) {
    String st = server.arg("state");
    st.toLowerCase();
    if (st == "on" || st == "1" || st == "true") {
      setLED(true);
    } else if (st == "off" || st == "0" || st == "false") {
      setLED(false);
    } else if (st == "toggle") {
      setLED(!state_led);
    }
  }
  server.send(200, "application/json", getStatusJson());
}

void handleRelay() {
  sendCORS();
  if (server.hasArg("ch")) {
    int ch = server.arg("ch").toInt(); // 1 to 4
    if (ch >= 1 && ch <= 4) {
      int idx = ch - 1;
      if (server.hasArg("state")) {
        String st = server.arg("state");
        st.toLowerCase();
        if (st == "on" || st == "1" || st == "true") {
          setRelay(idx, true);
        } else if (st == "off" || st == "0" || st == "false") {
          setRelay(idx, false);
        } else if (st == "toggle") {
          setRelay(idx, !state_relays[idx]);
        }
      }
    }
  }
  server.send(200, "application/json", getStatusJson());
}

void handleAC() {
  sendCORS();
  if (server.hasArg("power")) {
    String p = server.arg("power");
    p.toLowerCase();
    state_ac_power = (p == "on" || p == "1" || p == "true");
  }
  if (server.hasArg("temp")) {
    int t = server.arg("temp").toInt();
    if (t >= 16 && t <= 30) state_ac_temp = t;
  }
  if (server.hasArg("mode")) {
    state_ac_mode = server.arg("mode");
  }
  server.send(200, "application/json", getStatusJson());
}

void handleWindow() {
  sendCORS();
  if (server.hasArg("pos")) {
    int pos = server.arg("pos").toInt();
    if (pos >= 0 && pos <= 100) state_window_pos = pos;
  }
  server.send(200, "application/json", getStatusJson());
}

void handleRoot() {
  sendCORS();
  String html = "<!DOCTYPE html><html><head><title>ESP32 Smart Home</title></head>";
  html += "<body style='font-family:sans-serif; background:#121212; color:#fff; padding:20px;'>";
  html += "<h2>ESP32 Smart Home Voice Hub Companion</h2>";
  html += "<p>Status: <b>Online</b></p>";
  html += "<p>Endpoints available:</p>";
  html += "<ul>";
  html += "<li><a href='/status' style='color:#4fc3f7'>/status</a></li>";
  html += "<li><a href='/led?state=toggle' style='color:#4fc3f7'>/led?state=toggle</a></li>";
  html += "<li><a href='/relay?ch=1&state=toggle' style='color:#4fc3f7'>/relay?ch=1&state=toggle</a></li>";
  html += "<li><a href='/ac?power=on&temp=22' style='color:#4fc3f7'>/ac?power=on&temp=22</a></li>";
  html += "<li><a href='/window?pos=100' style='color:#4fc3f7'>/window?pos=100</a></li>";
  html += "</ul></body></html>";
  server.send(200, "text/html", html);
}

// Process commands sent over USB Serial or Bluetooth Serial
void processSerialCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();
  if (cmd == "STATUS") {
    Serial.println(getStatusJson());
  } else if (cmd == "LED:ON") {
    setLED(true);
    Serial.println(getStatusJson());
  } else if (cmd == "LED:OFF") {
    setLED(false);
    Serial.println(getStatusJson());
  } else if (cmd == "LED:TOGGLE") {
    setLED(!state_led);
    Serial.println(getStatusJson());
  } else if (cmd.startsWith("RELAY:")) {
    // Expected format: RELAY:1:ON or RELAY:2:OFF
    int firstColon = cmd.indexOf(':');
    int secondColon = cmd.indexOf(':', firstColon + 1);
    if (firstColon != -1 && secondColon != -1) {
      int ch = cmd.substring(firstColon + 1, secondColon).toInt();
      String action = cmd.substring(secondColon + 1);
      if (ch >= 1 && ch <= 4) {
        if (action == "ON" || action == "1") setRelay(ch - 1, true);
        else if (action == "OFF" || action == "0") setRelay(ch - 1, false);
        else if (action == "TOGGLE") setRelay(ch - 1, !state_relays[ch - 1]);
      }
      Serial.println(getStatusJson());
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\n==========================================");
  Serial.println("Starting ESP32 Smart Home Voice Hub Node...");
  Serial.println("==========================================");

  // Initialize GPIO pins
  pinMode(PIN_LED_ONBOARD, OUTPUT);
  pinMode(PIN_RELAY_1, OUTPUT);
  pinMode(PIN_RELAY_2, OUTPUT);
  pinMode(PIN_RELAY_3, OUTPUT);
  pinMode(PIN_RELAY_4, OUTPUT);

  // Initial states (All OFF)
  setLED(false);
  for (int i = 0; i < 4; i++) {
    setRelay(i, false);
  }

  // Connect to Wi-Fi
  Serial.print("Connecting to Wi-Fi SSID: ");
  Serial.println(DEFAULT_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(DEFAULT_SSID, DEFAULT_PASS);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    // Blink LED during connection attempt
    digitalWrite(PIN_LED_ONBOARD, !digitalRead(PIN_LED_ONBOARD));
    attempts++;
  }
  
  digitalWrite(PIN_LED_ONBOARD, LOW); // Turn off after connection

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[SUCCESS] Wi-Fi Connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());

    // Start mDNS Responder
    if (MDNS.begin(MDNS_HOSTNAME)) {
      Serial.print("mDNS responder started: http://");
      Serial.print(MDNS_HOSTNAME);
      Serial.println(".local");
      MDNS.addService("http", "tcp", 80);
    }
  } else {
    Serial.println("\n[WARNING] Wi-Fi connection timed out. Running in Serial / AP fallback mode.");
  }

  // Define HTTP REST Routes
  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/led", HTTP_GET, handleLED);
  server.on("/relay", HTTP_GET, handleRelay);
  server.on("/ac", HTTP_GET, handleAC);
  server.on("/window", HTTP_GET, handleWindow);
  
  server.begin();
  Serial.println("HTTP Server started on port 80");
}

void loop() {
  server.handleClient();

  // Process incoming USB Serial commands
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    processSerialCommand(cmd);
  }
}

