# 🍼 Smart Nursery Guardian System

<p align="center">
  <img src="assets/logo.png" alt="Smart Nursery Guardian Logo" width="180"/>
</p>

<p align="center">
  <strong>An intelligent IoT + Machine Learning system that monitors a baby’s environment, detects cry reasons, and alerts caregivers in real time.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Arduino-00979D?style=for-the-badge&logo=arduino&logoColor=white"/>
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white"/>
  <img src="https://img.shields.io/badge/scikit--learn-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white"/>
  <img src="https://img.shields.io/badge/Telegram-26A5E4?style=for-the-badge&logo=telegram&logoColor=white"/>
  <img src="https://img.shields.io/badge/Machine%20Learning-Cry%20Classification-success?style=for-the-badge"/>
</p>

---

## 👥 Team 6 Members

| Name                    | ID     |
|-------------------------|--------|
| Mohamed Ibrahim         | 7131E  |
| Pilopateer Hani         | 7129E  |
| Tharaa Mohamed          | 7005E  |

---

## 📖 Project Overview

**Smart Nursery Guardian** is a complete end-to-end smart baby monitoring system that combines:

- **Hardware sensors** (temperature, gas/smoke, light, motion)
- **Actuators** (fan, RGB LED, room lamp, servo rocker, buzzer)
- **Machine Learning** cry classification (Hungry / Tired / Discomfort)
- **Real-time dashboard** (Streamlit)
- **Instant caregiver alerts** via Telegram Bot

The system continuously monitors the nursery environment. When the baby cries, an audio clip is analyzed by a trained ML model. The predicted reason is sent to the Arduino, which activates the appropriate actuators, updates the LCD, and triggers a Telegram notification to the parents.

---

## ✨ Key Features

### 🔊 Cry Classification (ML)
- Detects three cry types: **Hungry**, **Tired**, **Discomfort**
- Feature extraction using Librosa (MFCC, spectral features, RMS, ZCR, etc.)
- Trained on the Donate-a-Cry corpus features dataset
- Real-time prediction from uploaded audio or live microphone

### 🌡️ Environmental Monitoring
- Temperature sensing + automatic fan speed control (Low / Half / Full)
- Gas / Smoke detection with emergency alert
- Light (LDR) sensing for automatic night lamp
- PIR motion detection to determine if baby is awake or sleeping

### 🤖 Smart Actuators
- **Servo motor** rocks the bed when baby is crying or awake
- **Buzzer** activates on Tired cry or Gas alert
- **RGB LED** indicates temperature status
- **Room lamp** turns on automatically in dark conditions when baby is active

### 📱 Caregiver Notifications
- Telegram Bot (`@SMART_NURSERY_GUARDIAN_bot`) sends instant alerts:
  - Cry reason + confidence
  - Gas / Smoke emergency

### 🖥️ Live Dashboard
- Beautiful dark-themed Streamlit interface
- Real-time metrics (Temp, Motion, Gas, Lamp)
- Serial log, ML info, mock testing buttons
- Manual audio upload for prediction

---

## 🖼️ System Screenshots

### Dashboard – Calm State
![Dashboard Calm](assets/Temp%20Alret.jpg)

### Dashboard – Gas Alert
![Gas Alert Dashboard](assets/Gas%20Alret.jpg)

### Hardware LCD Display
![Hardware LCD](assets/Hardware%20Result.jpg)

### Telegram Bot
![Telegram Bot](assets/Telegram%201.jpg)

---

## 🔌 Hardware Design

### Full Circuit Diagram
![Full Circuit](assets/full-circuit.jpg)

### Custom PCB (3D View)
![PCB 3D](assets/PCB%203D.png)

> Designed in **Altium Designer** – dated 5-9-2026 – Team 6

### Main Components

| Component              | Purpose                              | Pin / Connection      |
|------------------------|--------------------------------------|-----------------------|
| Arduino Uno            | Main controller                      | -                     |
| LCD 16x2 (I2C)         | Status display                       | SDA/SCL               |
| PIR Motion Sensor      | Detect baby movement                 | Digital 2             |
| LDR                    | Light intensity                      | Analog A0             |
| Temperature Sensor     | Ambient temperature                  | Analog A1             |
| MQ Gas Sensor          | Smoke / Gas detection                | Analog A2             |
| Servo Motor            | Rock the baby bed                    | Digital 6             |
| Buzzer                 | Audio alerts                         | Digital 8             |
| RGB LED                | Temperature status indication        | 9, 10, 11             |
| DC Fan + L293D         | Cooling system                       | PWM 5 + Direction 12  |
| Room LED               | Night lamp                           | Digital 3             |
| 9V Battery             | External power for motor driver      | -                     |

---

## 🧠 Machine Learning Pipeline

The model was trained on the **Donate-a-Cry Corpus Features Dataset**.

**Classes:**
- `hungry`
- `tired`
- `discomfort`

**Pipeline steps:**
1. Robust imputation + scaling
2. Feature selection (`SelectKBest`)
3. Class balancing (SMOTE / RandomOverSampler)
4. Model comparison (Logistic Regression, SVM, Random Forest, Extra Trees, HistGradientBoosting, KNN)
5. Hyperparameter tuning with `RandomizedSearchCV`
6. Final best model saved as `smart-nursery-guardian-model.pkl`

**Feature set (must match exactly at inference):**
- Amplitude_Envelope_Mean, RMS_Mean, ZCR_Mean, STFT_Mean
- SC_Mean, SBAN_Mean, SCON_Mean
- MFCCs13Mean, delMFCCs13, del2MFCCs13, MelSpec, MFCCs20
- MFCCs1 … MFCCs13

> See `machine-learning-pipeline.ipynb` for the complete training notebook.

---

## 🛠️ Software Architecture

```
┌─────────────────────┐       Serial (9600)      ┌─────────────────────┐
│  Streamlit Dashboard│ ◄──────────────────────► │   Arduino Firmware  │
│  (app.py)           │                          │   (main.ino)        │
│                     │                          │                     │
│  • ML Inference     │                          │  • Sensors reading  │
│  • Telegram Alerts  │                          │  • Actuator control │
│  • Live Metrics     │                          │  • LCD updates      │
│  • Serial Bridge    │                          │  • Command ACK      │
└─────────────────────┘                          └─────────────────────┘
```

**Communication Protocol**

| Direction       | Message Example              | Meaning                          |
|-----------------|------------------------------|----------------------------------|
| Laptop → Micro  | `CRY:hungry`                 | Activate hungry cry response     |
| Laptop → Micro  | `CRY:tired`                  | Activate tired cry + buzzer      |
| Laptop → Micro  | `CRY:discomfort`             | Activate discomfort response     |
| Laptop → Micro  | `RESET`                      | Return to calm state             |
| Micro → Laptop  | `GAS:450`                    | Gas sensor value                 |
| Micro → Laptop  | `TEMP:28`                    | Temperature reading              |
| Micro → Laptop  | `LIGHT:DARK` / `BRIGHT`      | Light condition                  |
| Micro → Laptop  | `AWAKE` / `MOTION:3`         | Motion / awake status            |
| Micro → Laptop  | `ALERT:GAS_DETECTED`         | Emergency gas alert              |
| Micro → Laptop  | `ACK:CRY:Hungry`             | Command acknowledgment           |

---

## 🚀 Getting Started

### 1. Hardware Setup
1. Wire the circuit according to the diagram above (or use the custom PCB).
2. Upload `main.ino` to the Arduino Uno using the Arduino IDE.
3. Connect the Arduino to the laptop via USB.

### 2. Software Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/smart-nursery-guardian.git
cd smart-nursery-guardian

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**Required packages** (suggested `requirements.txt`):
```
streamlit
pyserial
joblib
numpy
pandas
scikit-learn
imbalanced-learn
librosa
sounddevice
soundfile
python-telegram-bot
```

### 3. Model Placement
Place the trained model file at:
```
model/smart-nursery-guardian-model.pkl
```

### 4. Telegram Configuration
Create a `.streamlit/secrets.toml` file:
```toml
Token = "YOUR_TELEGRAM_BOT_TOKEN"
chat_id = "YOUR_CHAT_ID"
```

### 5. Run the Dashboard
```bash
streamlit run app.py
```

---

## 🎮 How to Use

1. Open the Streamlit dashboard.
2. Enter the correct **COM Port** (e.g. `COM7` on Windows or `/dev/ttyUSB0` on Linux).
3. Click **Start Monitoring**.
4. Use the **Mock Tests** buttons to simulate cry types and gas alerts.
5. Upload a real cry audio file (WAV/MP3) and click **Predict Uploaded File**.
6. Watch the dashboard, LCD, actuators, and Telegram notifications update in real time.
7. Click **Reset** to return the system to calm state.

---

## 📁 Repository Structure

```
smart-nursery-guardian/
├── app.py                          # Streamlit dashboard + serial + ML + Telegram
├── main.ino                        # Arduino firmware
├── machine-learning-pipeline.ipynb # Full ML training notebook
├── model/
│   └── smart-nursery-guardian-model.pkl
├── assets/
│   ├── full-circuit.jpg
│   ├── PCB 3D.png
│   ├── Hardware Result.jpg
│   ├── Gas Alret.jpg
│   ├── Temp Alret.jpg
│   ├── Telegram 1.jpg
│   └── logo.png                    # (add your logo here)
├── requirements.txt
└── README.md
```

---

## 🔮 Future Improvements

- Continuous live microphone monitoring with background thread
- Edge deployment of the ML model on a Raspberry Pi / ESP32
- Mobile companion app
- Multi-baby support
- Historical data logging & analytics dashboard
- Better noise-robust cry detection

---

## 📄 License

This project was developed as an academic graduation / course project by **Team 6**.  
Feel free to use and modify it for educational purposes.

---

<p align="center">
  <strong>Made with ❤️ by Team 6 – Smart Nursery Guardian</strong><br>
  Protecting little ones with technology.
</p>
