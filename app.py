import streamlit as st
import os
import joblib
import tempfile
import threading
import time
import numpy as np
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="Smart Nursery Guardian System", layout="wide")
st.title("Smart Nursery Guardian System")
st.markdown("---")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

defaults = {
    "status": "calm",
    "temp": 26,
    "light": "Bright",
    "gas": "Safe",
    "is_awake": False,
    "log": [],
    "monitoring": False,
    "auto_mode": False,
    "last_prediction": "-",
    "auto_thread_running": False,
    "serial_port": None,
    "last_telegram_gas": 0.0,
    "last_telegram_cry": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

def add_log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.log.append(f"[{ts}] {msg}")
    if len(st.session_state.log) > 40:
        st.session_state.log = st.session_state.log[-40:]

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _get_telegram_credentials():
    try:
        return st.secrets["Token"], st.secrets["chat_id"]
    except Exception:
        return None, None

async def _send_telegram_bot(token: str, chat_id: str, msg: str):
    from telegram import Bot
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=msg)

def send_telegram(msg: str, force: bool = False):
    """Send alert to caregiver. force=True skips dedup."""
    token, chat_id = _get_telegram_credentials()
    if not token or not chat_id:
        add_log("Telegram skipped: missing Token/chat_id in secrets")
        return False
    try:
        import asyncio
        asyncio.run(_send_telegram_bot(token, chat_id, msg))
        st.toast("Telegram Sent")
        add_log(f"Laptop -> Telegram: {msg}")
        return True
    except Exception as e:
        st.error(f"Telegram Failed: {e}")
        add_log(f"Telegram ERROR: {e}")
        return False

def notify_cry(label: str, confidence: float = 0.0, source: str = "ML", force: bool = False):
    """Telegram + log for cry predictions (dedup same label within session)."""
    key = f"{label}:{source}"
    if not force and st.session_state.last_telegram_cry == key:
        return
    conf_txt = f" ({confidence:.0%})" if confidence else ""
    msg = f"Your Baby is Crying. He is: {label.capitalize()}"
    if send_telegram(msg):
        st.session_state.last_telegram_cry = key

def notify_gas():
    """Telegram for gas (rate-limited to once per 30s)."""
    now = time.time()
    if now - st.session_state.last_telegram_gas < 30:
        return
    if send_telegram("GAS ALERT: Gas/Smoke Detected. Evacuate The Room Now"):
        st.session_state.last_telegram_gas = now


# ---------------------------------------------------------------------------
# Serial helpers (persistent connection while monitoring)
# ---------------------------------------------------------------------------

def open_serial(port: str, baud: int = 9600):
    try:
        import serial

        if not hasattr(serial, "Serial"):
            location = getattr(serial, "__file__", None)
            raise RuntimeError(
                "Invalid serial module loaded"
                f" ({location}). Install pyserial in the same Python environment."
            )

        if st.session_state.serial_port is not None:
            try:
                st.session_state.serial_port.close()
            except Exception:
                pass
            st.session_state.serial_port = None

        ser = serial.Serial(port=port, baudrate=baud, timeout=0.3)
        time.sleep(1.5)  # Arduino Uno/Nano may reset when the port opens.
        st.session_state.serial_port = ser
        add_log(f"Serial OPEN {port} @ {baud}")
        return ser
    except Exception as e:
        add_log(f"Serial open failed: {e}")
        st.session_state.serial_port = None
        return None

def close_serial():
    ser = st.session_state.serial_port
    if ser is not None:
        try:
            ser.close()
        except Exception:
            pass
    st.session_state.serial_port = None
    add_log("Serial CLOSED")

def serial_write(cmd: str):
    """Send a line command to Arduino (CRY:hungry, RESET, ...)."""
    ser = st.session_state.serial_port
    if ser is None or not ser.is_open:
        add_log(f"Serial WRITE skipped (not connected): {cmd}")
        return False
    try:
        line = (cmd.strip() + "\n").encode("utf-8")
        ser.write(line)
        ser.flush()
        add_log(f"Laptop -> Micro: {cmd}")
        return True
    except Exception as e:
        add_log(f"Serial WRITE error: {e}")
        return False

def apply_ml_action(label: str, confidence: float = 0.0, source: str = "ML"):
    """
    After ML prediction:
      1. Update GUI state
      2. Command Arduino actuators
      3. Notify Telegram
    """
    label = str(label).strip().lower()
    st.session_state.status = label
    st.session_state.is_awake = True
    conf = confidence or 0.0
    st.session_state.last_prediction = f"{label} ({conf:.1%}) [{source}]"

    if label in ("hungry", "tired", "discomfort"):
        serial_write(f"CRY:{label}")
        notify_cry(label, conf, source)
    elif label == "gas":
        st.session_state.gas = "DANGER"
        notify_gas()
    add_log(f"ML ACTION applied: {label}")

def reset_system():
    """Calm state + stop actuators on hardware."""
    serial_write("RESET")
    st.session_state.status = "calm"
    st.session_state.is_awake = False
    st.session_state.gas = "Safe"
    st.session_state.temp = 26
    st.session_state.last_telegram_cry = ""
    add_log("System RESET")

# ---------------------------------------------------------------------------
# ML model
# ---------------------------------------------------------------------------

@st.cache_resource
def load_model():
    candidates = [
        Path(r"model\smart-nursery-guardian-model.pkl")
    ]
    for p in candidates:
        if p.exists():
            try:
                art = joblib.load(p)
                required = {"pipeline", "feature_names", "class_names", "model_name"}
                missing = required - set(art.keys())
                if missing:
                    return None, f"Invalid artifact {p}: missing {missing}"
                return art, None
            except Exception as e:
                return None, f"Load failed {p}: {e}"
    return None, "Model not found. Place smart_nursery_guardian.pkl inside model/"

artifact, ml_error = load_model()
ml_ready = artifact is not None
if ml_error:
    st.warning(ml_error)

def predict_feature_row(feature_dict: dict) -> dict:
    import pandas as pd
    feature_names = artifact["feature_names"]
    row = pd.DataFrame([{f: feature_dict.get(f, float("nan")) for f in feature_names}])
    row = row.replace([np.inf, -np.inf], np.nan)
    pipeline = artifact["pipeline"]
    pred = pipeline.predict(row)[0]
    result = {"label": str(pred).lower()}
    if hasattr(pipeline, "predict_proba"):
        proba = pipeline.predict_proba(row)[0]
        result["confidence"] = float(max(proba))
        classes = list(getattr(pipeline, "classes_", []))
        result["probabilities"] = {
            str(c): float(p) for c, p in zip(classes, proba)
        }
    return result

def extract_standard_audio_features(audio_path, sr=22050, duration=5.0):
    """
    Must match Donate-a-Cry feature schema used in training notebook:
    Amplitude_Envelope_Mean, RMS_Mean, ZCR_Mean, STFT_Mean, SC_Mean,
    SBAN_Mean, SCON_Mean, MFCCs13Mean, delMFCCs13, del2MFCCs13, MelSpec,
    MFCCs20, MFCCs1..MFCCs13
    """
    import librosa

    y, _ = librosa.load(audio_path, sr=sr, mono=True, duration=duration)
    if y is None or len(y) == 0:
        raise ValueError("No audio samples")
    target_len = int(sr * duration)
    if len(y) < target_len:
        y = np.pad(y, (0, target_len - len(y)))
    else:
        y = y[:target_len]

    S = np.abs(librosa.stft(y))
    mfcc13 = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc20 = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    delta = librosa.feature.delta(mfcc13)
    delta2 = librosa.feature.delta(mfcc13, order=2)

    feat = {
        "Amplitude_Envelope_Mean": float(np.mean(np.abs(y))),
        "RMS_Mean": float(np.mean(librosa.feature.rms(y=y)[0])),
        "ZCR_Mean": float(np.mean(librosa.feature.zero_crossing_rate(y)[0])),
        "STFT_Mean": float(np.mean(S)),
        "SC_Mean": float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)[0])),
        "SBAN_Mean": float(np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr)[0])),
        "SCON_Mean": float(np.mean(librosa.feature.spectral_contrast(S=S, sr=sr))),
        "MFCCs13Mean": float(np.mean(mfcc13)),
        "delMFCCs13": float(np.mean(delta)),
        "del2MFCCs13": float(np.mean(delta2)),
        "MelSpec": float(np.mean(librosa.feature.melspectrogram(y=y, sr=sr))),
        "MFCCs20": float(np.mean(mfcc20)),
    }
    for i in range(13):
        feat[f"MFCCs{i+1}"] = float(np.mean(mfcc13[i]))
    return feat

def predict_audio_file(audio_path: str) -> dict:
    feat = extract_standard_audio_features(audio_path)
    for f in artifact["feature_names"]:
        if f not in feat:
            feat[f] = float(np.nan)
    return predict_feature_row(feat)

# ---------------------------------------------------------------------------
# Auto mic loop (optional)
# ---------------------------------------------------------------------------

def auto_loop():
    import sounddevice as sd
    import soundfile as sf

    sr = 22050
    duration = 3
    while st.session_state.auto_mode and st.session_state.monitoring:
        try:
            audio = sd.rec(int(duration * sr), samplerate=sr, channels=1, dtype="float32")
            sd.wait()
            y = audio.flatten()
            rms = float(np.sqrt(np.mean(y ** 2)))
            if rms < 0.008:
                time.sleep(0.5)
                continue
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                sf.write(tmp.name, y, sr)
                tmp_path = tmp.name
            try:
                if ml_ready:
                    result = predict_audio_file(tmp_path)
                    label = result["label"]
                    conf = result.get("confidence", 0.0)
                    # session_state updates from thread are best-effort in Streamlit
                    st.session_state.status = label
                    st.session_state.is_awake = True
                    st.session_state.last_prediction = f"{label} ({conf:.1%}) auto"
                    serial_write(f"CRY:{label}")
                    notify_cry(label, conf, "auto")
                    add_log(f"Auto ML PREDICT: {label} rms={rms:.3f}")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        except Exception as e:
            add_log(f"Auto loop error: {e}")
            time.sleep(1)
        time.sleep(1)

# ---------------------------------------------------------------------------
# Serial polling (Arduino -> GUI)
# ---------------------------------------------------------------------------

def poll_serial():
    if not st.session_state.monitoring:
        return
    ser = st.session_state.serial_port
    if ser is None or not getattr(ser, "is_open", False):
        return
    try:
        while ser.in_waiting:
            raw = ser.readline().decode(errors="ignore").strip()
            if not raw:
                continue
            add_log(f"Micro -> Laptop: {raw}")
            upper = raw.upper()

            if upper.startswith("GAS:"):
                try:
                    val = int("".join(filter(str.isdigit, raw.split(":", 1)[-1])))
                    if val > 400:
                        st.session_state.status = "gas"
                        st.session_state.gas = "DANGER"
                        st.session_state.is_awake = True
                        notify_gas()
                    else:
                        if st.session_state.gas == "DANGER" and st.session_state.status == "gas":
                            pass  # keep until RESET
                except Exception:
                    pass
            elif "ALERT:GAS" in upper or "GAS_DETECTED" in upper:
                st.session_state.status = "gas"
                st.session_state.gas = "DANGER"
                st.session_state.is_awake = True
                notify_gas()
            elif upper.startswith("TEMP:"):
                try:
                    v = int("".join(filter(str.isdigit, raw.split(":", 1)[-1])))
                    st.session_state.temp = v
                except Exception:
                    pass
            elif "LIGHT:DARK" in upper or upper.endswith("DARK"):
                st.session_state.light = "Dark"
            elif "LIGHT:BRIGHT" in upper or upper.endswith("BRIGHT"):
                st.session_state.light = "Bright"
            elif upper == "AWAKE" or "BABY IS AWAKE" in upper:
                st.session_state.is_awake = True
                if st.session_state.status == "calm":
                    st.session_state.status = "awake"
            elif upper.startswith("MOTION:"):
                st.session_state.is_awake = True
            elif upper.startswith("ACK:"):
                add_log(f"Hardware ACK: {raw}")
    except Exception as e:
        add_log(f"poll_serial error: {e}")

poll_serial()

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

st.sidebar.title("Control Panel")
selected_port = st.sidebar.text_input("COM Port", value=st.session_state.get("com_port_text", "COM7"))
st.session_state.com_port_text = selected_port

st.session_state.light = st.sidebar.selectbox(
    "Light Sensor (Mock)",
    ["Bright", "Dark"],
    index=0 if st.session_state.light == "Bright" else 1,
)

col_a, col_b = st.sidebar.columns(2)
with col_a:
    if st.button("Start Monitoring", use_container_width=True):
        ser = open_serial(selected_port.strip())
        if ser is not None:
            st.session_state.monitoring = True
            add_log(f"Monitoring START on {selected_port.strip()}")
            st.toast(f"Connected to {selected_port.strip()}")
        else:
            st.session_state.monitoring = False
            add_log(f"Monitoring NOT started on {selected_port.strip()}")
        st.rerun()
with col_b:
    if st.button("Stop Monitoring", use_container_width=True):
        st.session_state.monitoring = False
        st.session_state.auto_mode = False
        close_serial()
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.write("Mock Tests (simulate ML + hardware)")
if st.sidebar.button("Try Hungry"):
    apply_ml_action("hungry", 0.95, "mock")
    st.rerun()
if st.sidebar.button("Try Tired"):
    apply_ml_action("tired", 0.90, "mock")
    st.rerun()
if st.sidebar.button("Try Discomfort"):
    apply_ml_action("discomfort", 0.88, "mock")
    st.rerun()
if st.sidebar.button("Try Gas Alert"):
    st.session_state.status = "gas"
    st.session_state.gas = "DANGER"
    st.session_state.is_awake = True
    st.session_state.temp = 32
    add_log("Micro -> Laptop: GAS_ALERT [MOCK]")
    notify_gas()
    st.rerun()
if st.sidebar.button("Reset"):
    reset_system()
    st.rerun()

# Manual audio upload
st.sidebar.markdown("---")
st.sidebar.write("Voice Input - Manual")
uploaded = st.sidebar.file_uploader(
    "Upload cry audio", type=["wav", "mp3", "m4a", "flac", "ogg"]
)
if uploaded is not None:
    if not ml_ready:
        st.sidebar.error("Model not loaded")
    else:
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getbuffer())
            tmp_path = tmp.name
        st.sidebar.info(f"Uploaded: {uploaded.name}")
        if st.sidebar.button("Predict Uploaded File"):
            try:
                result = predict_audio_file(tmp_path)
                label = result["label"]
                conf = result.get("confidence", 0.0)
                apply_ml_action(label, conf, f"upload:{uploaded.name}")
                st.sidebar.success(f"Predicted: {label} {conf:.1%}")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Predict failed: {e}")
                add_log(f"Predict failed: {e}")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

is_crying = st.session_state.status in ["hungry", "tired", "discomfort"]
lamp_on = (
    st.session_state.light == "Dark"
    and (st.session_state.is_awake or is_crying or st.session_state.status == "gas")
)
servo_on = st.session_state.status in ["hungry", "tired", "discomfort", "gas"] or is_crying
buzzer_on = st.session_state.status in ["tired", "gas"]

col1, col2, col3, col4 = st.columns(4)
with col1:
    t = st.session_state.temp
    if t < 25:
        st.metric("Temp / Fan", f"{t}°C", "Blue - fan Low", delta_color="off")
    elif t <= 30:
        st.metric("Temp / Fan", f"{t}°C", "Green - fan Half", delta_color="off")
    else:
        st.metric("Temp / Fan", f"{t}°C", "Red - fan Full", delta_color="inverse")
with col2:
    st.metric("Motion", "Awake" if st.session_state.is_awake else "Calm")
with col3:
    st.metric(
        "Gas level",
        st.session_state.gas,
        "ALERT" if st.session_state.gas == "DANGER" else "Safe",
    )
with col4:
    st.metric(
        "Room Lamp",
        "ON" if lamp_on else "OFF",
        f"Light: {st.session_state.light}",
    )

st.caption(
    f"SERVO: {'Rocking' if servo_on else 'Stopped'} | "
    f"BUZZER: {'ON' if buzzer_on else 'OFF'} | "
    f"Light Sensor: {st.session_state.light} | "
    f"Serial: {'Connected' if st.session_state.serial_port else 'Off'}"
)

st.markdown("---")
with st.container():
    status = st.session_state.status
    if status == "gas":
        st.error("SAFETY ALERT - GAS DETECTED")
        st.error("Buzzer Continuous - Evacuate Room! | Telegram sent to caregiver")
        st.markdown(
            "<h1 style='text-align:center; color:#ff4b4b; font-size:48px;'>SAFETY ALERT</h1>",
            unsafe_allow_html=True,
        )
        if st.button("Reset Alert", type="primary"):
            reset_system()
            st.rerun()
    elif status == "hungry":
        st.info("Baby is Hungry — Feeding Needed")
    elif status == "tired":
        st.warning("Baby is Tired — URGENT")
    elif status == "discomfort":
        st.error("Baby is Discomfort — Check Diaper / Position")
    elif status == "awake":
        st.success("Baby is Awake")
    else:
        st.success("Baby is Calm")

st.markdown("---")
with st.expander("Serial Log", expanded=True):
    if st.session_state.log:
        st.code("\n".join(st.session_state.log[-15:]), language="text")
    else:
        st.code("No messages yet — Start Monitoring or use Mock Tests", language="text")
    if st.button("Clear Log"):
        st.session_state.log = []
        st.rerun()

with st.expander("ML Info", expanded=False):
    if ml_ready:
        st.write(f"**Model:** {artifact['model_name']}")
        st.write(f"**Classes:** {artifact['class_names']}")
        st.write(f"**Features:** {len(artifact['feature_names'])}")
        st.write(f"**Last prediction:** {st.session_state.last_prediction}")
        st.write("Feature list:", artifact["feature_names"])
    else:
        st.error(str(ml_error))

# Soft refresh while monitoring so serial keeps polling
if st.session_state.monitoring:
    time.sleep(1.2)
    st.rerun()