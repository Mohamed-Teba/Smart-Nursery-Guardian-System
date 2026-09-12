#include <LiquidCrystal_I2C.h>
#include <Servo.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);
Servo bedServo;

#define PIR_PIN     2
#define LDR_PIN     A0
#define TEMP_PIN    A1
#define ROOM_LED    3
#define RED         9
#define GREEN       10
#define BLUE        11
#define FAN_PIN     5
#define IN          12
#define GAS_PIN     A2
#define BUZZER_PIN  8
#define SERVO_PIN   6

const int DARKNESS_THRESHOLD = 500;
const int GAS_THRESHOLD      = 400;

// ---- Sensor state ----

int  pirState = LOW;
int  lastPirState = LOW;
int  motionCount = 0;
unsigned long windowStartTime = 0;
const unsigned long WINDOW_DURATION = 8000;
bool isBabyAwake = false;

int  ldrValue = 0;
bool roomDark = false;

float temp = 0.0;
float volt = 0.0;

int  gasValue = 0;
bool gasAlert = false;
bool lastGasState = false;

// ---- Commands from Python / ML ----

bool isCryDetected = false;
bool isTiredBuzzerOn = false;
String cryType = "None";

// ---- Timing ----

unsigned long lastLCDUpdate   = 0;
unsigned long lastServoMove   = 0;
unsigned long lastSensorPrint = 0;
int  servoState = 0;

String serialBuffer = "";

void setup() {
  pinMode(PIR_PIN, INPUT);
  pinMode(LDR_PIN, INPUT);
  pinMode(TEMP_PIN, INPUT);
  pinMode(ROOM_LED, OUTPUT);
  pinMode(RED, OUTPUT);
  pinMode(GREEN, OUTPUT);
  pinMode(BLUE, OUTPUT);
  pinMode(FAN_PIN, OUTPUT);
  pinMode(IN, OUTPUT);
  pinMode(GAS_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  Serial.begin(9600);

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Smart Baby Bed");
  lcd.setCursor(0, 1);
  lcd.print("System Ready...");
  delay(1500);
  lcd.clear();

  bedServo.attach(SERVO_PIN);
  bedServo.write(90);

  Serial.println("READY");
}

// ============================================================
// Receive commands from Laptop (Streamlit + ML)
// ============================================================

void processSerialCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "CRY:END" || cmd == "RESET" || cmd == "CRY_END") {
    isCryDetected   = false;
    isTiredBuzzerOn = false;
    cryType         = "None";

    bedServo.write(90);
    Serial.println("ACK:RESET");
  }
  else if (cmd.startsWith("CRY:")) {
    String reason = cmd.substring(4);
    reason.trim();
    reason.toLowerCase();

    isCryDetected = true;
    isBabyAwake   = true;

    if (reason == "hungry") {
      cryType = "Hungry";
      isTiredBuzzerOn = false;
    } else if (reason == "tired") {
      cryType = "Tired";
      isTiredBuzzerOn = true;
    } else if (reason == "discomfort") {
      cryType = "Discomfort";
      isTiredBuzzerOn = false;
    } else {
      cryType = reason;
      isTiredBuzzerOn = false;
    }

    Serial.print("ACK:CRY:");
    Serial.println(cryType);
  }
  else if (cmd == "GAS_CLEARED") {
    Serial.println("ACK:GAS_CLEARED");
  }
}

void readSerialFromLaptop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length() > 0) {
        processSerialCommand(serialBuffer);
        serialBuffer = "";
      }
    } else {
      serialBuffer += c;
      if (serialBuffer.length() > 64) {
        serialBuffer = "";
      }
    }
  }
}

// ============================================================
// Sensors
// ============================================================

void readSensors() {
  pirState = digitalRead(PIR_PIN);
  ldrValue = analogRead(LDR_PIN);
  roomDark = (ldrValue > DARKNESS_THRESHOLD);

  volt = analogRead(TEMP_PIN);
  temp = (volt * 5.0 / 1024.0) * 100.0;

  gasValue = analogRead(GAS_PIN);
  gasAlert = (gasValue > GAS_THRESHOLD);
}

void updateMotion() {
  unsigned long currentTime = millis();

  if (currentTime - windowStartTime >= WINDOW_DURATION) {
    windowStartTime = currentTime;
    motionCount = 0;
    if (!isCryDetected) {
      isBabyAwake = false;
    }
  }

  if (pirState == HIGH && lastPirState == LOW) {
    motionCount++;
    Serial.print("MOTION:");
    Serial.println(motionCount);

    if (motionCount >= 4) {
      isBabyAwake = true;
      Serial.println("AWAKE");
    }
  }
  lastPirState = pirState;
}


void sendSensorTelemetry() {
  if (millis() - lastSensorPrint < 1000) return;
  lastSensorPrint = millis();

  Serial.print("GAS:");
  Serial.println(gasValue);

  Serial.print("TEMP:");
  Serial.println((int)temp);

  Serial.print("LIGHT:");
  Serial.println(roomDark ? "DARK" : "BRIGHT");
}

// ============================================================
// Actuators
// ============================================================

void handleLighting() {
  if (roomDark && (isBabyAwake || isCryDetected || gasAlert)) {
    digitalWrite(ROOM_LED, HIGH);
  } else {
    digitalWrite(ROOM_LED, LOW);
  }
}

void handleTemp() {
  if (temp < 25.0) {
    digitalWrite(RED, LOW);
    digitalWrite(GREEN, LOW);
    digitalWrite(BLUE, HIGH);
    analogWrite(FAN_PIN, 100);
    digitalWrite(IN, HIGH);
  } else if (temp <= 30.0) {
    digitalWrite(RED, LOW);
    digitalWrite(GREEN, HIGH);
    digitalWrite(BLUE, LOW);
    analogWrite(FAN_PIN, 160);
    digitalWrite(IN, HIGH);
  } else {
    digitalWrite(RED, HIGH);
    digitalWrite(GREEN, LOW);
    digitalWrite(BLUE, LOW);
    analogWrite(FAN_PIN, 255);
    digitalWrite(IN, HIGH);
  }
}

void handleSafetyAlerts() {
  if (gasAlert || isTiredBuzzerOn) {
    digitalWrite(BUZZER_PIN, HIGH);
  } else {
    digitalWrite(BUZZER_PIN, LOW);
  }

  if (gasAlert && !lastGasState) {
    Serial.println("ALERT:GAS_DETECTED");
  }
  lastGasState = gasAlert;
}

void handleServo() {
  if (isBabyAwake || isCryDetected || gasAlert) {
    unsigned long currentTime = millis();
    if (currentTime - lastServoMove >= 600) {
      lastServoMove = currentTime;
      if (servoState == 0) {
        bedServo.write(0);
        servoState = 1;
      } else if (servoState == 1) {
        bedServo.write(90);
        servoState = 2;
      } else {
        bedServo.write(180);
        servoState = 0;
      }
    }
  } else {
    bedServo.write(90);
    servoState = 0;
  }
}

void updateDisplay() {
  if (millis() - lastLCDUpdate < 300) return;
  lastLCDUpdate = millis();

  if (gasAlert) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("!! DANGER !!");
    lcd.setCursor(0, 1);
    lcd.print("GAS DETECTED!");
  } else if (isCryDetected) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Baby Crying!");
    lcd.setCursor(0, 1);
    lcd.print("Reason: ");
    lcd.print(cryType);
  } else {
    lcd.setCursor(0, 0);
    lcd.print("Temp:");
    lcd.print((int)temp);
    lcd.print("C  ");
    lcd.print(roomDark ? "Dark " : "Light");

    lcd.setCursor(0, 1);
    lcd.print("Baby: ");
    lcd.print(isBabyAwake ? "Awake   " : "Sleeping");
  }
}

void loop() {
  readSerialFromLaptop();
  readSensors();
  updateMotion();
  sendSensorTelemetry();
  handleLighting();
  handleTemp();
  handleSafetyAlerts();
  handleServo();
  updateDisplay();
  delay(30);
}