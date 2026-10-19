# The following program is provided by DevMiser - https://github.com/DevMiser

import base64
import collections
import datetime
import hashlib
import inspect
import json
import math
import numpy as np
import openai as openai_lib
import os
import pyaudio
import queue
import re
import shutil
import sounddevice  # noqa: F401  # this import suppresses abberant ALSA lib messages
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import warnings

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from websocket import create_connection, WebSocketConnectionClosedException

import onnxruntime as ort

OrtInferenceSession = ort.InferenceSession

def quiet_inference_session(path_or_bytes, sess_options=None, *args, **kwargs):
    try:
        if sess_options is None:
            sess_options = ort.SessionOptions()
            sess_options.intra_op_num_threads = 1
            sess_options.inter_op_num_threads = 1
        sess_options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    except Exception as e:
        print(f"onnxruntime: could not apply single-thread settings ({e})")
    return OrtInferenceSession(path_or_bytes, sess_options, *args, **kwargs)

ort.InferenceSession = quiet_inference_session

import openwakeword 
from openwakeword.model import Model as OWWModel 

# openwakeword asks onnxruntime for CUDA first. The Pi has no NVIDIA GPU, so
# onnxruntime warns and uses the CPU. The warning will be supressed.
warnings.filterwarnings(
    "ignore",
    message=r"Specified provider 'CUDAExecutionProvider' is not in available provider names",
    category=UserWarning,
)

import RPi.GPIO as GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
led1_pin=18
GPIO.setup(led1_pin, GPIO.OUT)
led1_pwm = GPIO.PWM(led1_pin, 100)   # 100 Hz carrier frequency
led1_pwm.start(0)                     # start at 0% duty cycle (off)

# --- LED Control ---

LED_OFF   = 0
LED_ON    = 1
LED_PULSE = 2
LED_SETUP = 3   # Wi-Fi setup mode: a short blink every two seconds

led_state = LED_OFF
led_lock  = threading.Lock()
led_changed = threading.Event()   # set whenever led_state changes

def led_controller():
    # Off and on are written once and then the thread sleeps until the state
    # changes; only the pulse needs the 50 Hz animation loop.
    step = math.pi / 2          # start PULSE from full brightness for smooth transition
    applied = None
    while True:
        with led_lock:
            state = led_state
            led_changed.clear()
        if state == LED_PULSE:
            duty = (math.sin(step) + 1) / 2 * 100
            led1_pwm.ChangeDutyCycle(duty)
            step += 0.05        # ~2.5-second full cycle at 50 Hz
            applied = LED_PULSE
            led_changed.wait(0.02)
        elif state == LED_SETUP:
            led1_pwm.ChangeDutyCycle(100)
            applied = LED_SETUP
            step = math.pi / 2
            if led_changed.wait(0.15):
                continue
            led1_pwm.ChangeDutyCycle(0)
            led_changed.wait(1.85)
        else:
            if state != applied:
                led1_pwm.ChangeDutyCycle(100 if state == LED_ON else 0)
                applied = state
            step = math.pi / 2  # reset so next PULSE starts at 100%
            led_changed.wait()

threading.Thread(target=led_controller, daemon=True).start()

def _set_led_state(state):
    global led_state
    with led_lock:
        led_state = state
        led_changed.set()

def set_led_off():
    _set_led_state(LED_OFF)

def set_led_on():
    _set_led_state(LED_ON)

def set_led_pulse():
    _set_led_state(LED_PULSE)

def set_led_setup():
    _set_led_state(LED_SETUP)

# --- DaVinci's Personality ---

DAVINCI_BASE = ("""
    # Role & Identity
    - Your name is DaVinci. You do not have a namesake.
    - You are a helpful assistant.

    # Demeanor
    - Be welcoming, friendly, curious, and respectful.
    - Be concise and efficient.
    - Do not be syncophatic, condescending or sarcastic.

    # Tone and Voice Style
    - Use a tone and voice style that is authentic and polite.
    - Do not use a tone or voice style that is pompous or preachy.

    # Objectivity
    - Be honest, factual, intelligent, clear and concise.
    - Do not be biased, repetitive, or ambiguous.

    # Enthusiasm Level
    - Keep your enthusiam level calm and measured unless specifically requested otherwise.
    - Avoid rambling and excessive detail.

    # Filler Words
    - Occasionally use filler words such as "um," "uh," or "hm," to sound more natural.
    - Do not start your response with 'sure', 'good question', 'great', 'absolutely', or any other obsequious statement.
    - Do not end your response with a question unless necessary for clarification.

    # Volume Control
    - You can adjust the speaker volume when the user asks to change, increase,
      decrease, raise, lower, or set the volume.
    - Call the set_volume tool with either a specific level (10-100) or a direction
      ("up" or "down") for relative adjustment.
    - For requests like "set volume to 50 percent", pass level=50.
    - For "louder", "turn it up", or "increase the volume", pass direction="up".
    - For "quieter", "turn it down", or "decrease the volume", pass direction="down".
    - After adjusting, confirm the new volume level to the user.

    # Current Information
    - Your built-in knowledge has a cutoff date. For ANY question that may
      involve information from after that cutoff date, such as news, sports schedules,
      scores, election results, prices, product releases, "who won",
      "when is", "what's the latest", etc., call the search_web tool with a
      self-contained version of the user's question.
    - NEVER answer "I don't know" or mention your knowledge cutoff without
      first trying the search_web tool.
    - Do not use search_web for timeless facts you already know (history,
      math, definitions, general knowledge), for weather (use the weather
      tools), or for the current time (use get_current_time).
    - When you get the search result, speak it naturally as your own answer.
      Do not read URLs, do not cite sources aloud, and do not say "according
      to my search" or "my search tool found".

    # Preambles
    - By default, call tools SILENTLY and speak only the result. Never say
      "let me check that for you", "let me set that timer", "one moment
      while I look that up", or similar before calling a tool.
    - This silent default applies to: get_current_time, get_current_weather,
      get_weather_forecast, set_timer, cancel_timer, get_timer_status,
      set_volume, set_interaction_mode, dismiss_false_wake, and
      exit_the_program. The tool's returned text is the spoken announcement.
    - The only tool that gets a brief one-sentence acknowledgment before it
      runs is search_web — e.g. "Let me check on that" or "I'll look that up." 
      The search takes a few seconds, so a short preamble avoids dead air.
    - Do NOT preamble non-tool answers either. Never say "let me think
      about that", "let me get back to your question", "let me check the
      context of your question", or similar throat-clearing before
      answering. Just answer directly.

    # Exiting
    - When the user asks to exit, quit, shut down, close, or stop the program,
      say a brief goodbye and call the exit_the_program tool.
    - Only call it when the user clearly wants the whole program to stop — not
      for "stop talking", "never mind", or "cancel that".

    # False-Wake Handling
    - Your wake word can occasionally fire from background noise, for example,
      dialogue from a TV show or radio, a podcast playing in the room, or a
      snippet of conversation between other people that happens to sound like
      "DaVinci."
    - Call the dismiss_false_wake tool ONLY when you are confident nobody is
      talking to you: the audio is clearly a TV/movie/radio/podcast scene, two
      or more other people talking to each other, or just noise or mumbling
      with no recognizable words.
    - If the audio contains anything that sounds like a question, a command, or
      a request (even if it is short, informal, partly cut off, or has
      background noise behind it) it is directed at you. Respond normally.
    - Hearing your own name, "DaVinci," at the start is normal. It is the wake
      word the user just said. It is not a sign of a false wake.
    - When you are unsure, respond rather than dismiss. Answering the TV once in
      a while is better than ignoring the person who is speaking to you.
    - When you do dismiss, produce no text and no audio output; only the
      function call itself. Do not say "sorry, I didn't catch that" or "could
      you repeat that." Just call the tool and stay silent.
    """
)

DAVINCI_NORMAL_ADDENDUM = ("""
    # Interaction Mode
    - You support three interaction modes: 'normal', 'conversational', and 'strict'.
    - You are currently in 'normal' mode, which means the microphone is guarded while you
      are speaking, so the user must say the wake word "DaVinci" to interrupt
      you. Between turns the user can speak freely without the wake word.
    - In 'conversational' mode, the user can interrupt you mid-sentence by
      simply speaking. No wake word is required.
    - In 'strict' mode (also called "wake-word only" mode), the user must say
      the wake word "DaVinci" before every new request, including follow-ups.
      The session and our conversation history stay intact between turns so that
      you can reference earlier discussion.
    - "strict mode", "wake-word only mode", "wake word only", and "only respond
      to the wake word" all refer to the same mode, so pass mode="strict" in
      every case.
    - When the user asks to switch modes (e.g. "switch to conversational
      mode", "go back to normal mode", "let me interrupt you", "switch to
      strict mode", "wake word only mode"), call the set_interaction_mode
      tool with the requested mode, then briefly confirm the change to the
      user.
    """
)

DAVINCI_CONVERSATIONAL_ADDENDUM = ("""
    # Conversational Style
    - Keep responses brief and natural, as the user may interrupt you at any time.
    - Deliver information in small, digestible chunks rather than long monologues.
    - Pause naturally between thoughts to give the user room to interject.

    # Interaction Mode
    - You support three interaction modes: 'normal', 'conversational', and 'strict'.
    - You are currently in 'conversational' mode, which means the user can interrupt you
      mid-sentence by simply speaking. No wake word is required to interrupt.
    - In 'normal' mode, the microphone is guarded while you are speaking, so the
      user must say the wake word "DaVinci" to interrupt you. Between turns
      the user can speak freely without the wake word.
    - In 'strict' mode (also called "wake-word only" mode), the user must say
      the wake word "DaVinci" before every new request, including follow-ups.
      The session and our conversation history stay intact between turns.
    - "strict mode", "wake-word only mode", "wake word only", and "only respond
      to the wake word" all refer to the same mode, so pass mode="strict" in
      every case.
    - When the user asks to switch modes (e.g. "switch to normal mode",
      "go back to wake-word mode", "use conversational mode", "switch to
      strict mode", "wake word only"), call the set_interaction_mode tool
      with the requested mode, then briefly confirm the change to the user.
    """
)

DAVINCI_STRICT_ADDENDUM = ("""
    # Interaction Mode
    - You are currently in 'strict' mode (also called "wake-word only" mode).
      After you finish speaking, the user must say the wake word "DaVinci"
      again before each new request, even short follow-ups. Until they do,
      anything they say will not reach you.
    - The session and our conversation history stay intact across these
      wake-word-gated turns, so you can reference what we just discussed.
    - You also support 'normal' and 'conversational' modes.
    - "strict mode", "wake-word only mode", "wake word only", and "only respond
      to the wake word" all refer to the SAME mode, so pass mode="strict" in
      every case.
    - When the user asks to switch modes (e.g. "switch to normal mode",
      "go to conversational mode", "stop requiring the wake word"), call the
      set_interaction_mode tool with the requested mode, then briefly confirm
      the change to the user.
    """
)

# Personality strings used throughout the rest of the script
DAVINCI                = DAVINCI_BASE + DAVINCI_NORMAL_ADDENDUM
DAVINCI_CONVERSATIONAL = DAVINCI_BASE + DAVINCI_CONVERSATIONAL_ADDENDUM
DAVINCI_STRICT         = DAVINCI_BASE + DAVINCI_STRICT_ADDENDUM

# --- Load OPENAI Key ---

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

# Client for the Responses API (built-in web search tool). The Realtime session
# uses its own raw websocket — this client is only for search_web().
search_client = openai_lib.OpenAI(api_key=OPENAI_API_KEY)

# --- Wake Word (OpenWakeWord) ---
# The .onnx model must sit in the SAME directory as this script (e.g. /home/pi/).
# The path is resolved from __file__, so the script can be launched from anywhere.

WAKE_MODEL_FILE   = "DaVinci_20261008_030815.onnx"
WAKE_MODEL_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), WAKE_MODEL_FILE)
WAKE_LABEL        = "DaVinci"      # console output only
OWW_RATE          = 16000          # Hz — processing rate required by OpenWakeWord
OWW_CHUNK         = 1280           # samples — 80 ms, OWW's native frame size
OWW_THRESHOLD     = 0.5            # confidence gate (0.0-1.0); raise for fewer false wakes
OWW_VAD_THRESHOLD = 0.4            # openwakeword's bundled Silero VAD (onnxruntime, no torch)

# --- Quiet-Room Gate and Health Line ---
# Scoring a frame runs several small neural networks, ~12 times a second. While
# the room is quiet the gate skips that work and only measures loudness.
GATE_RMS              = None   # loudness that wakes the engine; None = auto, 0 = always on
GATE_MIN_RMS          = 60     # auto mode never sets the threshold below this
GATE_FLOOR_FACTOR     = 2.5    # auto mode: this many times the measured background level
GATE_PREROLL_FRAMES   = 25     # 2 s of audio kept back so the engine hears the wake word's start
GATE_HANG_SECONDS     = 3.0    # quiet time before the engine goes back to sleep
GATE_KEEP_AWAKE_SCORE = 0.05   # a near-miss score this high also keeps the engine awake
STATS_INTERVAL        = 60.0   # seconds between "Health:" lines (0 = off)

# Safety cap on the startup bridge (see the wake-word handoff in main()): audio
# captured while the websocket is still connecting. Normally well under a second.
BRIDGE_MAX_SECONDS = 5

# --- Audio and Streaming ---

CHUNK_SIZE = 2048
RATE = 24000
FORMAT = pyaudio.paInt16
INACTIVITY_TIMEOUT = 3   # DaVinci times out after this many seconds of inactivity
STRICT_INACTIVITY_TIMEOUT = 30   # Longer window in 'strict' mode so the user can use wake-word for follow-ups

# "normal" - existing NoInterrupt behavior (OpenWakeWord guards during AI response)
# "conversational" - OpenAI server-side VAD handles interruption; mic stays active during AI response
INTERACTION_MODE = "normal"

# True - resolve the default weather location from the device's public IP at startup
# False - use the hardcoded fallback below
USE_IP_LOCATION = True

# Default location used when no city is specified in a weather request.
# Overwritten at startup if USE_IP_LOCATION = True and geolocation succeeds.
DEFAULT_LATITUDE = 40.7128    # Open-Meteo works from coordinates
DEFAULT_LONGITUDE = -74.0060
DEFAULT_LOCATION_DISPLAY = "New York, New York"  # human-readable name for responses

# How many days ahead get_weather_forecast will look (Open-Meteo offers up to 15).
FORECAST_MAX_DAYS = 7

# --- Wi-Fi Setup Hotspot ---
# If DaVinci starts without Wi-Fi, it raises its own open Wi-Fi network so a
# phone can join it and enter the home network's name and password on a web
# page. DaVinci speaks the instructions from recordings made while it was online.
WIFI_SETUP_ENABLED = True
WIFI_IFACE = "wlan0"
HOTSPOT_SSID = "DaVinci-Setup"
HOTSPOT_CON = "DaVinciSetup"            # NetworkManager connection profile name
HOTSPOT_IP = "10.42.0.1"                # NetworkManager's default for shared mode
WEB_PORT = 8080                         # setup page port
NO_WIFI_GRACE_SECONDS = 30              # no saved Wi-Fi at all: wait this long before the hotspot
WIFI_CHECK_INTERVAL = 30.0
UNDETECTED_GRACE_SECONDS = 90           # saved network never seen in a scan for this long - setup
STUCK_BACKSTOP_SECONDS = 3600           # saved network visible but never connects - setup anyway
HOTSPOT_RETRY_INTERVAL = 300            # while the hotspot is up, retest the saved network this often
HOTSPOT_RETRY_TEST_SECONDS = 20         # how long NetworkManager gets to reconnect during a retest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETUP_PAGE = "davinci_setup.html"
SETUP_AUDIO_DIR = os.path.join(SCRIPT_DIR, "setup_audio")
TTS_MODEL_CANDIDATES = ["gpt-4o-mini-tts", "tts-1"]   # tried in order
TTS_VOICE_CANDIDATES = ["cedar", "ash"]               # tried in order

# Speaker playback volume.  Updated by the set_volume tool so DaVinci's
# view of "current volume" stays in sync with what was last applied.
current_volume = 80

# --- ALSA Volume Helpers ---

# The card index and the names of the volume controls differ between USB
# speakerphones (and the card index depends on what else the Pi has enabled), so
# both are discovered at startup rather than hardcoded. This lets one speakerphone
# be swapped for another with no changes here or to the system configuration.

alsa_card = None          # resolved card index, as a string
alsa_playback_ctl = None  # name of a control with playback volume, or None
alsa_capture_ctl = None   # name of a control with capture volume, or None

def find_alsa_card() -> str:
    """Find the ALSA card index of the USB speakerphone.
    Returns the first USB card listed in /proc/asound/cards, or "1" if none is
    found (the index this program originally assumed).
    """
    try:
        with open("/proc/asound/cards", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return "1"

    entries, current = [], None
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\s+\[(.*?)\s*\]:\s*(.*)", line)
        if m:
            current = [m.group(1), m.group(2) + " " + m.group(3)]
            entries.append(current)
        elif current is not None:
            current[1] += " " + line.strip()

    for idx, desc in entries:
        if "usb" in desc.lower():
            print(f"ALSA mixer: found USB audio device on card {idx}: {desc}")
            return idx
    print("ALSA mixer: no USB audio device found - is the speakerphone plugged in?")
    return "1"

def init_alsa_mixer() -> None:
    """Resolve the card index and discover which volume controls actually exist."""
    global alsa_card, alsa_playback_ctl, alsa_capture_ctl
    alsa_card = find_alsa_card()

    dump = ""
    try:
        r = subprocess.run(["amixer", "-c", alsa_card],
                           capture_output=True, text=True, timeout=2)
        if r.returncode == 0:
            dump = r.stdout
    except Exception as e:
        print(f"amixer probe failed: {e}")

    # Each control prints as:
    # Simple mixer control 'PCM',0
    # Capabilities: pvolume pvolume-joined pswitch pswitch-joined
    for name, caps in re.findall(
        r"Simple mixer control '([^']+)',\d+\s*\n\s*Capabilities:\s*(.*)", dump
    ):
        if "pvolume" in caps and alsa_playback_ctl is None:
            alsa_playback_ctl = name
        if "cvolume" in caps and alsa_capture_ctl is None:
            alsa_capture_ctl = name

    print(f"ALSA mixer: card {alsa_card}, "
          f"playback volume control = {alsa_playback_ctl or 'NONE'}, "
          f"capture volume control = {alsa_capture_ctl or 'NONE'}")
    if alsa_capture_ctl is None:
        print("ALSA mixer: this device exposes no capture volume control - mic gain is "
              "governed by the device itself and will not be set.")

def _ensure_alsa_mixer() -> None:
    if alsa_card is None:
        init_alsa_mixer()

def set_alsa_capture(gain_pct: int) -> bool:
    """Set ALSA microphone capture volume, if the device exposes one."""
    _ensure_alsa_mixer()
    if alsa_capture_ctl is None:
        return False
    try:
        result = subprocess.run(
            ["amixer", "-c", alsa_card, "-q", "sset", alsa_capture_ctl, f"{gain_pct}%"],
            check=False, timeout=1
        )
        return result.returncode == 0
    except Exception as e:
        print(f"amixer error: {e}")
        return False

def set_alsa_playback(vol_pct: int) -> bool:
    """Set ALSA speaker playback volume, if the device exposes one."""
    _ensure_alsa_mixer()
    if alsa_playback_ctl is None:
        return False
    try:
        result = subprocess.run(
            ["amixer", "-c", alsa_card, "-q", "sset", alsa_playback_ctl, f"{vol_pct}%"],
            check=False, timeout=1
        )
        return result.returncode == 0
    except Exception as e:
        print(f"amixer error: {e}")
        return False

pa_instance: Optional[pyaudio.PyAudio] = None

def play_chime():
    """Play a two-tone chime three times (1-second apart) using PyAudio.
    Used when a timer fires after the session ends."""
    if pa_instance is None:
        print("Chime: PyAudio instance not available.")
        return

    sample_rate = RATE   # 24000 Hz — same rate the device already handles
    duration = 1.0
    num_samples = int(sample_rate * duration)
    t = np.arange(num_samples)

    # Sum two sines (700 Hz + 1050 Hz)
    wave = (np.sin(2 * np.pi * 700  * t / sample_rate)
          + np.sin(2 * np.pi * 1050 * t / sample_rate))

    # Linear fade-in (0.2 s) and fade-out (0.4 s) envelope.
    envelope = np.ones(num_samples)
    fade_in  = int(sample_rate * 0.2)
    fade_out = int(sample_rate * 0.4)
    envelope[:fade_in]    = np.linspace(0.0, 1.0, fade_in)
    envelope[-fade_out:]  = np.linspace(1.0, 0.0, fade_out)

    wave = (wave / np.max(np.abs(wave)) * envelope * 32767).astype(np.int16)
    tone = wave.tobytes()

    for i in range(3):
        if i > 0:
            time.sleep(1.0)
        try:
            stream = pa_instance.open(
                format=FORMAT,
                channels=1,
                rate=sample_rate,
                output=True,
            )
            stream.write(tone)
            stream.stop_stream()
            stream.close()
        except Exception as e:
            print(f"Chime error: {e}")
            break

timers: Dict[str, Dict[str, Any]] = {}   # label -> {"timer": threading.Timer, "start": float, "duration": float}
timers_lock = threading.Lock()

active_session: Optional["Realtime"] = None
active_session_lock = threading.Lock()

def fire_timer(label):
    """Called by threading.Timer when a countdown expires.
    Announces through the currently active session (if any) or falls back to a chime."""
    with timers_lock:
        timers.pop(label, None)

    with active_session_lock:
        session = active_session

    session_live = (
        session is not None
        and not session.sock.is_stopped()
        and session.sock.ws is not None
        and session.sock.ws.connected
    )

    if session_live:
        print(f"Timer '{label}' fired — announcing via active session.")
        if len(session.audio.audio_buffer) > 0:
            session.audio.clear_buffer()
            session.sock.send({"type": "response.cancel"})
        session.sock.send({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": f"[System: The '{label}' timer has finished. Please announce this to the user.]"
                }]
            }
        })
        session.sock.send({"type": "response.create"})
    else:
        print(f"Timer '{label}' fired — no active session, playing chime.")
        threading.Thread(target=play_chime, daemon=True).start()

# --- Tool Helper and Functions ---

def get_ip_location():
    """Fetch coordinates and city/region from the device's public IP via ip-api.com.
    Returns (latitude, longitude, display_string) on success, or None on failure."""
    try:
        url = "http://ip-api.com/json"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") == "success":
            city    = data.get("city", "")
            region  = data.get("regionName", "")
            country = data.get("country", "")
            lat     = data.get("lat")
            lon     = data.get("lon")
            if city and lat is not None and lon is not None:
                display = ", ".join(p for p in [city, region, country] if p)
                return float(lat), float(lon), display
    except Exception as e:
        print(f"IP geolocation error: {e}")
    return None

def get_current_time():
    """Returns the current date and time as a natural language string."""
    now = datetime.datetime.now()
    return now.strftime("The current date and time is %A, %B %d, %Y at %I:%M %p.")

# Tried in order until one works; the winning combination is remembered.
SEARCH_MODEL_CANDIDATES = ["gpt-5-mini", "gpt-5", "gpt-4.1-mini", "gpt-4o-mini"]
SEARCH_TOOL_TYPES = ["web_search", "web_search_preview"]
search_model = None
search_tool_type = None

def search_web(query):
    """Answers a question with current information using the OpenAI
    Responses API's built-in web search tool. Reuses the existing
    OpenAI API key (the same one used for the Realtime session)."""
    global search_model, search_tool_type

    if not query or not query.strip():
        return "No search question was provided. Ask the user what they want to know."

    today = datetime.datetime.now().strftime("%A, %B %d, %Y")
    prompt = (
        f"Today's date is {today}. Answer the following question using current "
        f"information from the web. Answer concisely in 2-4 sentences of plain "
        f"spoken prose — no markdown, no lists, no URLs or citations.\n\n"
        f"Question: {query.strip()}"
    )

    print(f"Web search: {query.strip()}")

    if search_model:
        models = [search_model] + [m for m in SEARCH_MODEL_CANDIDATES
                                    if m != search_model]
    else:
        models = SEARCH_MODEL_CANDIDATES
    if search_tool_type:
        tool_types = [search_tool_type] + [t for t in SEARCH_TOOL_TYPES
                                            if t != search_tool_type]
    else:
        tool_types = SEARCH_TOOL_TYPES

    for model in models:
        for tool_type in tool_types:
            try:
                response = search_client.responses.create(
                    model=model,
                    tools=[{"type": tool_type}],
                    input=prompt,
                )
                if search_model != model or search_tool_type != tool_type:
                    search_model = model
                    search_tool_type = tool_type
                    print(f"Web search model: {model} (tool: {tool_type})")
                answer = (getattr(response, "output_text", "") or "").strip()
                if answer:
                    return answer
                return ("The search returned no answer. Let the user know you "
                        "couldn't find current information on that.")
            except openai_lib.RateLimitError:
                return "The search service is rate-limited right now. Ask the user to try again in a moment."
            except Exception as e:
                msg = str(e)
                if ("model" in msg.lower() and ("not found" in msg.lower()
                        or "does not exist" in msg.lower() or "404" in msg)):
                    print(f"Search model '{model}' unavailable, trying next candidate...")
                    break   # next model — no point trying other tool types
                if "web_search" in msg or "tool" in msg.lower():
                    print(f"Tool type '{tool_type}' rejected for '{model}': {e}")
                    continue   # try the other tool type on this model
                print(f"Web search error: {e}")
                return "The web search failed. Let the user know and suggest trying again."

    print("Web search failed: no compatible model/tool combination available.")
    return ("The web search failed because no compatible search model is "
            "available. Let the user know.")

# --- Weather (Open-Meteo) ---

WMO_DESCRIPTIONS = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    56: "light freezing drizzle", 57: "dense freezing drizzle",
    61: "light rain", 63: "moderate rain", 65: "heavy rain",
    66: "light freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "moderate snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    85: "light snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with light hail",
    99: "thunderstorms with heavy hail",
}

def describe_weather_code(code):
    """Turn a WMO weather code into a spoken description."""
    try:
        return WMO_DESCRIPTIONS.get(int(code), "unsettled conditions")
    except (TypeError, ValueError):
        return "unsettled conditions"

def geocode_location(name):
    """Resolve a place name to coordinates with Open-Meteo's geocoding API.
    A qualifier after a comma is honored ("Paris, France", "Springfield, IL").
    Returns (latitude, longitude, display_string), or None if nothing matches."""
    name = name.strip()
    url = (
        f"https://geocoding-api.open-meteo.com/v1/search"
        f"?name={urllib.parse.quote(name)}"
        f"&count=1&language=en&format=json"
    )
    with urllib.request.urlopen(url, timeout=5) as resp:
        data = json.loads(resp.read().decode())

    results = data.get("results") or []
    if not results:
        # "Springfield IL" only matches with the comma, so retry with one added
        if "," not in name and " " in name:
            city, qualifier = name.rsplit(" ", 1)
            return geocode_location(f"{city}, {qualifier}")
        return None

    top = results[0]
    parts = []
    for part in (top.get("name"), top.get("admin1"), top.get("country")):
        if part and part not in parts:
            parts.append(part)
    return top["latitude"], top["longitude"], ", ".join(parts)

def resolve_weather_location(location):
    """Returns (latitude, longitude, display_string) for a spoken location, the
    default location when none is given, or None if the place can't be found."""
    if not location or not location.strip():
        return DEFAULT_LATITUDE, DEFAULT_LONGITUDE, DEFAULT_LOCATION_DISPLAY
    return geocode_location(location)

def fetch_open_meteo(latitude, longitude, variables):
    """Calls the Open-Meteo forecast API in imperial units and returns the JSON."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        f"&{variables}"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
        f"&timezone=auto"
    )
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode())

def get_current_weather(location=None):
    """Fetches current weather from Open-Meteo for the given location.
    Uses the default location if no location is provided."""
    try:
        place = resolve_weather_location(location)
        if place is None:
            return f"Sorry, I couldn't find weather data for '{location}'."
        latitude, longitude, location_display = place

        data = fetch_open_meteo(
            latitude, longitude,
            "current=temperature_2m,weather_code,wind_speed_10m"
        )
        current = data["current"]

        temp      = round(current["temperature_2m"])
        wind      = round(current["wind_speed_10m"])
        condition = describe_weather_code(current["weather_code"])

        return (
            f"The current weather in {location_display} is {condition}, "
            f"with a temperature of {temp} degrees Fahrenheit "
            f"and winds at {wind} miles per hour."
        )
    except Exception as e:
        print(f"Weather error: {e}")
        return "I was unable to retrieve the weather right now. Please try again in a moment."

def resolve_forecast_date(date_str):
    """Resolve a date string to a datetime.date object.
    Accepts: None/'tomorrow', a weekday name, or an ISO 'YYYY-MM-DD' string.
    Returns (date, error_string).  error_string is None on success."""
    today    = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)

    if not date_str or date_str.strip().lower() == "tomorrow":
        return tomorrow, None

    ds = date_str.strip().lower()

    # Weekday name resolution
    weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    if ds in weekdays:
        target_dow = weekdays.index(ds)
        days_ahead = (target_dow - tomorrow.weekday()) % 7
        target = tomorrow + datetime.timedelta(days=days_ahead)
        return target, None

    # ISO date string
    try:
        target = datetime.date.fromisoformat(date_str.strip())
        return target, None
    except ValueError:
        pass

    return None, f"I don't understand the date '{date_str}'. Try 'tomorrow', a weekday name, or a date like '2025-04-22'."

def get_weather_forecast(location=None, date=None):
    """Fetches the daily weather forecast from Open-Meteo for a specific day.
    Defaults to the default location and tomorrow if no arguments are provided."""
    target_date, err = resolve_forecast_date(date)
    if err:
        return err

    today = datetime.date.today()
    if target_date <= today:
        return "I can only forecast future dates. For today's current conditions, ask for the current weather."
    if (target_date - today).days > FORECAST_MAX_DAYS:
        return (f"The forecast is only available up to {FORECAST_MAX_DAYS} days ahead. "
                f"Please ask about a closer date.")

    try:
        place = resolve_weather_location(location)
        if place is None:
            return f"Sorry, I couldn't find forecast data for '{location}'."
        latitude, longitude, location_display = place

        # +2: today itself, plus a day of slack for places whose local date
        # is ahead of this device's
        data = fetch_open_meteo(
            latitude, longitude,
            "daily=weather_code,temperature_2m_max,temperature_2m_min,wind_speed_10m_max"
            f"&forecast_days={FORECAST_MAX_DAYS + 2}"
        )
        daily = data["daily"]

        date_label = target_date.strftime("%A, %B %d, %Y")

        days = daily.get("time", [])
        if target_date.isoformat() not in days:
            return f"No forecast data is available for {date_label} in {location_display}."
        i = days.index(target_date.isoformat())

        high      = round(daily["temperature_2m_max"][i])
        low       = round(daily["temperature_2m_min"][i])
        wind      = round(daily["wind_speed_10m_max"][i])
        condition = describe_weather_code(daily["weather_code"][i])

        return (
            f"The weather forecast for {location_display} on {date_label} is "
            f"{condition}, with a high of {high} degrees Fahrenheit, "
            f"a low of {low} degrees Fahrenheit, and winds up to {wind} miles per hour."
        )

    except Exception as e:
        print(f"Forecast error: {e}")
        return "I was unable to retrieve the forecast right now. Please try again in a moment."

# --- Wi-Fi Setup: spoken instructions ---

def spoken_setup_address():
    ip = " dot ".join(HOTSPOT_IP.split("."))
    port = " ".join(str(WEB_PORT))
    return f"{ip}, colon, {port}"

SPOKEN_HOTSPOT = HOTSPOT_SSID.replace("-", " ")

SETUP_MESSAGES = {
    "setup": (
        "I'm not connected to Wi-Fi. To set me up, use your phone to join the "
        f"Wi-Fi network called {SPOKEN_HOTSPOT}. Then open your web browser and "
        f"go to the address {spoken_setup_address()}. "
        f"Again, the address is {spoken_setup_address()}. "
        "Choose your home network there and enter its password."
    ),
    "connected": "Thank you. I'm connected to Wi-Fi now and ready to help.",
    "failed": (
        "I couldn't connect to that network. Please check the password, join the "
        f"{SPOKEN_HOTSPOT} network again, and try once more."
    ),
}

def setup_clip_path(key):
    """Recording file for a setup message. The name carries a hash of the
    wording, so changing a message (or the hotspot name) re-records it."""
    digest = hashlib.sha1(SETUP_MESSAGES[key].encode("utf-8")).hexdigest()[:10]
    return os.path.join(SETUP_AUDIO_DIR, f"{key}_{digest}.pcm")

def synthesize_speech(text):
    """Raw 24 kHz 16-bit mono PCM of `text` from OpenAI text-to-speech, or None."""
    last_error = None
    for model in TTS_MODEL_CANDIDATES:
        for voice in TTS_VOICE_CANDIDATES:
            try:
                response = search_client.audio.speech.create(
                    model=model, voice=voice, input=text, response_format="pcm",
                )
                data = response.content
                if data:
                    return data
            except Exception as e:
                last_error = e
    print(f"Setup audio: text-to-speech failed ({last_error})")
    return None

def prepare_setup_audio():
    """Record any missing setup messages while online, so DaVinci can still
    speak them when it has no internet connection."""
    try:
        os.makedirs(SETUP_AUDIO_DIR, exist_ok=True)
        wanted = set()
        for key, text in SETUP_MESSAGES.items():
            clip = setup_clip_path(key)
            wanted.add(os.path.basename(clip))
            if os.path.exists(clip):
                continue
            audio = synthesize_speech(text)
            if audio is None:
                print("Setup audio: will try again next time DaVinci starts online.")
                return
            with open(clip + ".tmp", "wb") as f:
                f.write(audio)
            os.replace(clip + ".tmp", clip)
            print(f"Setup audio: recorded the '{key}' message.")
        # Remove recordings of older wording
        for name in os.listdir(SETUP_AUDIO_DIR):
            if name.endswith(".pcm") and name not in wanted:
                os.remove(os.path.join(SETUP_AUDIO_DIR, name))
    except Exception as e:
        print(f"Setup audio: could not prepare recordings ({e})")

def play_setup_clip(key):
    """Play a recorded setup message. Returns False if it can't be played."""
    try:
        with open(setup_clip_path(key), "rb") as f:
            data = f.read()
    except OSError:
        print(f"Setup audio: no recording of the '{key}' message yet — "
              f"it is recorded the first time DaVinci runs with internet.")
        return False
    if pa_instance is None:
        return False
    try:
        stream = pa_instance.open(format=FORMAT, channels=1, rate=RATE, output=True)
        stream.write(data)
        stream.stop_stream()
        stream.close()
        return True
    except Exception as e:
        print(f"Setup audio: playback failed ({e})")
        return False

# --- Wi-Fi Setup: connectivity check and hotspot (NetworkManager) ---

class WifiManager(threading.Thread):
    """Checks for a network connection at startup. If the Pi isn't online
    (including a saved network that's visible but won't connect), it raises an
    open hotspot so a mobile device can provision credentials through the setup page.
    The thread ends once the Pi is online."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop_event = threading.Event()
        self.online_event = threading.Event()   # set once online (or if disabled)
        self.lock = threading.Lock()
        self.state = "starting"    # starting | online | hotspot | connecting | disabled
        self.scan_cache = []       # last good scan (AP mode usually can't scan)
        self._down_since = None
        self._last_seen_known = None
        self._announced_setup = False
        self._announcements = []   # setup messages waiting for the main loop to speak

        if not WIFI_SETUP_ENABLED:
            self._disable("turned off (WIFI_SETUP_ENABLED = False)")
        elif shutil.which("nmcli") is None:
            self._disable("NetworkManager's nmcli command was not found")

    def _disable(self, reason):
        self.state = "disabled"
        self.online_event.set()
        print(f"Wi-Fi setup hotspot: {reason}.")

    # --- nmcli helpers ---

    def _run(self, cmd, timeout):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
        except Exception as e:
            return False, str(e)

    def _nmcli(self, *args, timeout=20):
        ok, out = self._run(["nmcli", *args], timeout)
        # Without a desktop login (e.g. running as a service), NetworkManager
        # may refuse changes; retry through passwordless sudo if it does.
        if not ok and ("Not authorized" in out or "Insufficient privileges" in out):
            ok, out = self._run(["sudo", "-n", "nmcli", *args], timeout)
        return ok, out

    def network_online(self):
        """True when a real network connection (Wi-Fi or Ethernet, not our
        hotspot) is active."""
        ok, out = self._nmcli("-t", "-f", "NAME,TYPE,DEVICE",
                              "connection", "show", "--active", timeout=10)
        if not ok:
            return False
        for line in out.splitlines():
            parts = line.rsplit(":", 2)
            if len(parts) < 3 or parts[0] == HOTSPOT_CON:
                continue
            if parts[1] in ("802-11-wireless", "wifi", "802-3-ethernet", "ethernet"):
                return True
        return False

    def scan_networks(self):
        """Returns [{ssid, signal, open}] sorted by signal, or None on
        failure (typical while the hotspot has the radio in AP mode)."""
        ok, out = self._nmcli("-t", "-f", "SSID,SIGNAL,SECURITY",
                              "device", "wifi", "list", "--rescan", "yes",
                              timeout=25)
        if not ok:
            return None
        best = {}
        for line in out.splitlines():
            parts = line.rsplit(":", 2)
            if len(parts) != 3:
                continue
            ssid = parts[0].replace("\\:", ":").strip()
            if not ssid or ssid == HOTSPOT_SSID:
                continue          # hidden network, or our own hotspot
            try:
                signal = int(parts[1])
            except ValueError:
                signal = 0
            is_open = parts[2].strip() in ("", "--")
            if ssid not in best or signal > best[ssid]["signal"]:
                best[ssid] = {"ssid": ssid, "signal": signal, "open": is_open}
        return sorted(best.values(), key=lambda n: -n["signal"])

    def known_ssids(self):
        """SSIDs of saved Wi-Fi profiles, excluding our own setup hotspot."""
        ok, out = self._nmcli("-t", "-f", "NAME,TYPE", "connection", "show")
        if not ok:
            return set()
        ssids = set()
        for line in out.splitlines():
            parts = line.rsplit(":", 1)
            if len(parts) != 2:
                continue
            name, conn_type = parts[0].replace("\\:", ":").strip(), parts[1].strip()
            if conn_type != "802-11-wireless" or name == HOTSPOT_CON:
                continue
            ok2, ssid_out = self._nmcli("-g", "802-11-wireless.ssid",
                                        "connection", "show", name, timeout=10)
            ssid = ssid_out.strip() if ok2 else ""
            ssids.add(ssid or name)
        return ssids

    def known_network_visible(self, known_ssids):
        nets = self.scan_networks()
        if nets is None:
            return False
        if nets:
            self.scan_cache = nets
        return bool(known_ssids & {n["ssid"] for n in nets})

    # --- state ---

    def _announce(self, key):
        with self.lock:
            self._announcements.append(key)

    def take_announcement(self):
        """Next setup message for the main loop to speak, or None."""
        with self.lock:
            return self._announcements.pop(0) if self._announcements else None

    def in_setup(self):
        with self.lock:
            return self.state in ("hotspot", "connecting")

    def snapshot(self):
        with self.lock:
            return self.state

    def _set_online(self, announce):
        with self.lock:
            was_setup = self.state in ("hotspot", "connecting")
            self.state = "online"
        self.online_event.set()
        if was_setup:
            set_led_off()
            if announce:
                self._announce("connected")

    # --- main loop: startup check only ---

    def run(self):
        if self.state == "disabled":
            return
        next_hotspot_retry = None
        while not self.stop_event.is_set():
            try:
                state = self.snapshot()

                if state != "hotspot":
                    next_hotspot_retry = None

                if state == "connecting":
                    self.stop_event.wait(2)
                    continue

                if state == "online":
                    break

                if state == "hotspot":
                    now = time.time()
                    if next_hotspot_retry is None:
                        next_hotspot_retry = now + HOTSPOT_RETRY_INTERVAL
                    elif now >= next_hotspot_retry:
                        if self._retry_known_network():
                            continue
                        next_hotspot_retry = now + HOTSPOT_RETRY_INTERVAL
                    self.stop_event.wait(WIFI_CHECK_INTERVAL)
                    continue

                if self.network_online():
                    self._teardown_hotspot()
                    self._set_online(announce=False)
                    print("Network: online.")
                    break

                now = time.time()
                if self._down_since is None:
                    self._down_since = now
                    print("Network: not connected — checking for a saved Wi-Fi network...")

                known_ssids = self.known_ssids()
                if not known_ssids:
                    # Never configured — nothing to detect, so use a short grace period
                    if now - self._down_since >= NO_WIFI_GRACE_SECONDS:
                        self.start_hotspot()
                else:
                    if self.known_network_visible(known_ssids):
                        self._last_seen_known = now
                    last_seen = self._last_seen_known or self._down_since
                    if (now - last_seen >= UNDETECTED_GRACE_SECONDS
                            or now - self._down_since >= STUCK_BACKSTOP_SECONDS):
                        self.start_hotspot()
                self.stop_event.wait(WIFI_CHECK_INTERVAL)
            except Exception as e:
                print(f"Wi-Fi setup error, retrying: {e}")
                self.stop_event.wait(WIFI_CHECK_INTERVAL)

    def start_hotspot(self):
        # Scan while the radio can still scan; the cache feeds the setup page
        # once AP mode blocks scanning.
        nets = self.scan_networks()
        if nets:
            self.scan_cache = nets
        self._nmcli("connection", "delete", HOTSPOT_CON)
        ok, out = self._nmcli(
            "connection", "add", "type", "wifi", "ifname", WIFI_IFACE,
            "con-name", HOTSPOT_CON, "autoconnect", "no",
            "ssid", HOTSPOT_SSID,
            "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
            "ipv4.method", "shared", "ipv6.method", "disabled")
        if ok:
            ok, out = self._nmcli("connection", "up", HOTSPOT_CON, timeout=30)
        if not ok:
            print(f"Wi-Fi setup hotspot failed: {out.strip()}")
            self._down_since = time.time()   # retry after another grace period
            return
        with self.lock:
            self.state = "hotspot"
        start_setup_server(self)
        set_led_setup()
        print(f"Wi-Fi setup hotspot '{HOTSPOT_SSID}' is up — "
              f"setup page at http://{HOTSPOT_IP}:{WEB_PORT}/")
        if not self._announced_setup:
            self._announced_setup = True
            self._announce("setup")

    def _teardown_hotspot(self):
        self._nmcli("connection", "down", HOTSPOT_CON, timeout=15)
        self._nmcli("connection", "delete", HOTSPOT_CON, timeout=15)

    def _retry_known_network(self):
        """Briefly drops the hotspot so NetworkManager can try any saved
        Wi-Fi profile; re-raises the hotspot if it doesn't reconnect."""
        print("Wi-Fi setup: testing for the saved network...")
        self._nmcli("connection", "down", HOTSPOT_CON, timeout=15)
        deadline = time.time() + HOTSPOT_RETRY_TEST_SECONDS
        while time.time() < deadline:
            if self.network_online():
                self._nmcli("connection", "delete", HOTSPOT_CON)
                self._set_online(announce=True)
                print("Wi-Fi setup: the saved network is back — hotspot retired.")
                return True
            time.sleep(2)
        ok, out = self._nmcli("connection", "up", HOTSPOT_CON, timeout=30)
        if not ok:
            print(f"Wi-Fi setup: re-raising the hotspot failed: {out.strip()}")
        return False

    def submit_wifi(self, ssid, password):
        """Called from the setup page. Runs in a worker so the HTTP response
        goes out before the hotspot (and the phone's connection) goes away."""
        def _do():
            with self.lock:
                self.state = "connecting"
            time.sleep(2)                       # let the phone get its 200 OK
            self._nmcli("connection", "down", HOTSPOT_CON, timeout=15)
            self._nmcli("connection", "delete", ssid)   # drop a stale profile
            args = ["device", "wifi", "connect", ssid]
            if password:
                args += ["password", password]
            ok, out = self._nmcli(*args, timeout=60)
            if ok and self.network_online():
                self._teardown_hotspot()
                self._set_online(announce=True)
                print(f"Wi-Fi setup: joined '{ssid}'.")
                return
            print(f"Wi-Fi setup: joining '{ssid}' failed: {out.strip()}")
            self._nmcli("connection", "delete", ssid)
            ok2, _ = self._nmcli("connection", "up", HOTSPOT_CON, timeout=30)
            with self.lock:
                self.state = "hotspot" if ok2 else "starting"
            self._down_since = time.time() if ok2 else 0
            self._announce("failed")
        threading.Thread(target=_do, daemon=True).start()

    def shutdown(self):
        self.stop_event.set()
        if self.in_setup():
            self._teardown_hotspot()

# --- Wi-Fi Setup: web page ---

class SetupHandler(BaseHTTPRequestHandler):
    wifi: Optional[WifiManager] = None   # wired up by start_setup_server()
    server_version = "DaVinci/1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/setup"):
            if not self.wifi.in_setup():
                self._send(200, "<p>DaVinci is connected to the network.</p>", "text/html")
                return
            try:
                with open(os.path.join(SCRIPT_DIR, SETUP_PAGE), encoding="utf-8") as f:
                    self._send(200, f.read(), "text/html")
            except OSError:
                self._send(500, json.dumps({"error": f"{SETUP_PAGE} missing on the Pi"}))
        elif path == "/api/scan":
            nets = self.wifi.scan_networks()
            if nets:
                self.wifi.scan_cache = nets
            else:
                nets = self.wifi.scan_cache
            self._send(200, json.dumps({"networks": nets}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path != "/api/wifi":
            self._send(404, json.dumps({"error": "not found"}))
            return
        # Only while the hotspot is up — never let someone on the home network
        # change DaVinci's Wi-Fi.
        if self.wifi.snapshot() != "hotspot":
            self._send(409, json.dumps({"error": "not in setup mode"}))
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, OSError):
            self._send(400, json.dumps({"error": "bad request"}))
            return
        ssid = (payload.get("ssid") or "").strip()
        if not ssid:
            self._send(400, json.dumps({"error": "ssid required"}))
            return
        self.wifi.submit_wifi(ssid, payload.get("password") or "")
        self._send(200, json.dumps({"ok": True}))

setup_server = None

def start_setup_server(wifi):
    """Start the setup page's web server the first time the hotspot comes up."""
    global setup_server
    if setup_server is not None:
        return
    SetupHandler.wifi = wifi
    try:
        setup_server = ThreadingHTTPServer(("0.0.0.0", WEB_PORT), SetupHandler)
    except OSError as e:
        print(f"Wi-Fi setup: web server failed to start on port {WEB_PORT}: {e}")
        return
    threading.Thread(target=setup_server.serve_forever, daemon=True).start()

def apply_ip_location():
    """Resolve the default weather location from the device's public IP."""
    global DEFAULT_LATITUDE, DEFAULT_LONGITUDE, DEFAULT_LOCATION_DISPLAY
    result = get_ip_location()
    if result:
        DEFAULT_LATITUDE, DEFAULT_LONGITUDE, DEFAULT_LOCATION_DISPLAY = result
        print(f"IP geolocation: default location set to '{DEFAULT_LOCATION_DISPLAY}'.")
    else:
        print("IP geolocation failed — keeping hardcoded default location.")

def when_online(wifi):
    """Startup work that needs the internet, run once the network is up."""
    wifi.online_event.wait()
    if USE_IP_LOCATION:
        apply_ip_location()
    if wifi.snapshot() != "disabled":
        prepare_setup_audio()

def _drain_mic(stream):
    """Discard audio the mic buffered while DaVinci was speaking."""
    try:
        while stream.get_read_available() >= OWW_CHUNK:
            stream.read(OWW_CHUNK, exception_on_overflow=False)
    except Exception:
        pass

def speak_setup_message(key, wifi, audio_stream, gate):
    """Speak a recorded setup message from the main loop, then make sure the
    wake-word engine doesn't hear DaVinci's own voice."""
    set_led_pulse()
    play_setup_clip(key)
    if wifi.in_setup():
        set_led_setup()
    else:
        set_led_off()
    _drain_mic(audio_stream)
    gate.rearm()

class Socket:
    def __init__(self, api_key, ws_url):
        self.api_key = api_key
        self.ws_url = ws_url
        self.ws: Any = None
        self.on_msg = None
        self._stop_event = threading.Event()
        self.lock = threading.Lock()

    def is_stopped(self):
        return self._stop_event.is_set()

    def connect(self):
        self.ws = create_connection(
            self.ws_url,
            header=[f"Authorization: Bearer {self.api_key}"]
        )
        print("Connected to WebSocket.")
        threading.Thread(target=self._receive_messages, daemon=True).start()

    def _receive_messages(self):
        while not self._stop_event.is_set():
            try:
                raw = self.ws.recv()
                if raw and self.on_msg:
                    self.on_msg(json.loads(raw))
            except WebSocketConnectionClosedException:
                if not self._stop_event.is_set(): print("WebSocket closed by server.")
                break
            except Exception as e:
                if not self._stop_event.is_set(): print(f"Error: {e}")
        print("Receiver thread exiting.")
        set_led_off()

    def send(self, obj):
        try:
            with self.lock:
                if self.ws and self.ws.connected:
                    self.ws.send(json.dumps(obj))
        except Exception as e:
            print(f"Send error: {e}")

    def close(self):
        if not self._stop_event.is_set():
            self._stop_event.set()
            if self.ws:
                try:
                    self.ws.close()
                except Exception: pass
            print("WebSocket closed.")

# --- OpenWakeWord Setup ---

def _fatal(msg):
    """Abort with a visible message."""
    print(f"\nFATAL: {msg}\n", file=sys.stderr, flush=True)
    raise SystemExit(msg)

def download_oww_support_models():
    for holder_name, holder in (("openwakeword.utils", getattr(openwakeword, "utils", None)),
                                ("openwakeword", openwakeword)):
        fn = getattr(holder, "download_models", None) if holder is not None else None
        if callable(fn):
            print(f"Downloading OpenWakeWord support models via "
                  f"{holder_name}.download_models() (skipped if already present) ...")
            try:
                fn()
            except Exception as e:
                print(f"OpenWakeWord: support-model download failed ({e}) — "
                      f"continuing with whatever is already on disk.")
            return

    res_dir = os.path.join(os.path.dirname(os.path.abspath(openwakeword.__file__)),
                           "resources", "models")
    needed = ["melspectrogram.onnx", "embedding_model.onnx"]
    try:
        # Builds without vad_threshold have no VAD, so no Silero model to look for
        if "vad_threshold" in inspect.signature(OWWModel.__init__).parameters:
            needed.append("silero_vad.onnx")
    except (TypeError, ValueError):
        pass
    missing = [n for n in needed if not os.path.exists(os.path.join(res_dir, n))]
    if missing:
        print(f"OpenWakeWord: this build exposes no download_models(), and these "
              f"support models are MISSING from {res_dir}: {', '.join(missing)}")
    else:
        print("OpenWakeWord: this build exposes no download_models() — "
              "support models found, nothing to fetch.")

def oww_model_kwargs():
    try:
        params = inspect.signature(OWWModel.__init__).parameters
    except (TypeError, ValueError):
        params = {}

    kwargs = {}
    if "wakeword_models" in params:
        kwargs["wakeword_models"] = [WAKE_MODEL_PATH]
    elif "wakeword_model_paths" in params:
        kwargs["wakeword_model_paths"] = [WAKE_MODEL_PATH]
    else:
        # Unknown signature — the first positional arg is the model list in
        # every released version, so fall back to the new name and let the
        # diagnostic in load_oww_model() report it if that's wrong.
        kwargs["wakeword_models"] = [WAKE_MODEL_PATH]

    if "inference_framework" in params:
        kwargs["inference_framework"] = "onnx"
    if "vad_threshold" in params:
        kwargs["vad_threshold"] = OWW_VAD_THRESHOLD
    else:
        print("OpenWakeWord: this build has no vad_threshold — running without "
              "the VAD gate. Raise OWW_THRESHOLD if false wakes increase.")

    return kwargs

def oww_reset(model):
    """reset() clears OWW's ~1.4 s sliding window. Older builds don't have it;
    without it a detection can re-fire on the following frames."""
    fn = getattr(model, "reset", None)
    if callable(fn):
        fn()

def load_oww_model():
    """Load the custom wake-word model. Returns (model, wake_key)."""
    download_oww_support_models()

    if not os.path.exists(WAKE_MODEL_PATH):
        _fatal(f"Wake word model not found: {WAKE_MODEL_PATH}\n"
               f"Copy {WAKE_MODEL_FILE} into the same directory as this script.")

    print(f"Loading OpenWakeWord model: {WAKE_MODEL_FILE} ...")
    kwargs = oww_model_kwargs()
    print(f"Model() arguments for this build: {sorted(kwargs)}")
    try:
        oww = OWWModel(**kwargs)
    except Exception as e:
        res_dir = os.path.join(os.path.dirname(os.path.abspath(openwakeword.__file__)),
                               "resources", "models")
        present = sorted(os.listdir(res_dir)) if os.path.isdir(res_dir) else "(directory not found)"
        try:
            sig = str(inspect.signature(OWWModel.__init__))
        except (TypeError, ValueError):
            sig = "(could not introspect)"
        _fatal(f"Failed to load the OpenWakeWord model: {e}\n"
               f"openwakeword package: {openwakeword.__file__}\n"
               f"Model.__init__ signature: {sig}\n"
               f"Arguments passed: {sorted(kwargs)}\n"
               f"Support models in {res_dir}: {present}")

    models_attr = getattr(oww, "models", None)
    if models_attr:
        wake_key = list(models_attr.keys())[0]
    else:
        wake_key = os.path.splitext(WAKE_MODEL_FILE)[0]
    print(f"Model key: {wake_key}")
    return oww, wake_key

# --- Idle CPU (quiet-room gate and health line) ---

def frame_rms(samples):
    """RMS level of an int16 frame, as a float."""
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))

class WakeGate:
    """Keeps the wake-word engine asleep while the room is quiet."""

    def __init__(self, oww, wake_key, background_rms):
        self.oww = oww
        self.wake_key = wake_key
        self.threshold = (max(GATE_MIN_RMS, GATE_FLOOR_FACTOR * background_rms)
                          if GATE_RMS is None else float(GATE_RMS))
        self.preroll = collections.deque(maxlen=max(1, GATE_PREROLL_FRAMES))
        self.awake = self.threshold <= 0      # a threshold of 0 disables the gate
        self.quiet_for = 0.0
        self.frames = 0
        self.scored_frames = 0

        if self.threshold <= 0:
            print("Quiet-room gate: off — the wake-word engine runs on every frame.")
        else:
            print(f"Quiet-room gate: RMS {self.threshold:.0f} "
                  f"(background {background_rms:.0f}) — the wake-word engine sleeps "
                  f"while the room is quiet")

    def score(self, samples):
        """Highest wake-word score for this frame; 0.0 while the engine sleeps."""
        self.frames += 1
        loud = frame_rms(samples) >= self.threshold

        if not self.awake:
            self.preroll.append(samples)
            if not loud:
                return 0.0
            # Sound in a quiet room: wake the engine, and let it hear the moments
            # just before so a wake word already under way isn't cut in half.
            # reset() first — openwakeword must never stitch together audio from
            # either side of a gap.
            self.awake, self.quiet_for = True, 0.0
            oww_reset(self.oww)
            backlog = list(self.preroll)
            self.preroll.clear()
            return max(self._predict(frame) for frame in backlog)

        score = self._predict(samples)
        if loud or score >= GATE_KEEP_AWAKE_SCORE:
            self.quiet_for = 0.0
        else:
            self.quiet_for += OWW_CHUNK / OWW_RATE
            if self.threshold > 0 and self.quiet_for >= GATE_HANG_SECONDS:
                self.awake = False
                self.preroll.clear()
        return score

    def _predict(self, samples):
        self.scored_frames += 1
        return self.oww.predict(samples).get(self.wake_key, 0.0)

    def rearm(self):
        """Call after a session: forget buffered audio and go back to sleep."""
        oww_reset(self.oww)
        self.preroll.clear()
        self.awake = self.threshold <= 0
        self.quiet_for = 0.0

    def take_active_fraction(self):
        """Share of frames the engine actually scored since the last call."""
        if self.frames == 0:
            return None
        fraction = self.scored_frames / self.frames
        self.frames = self.scored_frames = 0
        return fraction

def cpu_temperature():
    """Pi SoC temperature in °C, or None if it can't be read."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None

def throttled_flags():
    """`vcgencmd get_throttled` value, e.g. "0x0". None if unavailable.

    Anything other than 0x0 means the firmware has had to throttle the CPU or
    has logged an undervoltage event.
    """
    try:
        result = subprocess.run(["vcgencmd", "get_throttled"],
                                capture_output=True, text=True, timeout=2)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or "=" not in result.stdout:
        return None
    return result.stdout.strip().split("=", 1)[1]

class Health:
    """Prints one line a minute: temperature, CPU use and how busy the gate is."""

    def __init__(self):
        self.last_wall = time.time()
        self.last_cpu = time.process_time()

    def maybe_report(self, gate):
        if STATS_INTERVAL <= 0:
            return
        now = time.time()
        elapsed = now - self.last_wall
        if elapsed < STATS_INTERVAL:
            return

        cpu = time.process_time()
        parts = []
        temperature = cpu_temperature()
        if temperature is not None:
            parts.append(f"CPU {temperature:.0f}°C")
        parts.append(f"process CPU {100 * (cpu - self.last_cpu) / elapsed:.0f}% of one core")
        fraction = gate.take_active_fraction()
        if fraction is not None:
            parts.append(f"wake-word engine active {100 * fraction:.0f}% of the time")
        flags = throttled_flags()
        if flags is not None:
            parts.append(f"throttled={flags}")
        print("Health: " + ", ".join(parts))

        self.last_wall, self.last_cpu = now, cpu

def resample_16k_to_24k(samples_16k):
    """Linear-interpolate 16 kHz PCM up to the 24 kHz Realtime session rate."""

    if len(samples_16k) < 2:
        return np.array([], dtype=np.int16)
    num_out = int(len(samples_16k) * RATE / OWW_RATE)
    indices = np.linspace(0, len(samples_16k) - 1, num_out)
    return np.interp(
        indices, np.arange(len(samples_16k)), samples_16k.astype(np.float64)
    ).astype(np.int16)

class AudioIO:
    def __init__(self, p_instance, oww, wake_key):
        self.audio_buffer = bytearray()
        self.mic_queue: "queue.Queue[bytes]" = queue.Queue()
        self._stop_event = threading.Event()
        self.p = p_instance

        # Two-mode mic architecture
        self.oww = oww               # shared OpenWakeWord Model (also used by the idle loop)
        self.wake_key = wake_key     # key OWW uses for this model in its prediction dict
        self.mode = 'active'         # 'guarded' or 'active'
        self.mode_lock = threading.Lock()

        # Resampling and frame accumulation buffers for guarded mode
        self._resample_buf_16k = np.array([], dtype=np.int16)
        self._oww_buf = np.array([], dtype=np.int16)

        # Set by set_mode() (websocket thread), acted on by _process_guarded_audio()
        # (mic thread) so only one thread ever touches the OWW model during a session
        self._oww_needs_reset = False

        # Callback for wake-word detection during session
        self.on_wake_word = None

    def _mic_cb(self, in_data, frame_count, time_info, status):
        self.mic_queue.put(in_data)
        return (None, pyaudio.paContinue)

    def _spk_cb(self, in_data, frame_count, time_info, status):
        needed = frame_count * 2
        chunk = self.audio_buffer[:needed]
        self.audio_buffer = self.audio_buffer[needed:]

        if len(chunk) < needed:
            # Pad with silence if buffer is empty
            chunk += b"\x00" * (needed - len(chunk))

        return (bytes(chunk), pyaudio.paContinue)

    def clear_buffer(self):
        """Instantly clears the audio buffer to stop AI speech."""
        self.audio_buffer = bytearray()

    def set_mode(self, mode):
        """Thread-safe mode switch between 'guarded' and 'active'."""
        with self.mode_lock:
            old_mode = self.mode
            self.mode = mode

        if mode == 'guarded' and old_mode == 'active':
            self._oww_needs_reset = True
            print(f"Audio mode: {old_mode} -> {mode}")

        elif mode == 'active' and old_mode == 'guarded':
            while not self.mic_queue.empty():
                try:
                    self.mic_queue.get_nowait()
                except queue.Empty:
                    break
            print(f"Audio mode: {old_mode} -> {mode}")

    def _process_guarded_audio(self, raw_24k_bytes):

        if self._oww_needs_reset:
            self._oww_needs_reset = False
            self._resample_buf_16k = np.array([], dtype=np.int16)
            self._oww_buf = np.array([], dtype=np.int16)
            oww_reset(self.oww)

        # Convert bytes to numpy int16 array
        samples_24k = np.frombuffer(raw_24k_bytes, dtype=np.int16)

        # Resample from 24kHz to 16kHz using linear interpolation
        num_out = int(len(samples_24k) * 16000 / 24000)
        if num_out == 0:
            return
        indices = np.linspace(0, len(samples_24k) - 1, num_out)
        samples_16k = np.interp(
            indices, np.arange(len(samples_24k)), samples_24k.astype(np.float64)
        ).astype(np.int16)

        # Accumulate resampled audio
        self._oww_buf = np.concatenate([self._oww_buf, samples_16k])

        # Drain OWW-sized frames (1280 samples = 80 ms) from the buffer
        while len(self._oww_buf) >= OWW_CHUNK:
            oww_frame = self._oww_buf[:OWW_CHUNK]
            self._oww_buf = self._oww_buf[OWW_CHUNK:]

            score = self.oww.predict(oww_frame).get(self.wake_key, 0.0)

            if score >= OWW_THRESHOLD:
                print(f"Wake word detected during session (guarded mode, confidence: {score:.2f})")
                oww_reset(self.oww)
                if self.on_wake_word:
                    self.on_wake_word()

    def start_streams(self):
        self.in_stream = self.p.open(
            format=FORMAT, channels=1, rate=RATE,
            input=True, frames_per_buffer=CHUNK_SIZE, stream_callback=self._mic_cb,
        )
        self.out_stream = self.p.open(
            format=FORMAT, channels=1, rate=RATE,
            output=True, frames_per_buffer=CHUNK_SIZE, stream_callback=self._spk_cb
        )
        self.in_stream.start_stream()
        self.out_stream.start_stream()

    def stop_streams(self):
        self._stop_event.set()
        if hasattr(self, 'in_stream'):
            self.in_stream.stop_stream()
            self.in_stream.close()
        if hasattr(self, 'out_stream'):
            self.out_stream.stop_stream()
            self.out_stream.close()

    def send_mic(self, sock):
        while not self._stop_event.is_set():
            try:
                data = self.mic_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            with self.mode_lock:
                current_mode = self.mode

            if current_mode == 'active':
                # Send audio to Realtime API (normal behavior)
                enc = base64.b64encode(data).decode()
                sock.send({"type": "input_audio_buffer.append", "audio": enc})
            else:
                # Guarded mode: run wake-word detection locally
                self._process_guarded_audio(data)

    def push_back(self, audio_bytes):
        self.audio_buffer.extend(audio_bytes)

class Realtime:
    def __init__(self, api_key, ws_url, p_instance, oww, wake_key):
        self.sock = Socket(api_key, ws_url)
        self.audio = AudioIO(p_instance, oww, wake_key)
        self.sent_update = False
        self._stop_event = threading.Event()
        self.user_speaking = False
        self.ai_responding = False
        self.tools_in_flight = 0
        self.exit_requested = False
        self.exit_requested_at = 0.0
        self.pending_active_switch = False
        self.interaction_mode = INTERACTION_MODE  # runtime-mutable; starts from top-of-file default
        self.dismissed_silently = False

    def connect(self):
        self.sock.on_msg = self.on_msg
        self.sock.connect()

    def start_audio(self, bridge_pcm16_16k=None):
        global active_session
        self.audio.on_wake_word = self.handle_wake_word_interrupt
        self.audio.set_mode('active')  # User just said the wake word, expect speech
        self.audio.start_streams()
        deadline = time.time() + 0.5
        while not self.sent_update and time.time() < deadline:
            time.sleep(0.01)

        if bridge_pcm16_16k:
            self.send_bridge_audio(bridge_pcm16_16k)

        threading.Thread(target=self.audio.send_mic, args=(self.sock,), daemon=True).start()
        with active_session_lock:
            active_session = self

    def send_bridge_audio(self, pcm16_16k_bytes):
        """Upsample and send the handoff bridge audio ahead of the live mic."""
        try:
            samples_16k = np.frombuffer(pcm16_16k_bytes, dtype=np.int16)
            samples_24k = resample_16k_to_24k(samples_16k)
            if not len(samples_24k):
                return
            enc = base64.b64encode(samples_24k.tobytes()).decode()
            self.sock.send({"type": "input_audio_buffer.append", "audio": enc})
            print(f"Bridged {len(samples_16k) / OWW_RATE:.2f}s of audio "
                  f"captured during session startup")
        except Exception as e:
            print(f"Failed to send bridge audio: {e}")

    def handle_wake_word_interrupt(self):
        """Called when wake word is detected during an active session (guarded mode)."""
        print(f"{WAKE_LABEL} detected - interrupting AI and switching to active mode")
        set_led_on()

        # Clear any playing AI audio
        self.audio.clear_buffer()

        # Cancel any in-progress response from the API
        self.sock.send({"type": "response.cancel"})

        # Clear OpenAI's input audio buffer (discard stale audio from before the wake word)
        self.sock.send({"type": "input_audio_buffer.clear"})

        # Switch to active mode - start sending mic audio to Realtime API
        self.audio.set_mode('active')

    def handle_exit_word(self):
        """Called when the model invokes the exit_the_program tool."""
        print("Exit requested by the exit_the_program tool - flagging for shutdown")
        self.exit_requested = True
        self.exit_requested_at = time.time()

    def silently_dismiss(self, reason="unknown"):
        """Mark this session for silent close (model called dismiss_false_wake)."""
        print(f"Silent dismissal — reason: {reason}")
        if not self.dismissed_silently:
            self.audio.clear_buffer()
            try:
                self.sock.send({"type": "response.cancel"})
            except Exception as e:
                print(f"response.cancel during dismissal failed: {e}")
        self.dismissed_silently = True

    def on_msg(self, msg):
        typ = msg.get("type")

        # Print interesting events, ignore frequent deltas
        # (errors are printed by their own handler below)
        if typ not in ("response.output_audio.delta", "response.output_audio_transcript.delta", "rate_limits.updated", "error"):
            print(f"Event: {typ}")

        if typ == "response.output_item.added":
            item = msg.get("item") or {}
            if (item.get("type") == "function_call"
                    and item.get("name") == "dismiss_false_wake"):
                self.silently_dismiss(reason="model called dismiss_false_wake")
                return

        if typ == "session.created" and not self.sent_update:
            self.sent_update = True
            print("Session created. Sending session update (Server VAD)...")
            self._send_session_update()

        # --- Speech events ---

        elif typ == "input_audio_buffer.speech_started":
            with self.audio.mode_lock:
                current_mode = self.audio.mode
            if current_mode == 'active':
                print("User started speaking (active mode)")
                self.user_speaking = True
                if len(self.audio.audio_buffer) > 0:
                    self.audio.clear_buffer()
                    self.sock.send({"type": "response.cancel"})
            else:
                print("Speech detected but ignoring (guarded mode)")

        elif typ == "input_audio_buffer.speech_stopped":
            with self.audio.mode_lock:
                current_mode = self.audio.mode
            if current_mode == 'active':
                print("User stopped speaking")
                self.user_speaking = False

        elif typ == "input_audio_buffer.timeout_triggered":
            print("Idle timeout triggered by server VAD")

        # --- Response lifecycle for mode switching ---
        elif typ == "response.created":
            self.ai_responding = True
            if self.interaction_mode != "conversational":
                self.audio.set_mode('guarded')
                self.sock.send({"type": "input_audio_buffer.clear"})
                threading.Thread(target=set_alsa_capture, args=(33,), daemon=True).start()

        elif typ == "response.done":
            response_obj = msg.get("response", {})
            status = response_obj.get("status", "")
            output = response_obj.get("output", [])

            has_function_call = any(
                item.get("type") == "function_call" for item in output
            )

            print(f"Response complete (status={status}, has_tool_call={has_function_call})")

            if status == "completed" and not has_function_call:
                self.ai_responding = False
                if self.interaction_mode == "normal":
                    self.pending_active_switch = True
                threading.Thread(target=set_alsa_capture, args=(42,), daemon=True).start()
            elif status == "cancelled":
                self.ai_responding = False
                threading.Thread(target=set_alsa_capture, args=(42,), daemon=True).start()
            else:
                self.ai_responding = False

        # --- Audio Playback ---
        elif typ == "response.output_audio.delta":
            data = base64.b64decode(msg["delta"])
            self.audio.push_back(data)

        elif typ == "response.function_call_arguments.done":
            call_id = msg.get("call_id")
            func_name = msg.get("name")
            raw_args = msg.get("arguments", "{}")
            print(f"Tool call: {func_name}  args={raw_args}")
            threading.Thread(
                target=self.execute_tool,
                args=(call_id, func_name, raw_args),
                daemon=True
            ).start()

        elif typ == "error":
            error = msg.get("error") or {}
            # A cancel that arrives after the response already finished — harmless
            if error.get("code") != "response_cancel_not_active":
                print(f"Server error: {error}")

    def execute_tool(self, call_id, func_name, raw_args):
        """Executes a tool function and sends the result back to the Realtime API."""
        if func_name == "dismiss_false_wake":
            self.silently_dismiss(reason="model called dismiss_false_wake (late path)")
            return

        if not call_id:
            print("Tool call received with no call_id, skipping.")
            return

        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            args = {}

        # Tracked so the session inactivity timeout is suppressed while a
        # tool is still executing (a web search can take several seconds).
        self.tools_in_flight += 1
        try:
            if func_name == "get_current_time":
                output = get_current_time()
            elif func_name == "get_current_weather":
                output = get_current_weather(args.get("location", None))
            elif func_name == "get_weather_forecast":
                output = get_weather_forecast(args.get("location"), args.get("date"))
            elif func_name == "search_web":
                output = search_web(args.get("query", ""))
            elif func_name == "set_interaction_mode":
                output = self._apply_mode_switch(args.get("mode"))
            elif func_name == "set_timer":
                output = self.set_timer(args.get("label", "timer"), args.get("duration_seconds"))
            elif func_name == "cancel_timer":
                output = self._cancel_timer(args.get("label"))
            elif func_name == "get_timer_status":
                output = self.get_timer_status(args.get("label"))
            elif func_name == "exit_the_program":
                self.handle_exit_word()
                output = "Goodbye."
            elif func_name == "set_volume":
                global current_volume
                level = args.get("level")
                direction = args.get("direction")
                if level is not None:
                    new_vol = max(10, min(100, int(level)))
                elif direction == "up":
                    new_vol = min(100, current_volume + 10)
                elif direction == "down":
                    new_vol = max(10, current_volume - 10)
                else:
                    new_vol = current_volume
                success = set_alsa_playback(new_vol)
                if success:
                    current_volume = new_vol
                    output = f"Volume set to {new_vol}%."
                else:
                    output = "Failed to adjust volume. The amixer command returned an error."
            else:
                output = f"Unknown function: {func_name}"
        except Exception as e:
            output = f"An error occurred while executing {func_name}: {str(e)}"
        finally:
            self.tools_in_flight -= 1

        print(f"Tool result: {output}")

        self.sock.send({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": output
            }
        })
        self.sock.send({"type": "response.create"})

    def _send_session_update(self):
        """Send (or re-send) session.update to OpenAI with the current interaction_mode settings.
        Called at session creation and again whenever the mode is switched at runtime."""
        if self.interaction_mode == "conversational":
            instructions = DAVINCI_CONVERSATIONAL
        elif self.interaction_mode == "strict":
            instructions = DAVINCI_STRICT
        else:
            instructions = DAVINCI

        self.sock.send({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "reasoning": {"effort": "low"},
                "instructions": instructions,
                "tools": [
                    {
                        "type": "function",
                        "name": "get_current_time",
                        "description": "Returns the current date and time.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                            "additionalProperties": False
                        }
                    },
                    {
                        "type": "function",
                        "name": "get_current_weather",
                        "description": (
                            "Gets the current weather conditions for a location using the Open-Meteo API. "
                            "Use this for present conditions only — use get_weather_forecast for future days. "
                            "If the user did not mention a specific location, call this tool immediately "
                            "with location=null — do NOT ask the user to confirm or name a location first."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": ["string", "null"],
                                    "description": (
                                        "The city or location name to get weather for. "
                                        "Put a state or country after a comma when one was "
                                        "given, e.g. 'Springfield, Illinois' or 'Paris, France'. "
                                        f"Pass null to automatically use the default ({DEFAULT_LOCATION_DISPLAY}) "
                                        "without asking the user for confirmation."
                                    )
                                }
                            },
                            "required": ["location"],
                            "additionalProperties": False
                        }
                    },
                    {
                        "type": "function",
                        "name": "get_weather_forecast",
                        "description": (
                            "Returns the daily weather forecast (conditions, high, low, wind) for a "
                            "specific future day using the Open-Meteo API. "
                            f"Supports up to {FORECAST_MAX_DAYS} days ahead. "
                            "Use this for any question about tomorrow's weather or a future day. "
                            "If the user did not mention a specific location, call this tool immediately "
                            "with location=null — do NOT ask the user to confirm or name a location first."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": ["string", "null"],
                                    "description": (
                                        "The city or location name to get the forecast for. "
                                        "Put a state or country after a comma when one was "
                                        "given, e.g. 'Springfield, Illinois' or 'Paris, France'. "
                                        f"Pass null to automatically use the default ({DEFAULT_LOCATION_DISPLAY}) "
                                        "without asking the user for confirmation."
                                    )
                                },
                                "date": {
                                    "type": ["string", "null"],
                                    "description": (
                                        "The day to forecast. Accepts: 'tomorrow', a weekday name "
                                        "('Monday'…'Sunday'), or an ISO date string 'YYYY-MM-DD'. "
                                        "Pass null to default to tomorrow."
                                    )
                                }
                            },
                            "required": ["location", "date"],
                            "additionalProperties": False
                        }
                    },
                    {
                        "type": "function",
                        "name": "search_web",
                        "description": (
                            "Searches the web for current, up-to-date information and "
                            "returns a concise answer. Use this for any question about "
                            "events, news, sports, schedules, scores, prices, releases, "
                            "or facts that may have changed after your training data "
                            "ends — never guess or say you don't know without trying "
                            "this tool first. Do not use it for weather (use the "
                            "weather tools) or timeless facts you already know. "
                            "Say a brief acknowledgment like 'Let me check on that' or "
			    "'I'll look that up' before calling, "
                            "since the search takes a few seconds."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": (
                                        "The question to answer, phrased self-contained: "
                                        "resolve pronouns and conversation context so the "
                                        "question makes sense on its own (e.g. 'What teams "
                                        "play in the next FIFA World Cup match?')."
                                    )
                                }
                            },
                            "required": ["query"],
                            "additionalProperties": False
                        }
                    },
                    {
                        "type": "function",
                        "name": "set_interaction_mode",
                        "description": (
                            "Switches the interaction mode between 'normal', 'conversational', "
                            "and 'strict'. "
                            "Use 'normal' for the standard wake-word-guarded mode (free speech "
                            "between turns, wake word interrupts AI). "
                            "Use 'conversational' to allow the user to interrupt DaVinci while "
                            "speaking. "
                            "Use 'strict' to require the wake word before EVERY user turn, "
                            "including follow-ups; the session and history stay alive. "
                            "Important: 'strict mode', 'wake-word only mode', 'wake word only', "
                            "and 'only respond to the wake word' all refer to the SAME mode — "
                            "pass mode='strict' in every case."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "mode": {
                                    "type": "string",
                                    "enum": ["normal", "conversational", "strict"],
                                    "description": "The interaction mode to switch to."
                                }
                            },
                            "required": ["mode"],
                            "additionalProperties": False
                        }
                    },
                    {
                        "type": "function",
                        "name": "set_timer",
                        "description": (
                            "Sets a named countdown timer. If a timer with the same label is "
                            "already running it is cancelled and replaced with the new one."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "label": {
                                    "type": "string",
                                    "description": (
                                        "A short name for the timer, e.g. 'pasta', 'sauce', or 'timer'. "
                                        "Used to identify it when querying or cancelling."
                                    )
                                },
                                "duration_seconds": {
                                    "type": "integer",
                                    "description": "How many seconds to count down."
                                }
                            },
                            "required": ["label", "duration_seconds"],
                            "additionalProperties": False
                        }
                    },
                    {
                        "type": "function",
                        "name": "cancel_timer",
                        "description": (
                            "Cancels a running timer. If exactly one timer is active, "
                            "call this with no label to cancel it without asking. "
                            "Only ask the user which timer to cancel when two or more are active."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "label": {
                                    "type": "string",
                                    "description": (
                                        "The label of the timer to cancel. Omit to auto-cancel "
                                        "when only one timer is running."
                                    )
                                }
                            },
                            "required": [],
                            "additionalProperties": False
                        }
                    },
                    {
                        "type": "function",
                        "name": "get_timer_status",
                        "description": (
                            "Returns the time remaining on a specific timer or on all active timers."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "label": {
                                    "type": ["string", "null"],
                                    "description": (
                                        "The label of the timer to check, or null to return "
                                        "the status of all active timers."
                                    )
                                }
                            },
                            "required": ["label"],
                            "additionalProperties": False
                        }
                    },
                    {
                        "type": "function",
                        "name": "set_volume",
                        "description": (
                            "Adjusts the speaker playback volume. Use this when the user asks to "
                            "change, increase, decrease, raise, lower, or set the volume. "
                            "Provide either a specific level (10-100) OR a direction for relative "
                            "adjustment, but not both. Each relative step changes volume by 10 "
                            "percentage points. Volume cannot go below 10 percent."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "level": {
                                    "type": "integer",
                                    "description": (
                                        "Absolute volume level from 10 to 100. Use this when the user "
                                        "requests a specific volume (e.g., 'set volume to 50 percent')."
                                    )
                                },
                                "direction": {
                                    "type": "string",
                                    "enum": ["up", "down"],
                                    "description": (
                                        "Relative volume adjustment direction. 'up' increases by 10 percent, "
                                        "'down' decreases by 10 percent. Use this for requests like "
                                        "'louder', 'quieter', 'turn it up', 'turn it down'."
                                    )
                                }
                            },
                            "required": [],
                            "additionalProperties": False
                        }
                    },
                    {
                        "type": "function",
                        "name": "dismiss_false_wake",
                        "description": (
                            "Call this only when you are confident nobody is talking to "
                            "you — the audio is clearly dialogue from a TV show, radio or "
                            "podcast, other people talking to each other, or just noise or "
                            "mumbling with no recognizable words. Do not call it if the "
                            "audio contains anything that sounds like a question, command "
                            "or request, even a short, informal or partly cut-off one, or "
                            "if it begins with your name, DaVinci. When unsure, respond "
                            "instead. When you call this tool, produce no text and no audio output, "
                            "only the function call itself. Do not apologize, do not say "
                            "'sorry, I didn't catch that' Instead, just call the tool and stay silent."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                            "additionalProperties": False
                        }
                    },
                    {
                        "type": "function",
                        "name": "exit_the_program",
                        "description": (
                            "Call this when the user asks to exit, quit, shut down, close, "
                            "or stop the program — for example 'exit the program', 'shut "
                            "down', 'quit', or 'goodbye, shut yourself off'. Say a brief "
                            "goodbye, then call this tool. Do not call it for 'stop "
                            "talking', 'never mind', or 'cancel that'. Those and similar " 
                            "phrases just end the current turn, not the program."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                            "additionalProperties": False
                        }
                    }
                ],
                "tool_choice": "auto",
                "audio": {
                    "input": {
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.80 if self.interaction_mode == "conversational" else 0.88,
                            "silence_duration_ms": 550 if self.interaction_mode == "conversational" else 700,
                            "prefix_padding_ms": 180,
                            "idle_timeout_ms": 15000
                        }
                    },
                    "output": {
                        "voice": "cedar"
                    }
                }
            }
        })

    def _apply_mode_switch(self, new_mode):
        """Switch self.interaction_mode at runtime and push updated settings to OpenAI.
        Returns a confirmation string that DaVinci will speak to the user."""
        global INTERACTION_MODE
        if new_mode not in ("normal", "conversational", "strict"):
            return f"Invalid mode '{new_mode}'. Please choose 'normal', 'conversational', or 'strict'."

        if new_mode == self.interaction_mode:
            return f"Already in {new_mode} mode — no change needed."

        old_mode = self.interaction_mode
        self.interaction_mode = new_mode
        INTERACTION_MODE = new_mode
        print(f"Interaction mode: {old_mode} -> {new_mode}")

        self._send_session_update()

        if new_mode == "conversational":
            self.audio.set_mode('active')

        labels = {
            "normal": "normal mode",
            "conversational": "conversational mode",
            "strict": "strict mode",
        }
        return f"Switched from {labels[old_mode]} to {labels[new_mode]}."

    # --- Timer methods ---

    def set_timer(self, label, duration_seconds):
        """Create (or replace) a named countdown timer."""
        try:
            duration_seconds = int(duration_seconds)
        except (TypeError, ValueError):
            return "Invalid duration. Please provide a number of seconds."
        if duration_seconds <= 0:
            return "Duration must be greater than zero."

        with timers_lock:
            # Cancel existing timer with the same label before replacing
            if label in timers:
                timers[label]["timer"].cancel()
                print(f"Timer '{label}' replaced.")

            t = threading.Timer(duration_seconds, fire_timer, args=[label])
            timers[label] = {
                "timer": t,
                "start": time.time(),
                "duration": float(duration_seconds),
            }
            t.start()

        mins, secs = divmod(duration_seconds, 60)
        hrs, mins = divmod(mins, 60)
        parts = []
        if hrs:
            parts.append(f"{hrs} hour{'s' if hrs != 1 else ''}")
        if mins:
            parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
        if secs:
            parts.append(f"{secs} second{'s' if secs != 1 else ''}")
        duration_str = " and ".join(parts) if parts else "0 seconds"

        print(f"Timer '{label}' set for {duration_str}.")
        return f"Timer '{label}' set for {duration_str}."

    def _cancel_timer(self, label):
        """Cancel a running timer by label. If label is omitted and exactly one
        timer is running, cancel that one without asking."""
        with timers_lock:
            if not label:
                if len(timers) == 1:
                    label = next(iter(timers))
                elif len(timers) == 0:
                    return "There are no timers currently running."
                else:
                    names = ", ".join(f"'{n}'" for n in timers)
                    return f"Multiple timers are running ({names}). Which one should I cancel?"
            entry = timers.pop(label, None)
        if entry:
            entry["timer"].cancel()
            print(f"Timer '{label}' cancelled.")
            return f"Timer '{label}' cancelled."
        return f"No timer named '{label}' is currently running."

    def get_timer_status(self, label):
        """Return remaining time for one or all active timers."""
        def _fmt_remaining(entry):
            elapsed = time.time() - entry["start"]
            remaining = max(0.0, entry["duration"] - elapsed)
            mins, secs = divmod(int(remaining), 60)
            hrs, mins = divmod(mins, 60)
            parts = []
            if hrs:
                parts.append(f"{hrs} hour{'s' if hrs != 1 else ''}")
            if mins:
                parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
            if secs or not parts:
                parts.append(f"{secs} second{'s' if secs != 1 else ''}")
            return " and ".join(parts)

        with timers_lock:
            snapshot = dict(timers)

        if label:
            if label not in snapshot:
                return f"No timer named '{label}' is currently running."
            return f"{_fmt_remaining(snapshot[label])} remaining on the '{label}' timer."

        if not snapshot:
            return "No timers are currently running."
        lines = [f"'{lbl}': {_fmt_remaining(entry)} remaining"
                 for lbl, entry in snapshot.items()]
        return "Active timers — " + "; ".join(lines) + "."

    def stop(self):
        global active_session
        self._stop_event.set()
        self.audio.stop_streams()
        self.sock.close()
        with active_session_lock:
            if active_session is self:
                active_session = None
        print("Realtime session stopped.")
        print("\nListening for wake word...")

def main():
    url = "wss://api.openai.com/v1/realtime?model=gpt-realtime-2" # or change to preferred model
    oww, pa = None, None
    audio_stream = None


    # --- Set ALSA volume levels at startup ---
    # The speakerphone's card index and control names are detected automatically.
    init_alsa_mixer()
    set_alsa_playback(current_volume)    # safe speaker level that won't over-drive the mic
    set_alsa_capture(48)                 # sensible baseline capture gain

    # Check the network in the background; raise the setup hotspot if needed
    wifi = WifiManager()
    wifi.start()
    threading.Thread(target=when_online, args=(wifi,), daemon=True).start()

    try:

        # Initialize OpenWakeWord (Wake Word)
        oww, wake_key = load_oww_model()

        pa = pyaudio.PyAudio()

        global pa_instance
        pa_instance = pa

        # (The default weather location is resolved by when_online().)

        audio_stream = pa.open(
            rate=OWW_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=OWW_CHUNK,
        )

        # Two seconds of room noise set the quiet-room gate's threshold.
        floor = [frame_rms(np.frombuffer(audio_stream.read(OWW_CHUNK, exception_on_overflow=False),
                                         dtype=np.int16))
                 for _ in range(25)]
        background_rms = float(np.median(floor))
        print(f"Microphone background level: RMS {background_rms:.0f} "
              f"(0 means the mic is muted or not delivering audio)")

        gate = WakeGate(oww, wake_key, background_rms)
        health = Health()

        print(f"Listening for wake word ('{WAKE_LABEL}')...")

        while True:
            try:
                health.maybe_report(gate)

                # Wi-Fi setup messages (hotspot up, connected, failed)
                announcement = wifi.take_announcement()
                if announcement:
                    speak_setup_message(announcement, wifi, audio_stream, gate)
                    continue

                # Read audio from the already-open stream
                pcm = audio_stream.read(OWW_CHUNK, exception_on_overflow=False)

                # Score the 80 ms frame — the gate skips OpenWakeWord while the room is quiet
                # (.copy() — np.frombuffer returns a read-only view of the PyAudio buffer)
                samples = np.frombuffer(pcm, dtype=np.int16).copy()
                score = gate.score(samples)

                if score >= OWW_THRESHOLD:
                    print(f"\nWake word detected  (confidence: {score:.2f})")

                    # No internet: explain how to set up Wi-Fi instead
                    if wifi.in_setup():
                        speak_setup_message("setup", wifi, audio_stream, gate)
                        continue

                    set_led_on()

                    oww_reset(oww)

                    # Share the OWW model with the session for in-session
                    # (guarded mode) wake-word detection
                    rt_session = Realtime(OPENAI_API_KEY, url, pa, oww, wake_key)

                    try:
                        # 1. Connect on a background thread while this thread keeps
                        #    reading the mic. Closing the stream first and connecting
                        #    afterwards left the mic dead for the whole handshake, so
                        #    the start of the user's request was never captured.
                        connect_error = []

                        def _connect():
                            try:
                                rt_session.connect()
                            except Exception as exc:
                                connect_error.append(exc)

                        connect_thread = threading.Thread(target=_connect, daemon=True)
                        connect_thread.start()

                        bridge_chunks = []
                        bridge_samples = 0
                        max_bridge_samples = OWW_RATE * BRIDGE_MAX_SECONDS
                        while connect_thread.is_alive() and bridge_samples < max_bridge_samples:
                            try:
                                bridge_chunks.append(
                                    audio_stream.read(OWW_CHUNK, exception_on_overflow=False)
                                )
                                bridge_samples += OWW_CHUNK
                            except Exception as exc:
                                print(f"Bridge capture stopped: {exc}")
                                break

                        connect_thread.join(timeout=10)
                        if connect_error:
                            raise connect_error[0]
                        if connect_thread.is_alive():
                            raise TimeoutError("WebSocket connect did not complete in time")

                        # 2. Hand the mic over: close the wake-word stream, then open
                        #    the session's 24 kHz streams and replay the bridge audio.
                        if audio_stream.is_active():
                            audio_stream.stop_stream()
                        audio_stream.close()
                        audio_stream = None

                        rt_session.start_audio(b"".join(bridge_chunks))
                        last_activity_time = time.time()
                        prev_busy = False
                        exit_audio_idle_since = None

                        while True:
                            # Check activity based on Server VAD events and Audio Buffer
                            ai_is_talking  = len(rt_session.audio.audio_buffer) > 0
                            user_is_talking = rt_session.user_speaking
                            tool_running    = rt_session.tools_in_flight > 0

                            # A running tool counts as activity. Without this the
                            # 3-second inactivity timeout closes the session while a
                            # web search is still in flight, and the answer is lost.
                            if user_is_talking or ai_is_talking or tool_running:
                                last_activity_time = time.time()

                            # --- LED state machine ---
                            # Pulse while the AI speaks or while a slow tool runs
                            busy = ai_is_talking or tool_running
                            if busy and not prev_busy:
                                set_led_pulse()
                            elif not busy and prev_busy:
                                if rt_session.interaction_mode == "strict":
                                    set_led_off()
                                else:
                                    set_led_on()
                            prev_busy = busy

                            if rt_session.pending_active_switch and not ai_is_talking:
                                rt_session.pending_active_switch = False
                                rt_session.audio.set_mode('active')
                                last_activity_time = time.time()

                            if rt_session.exit_requested:
                                # Let DaVinci's goodbye finish playing before stopping
                                elapsed = time.time() - rt_session.exit_requested_at

                                if ai_is_talking:
                                    exit_audio_idle_since = None
                                elif exit_audio_idle_since is None:
                                    exit_audio_idle_since = time.time()

                                audio_settled = (
                                    exit_audio_idle_since is not None
                                    and time.time() - exit_audio_idle_since > 1.0
                                )

                                if (elapsed > 2.5 and audio_settled) or elapsed > 8.0:
                                    print("Exit requested during session. Shutting down.")
                                    rt_session.stop()
                                    set_led_off()
                                    if pa is not None:
                                        pa.terminate()
                                    print("Cleanup complete.")
                                    set_led_off()
                                    return

                            if rt_session.dismissed_silently:
                                print("Silently dismissed false wake. Closing session quietly.")
                                set_led_off()
                                break

                            timeout = (STRICT_INACTIVITY_TIMEOUT
                                       if rt_session.interaction_mode == "strict"
                                       else INACTIVITY_TIMEOUT)
                            if time.time() - last_activity_time > timeout:
                                print("Inactivity timeout reached. Closing session.")
                                break
                            time.sleep(0.1)

                    except Exception as e:
                        print(f"Failed to start or run session: {e}")

                    finally:
                        rt_session.stop()
                        set_led_off()

                        # If we failed before the handoff, the wake-word stream is
                        # still open — close it so the re-open below is the only one.
                        if audio_stream is not None:
                            try:
                                audio_stream.close()
                            except Exception:
                                pass

                        # 3. RE-OPEN the wake-word stream for the next loop.
                        #    Reset OWW first — the guarded-mode path left its
                        #    window full of 24 kHz-resampled session audio —
                        #    and put the quiet-room gate back to sleep.
                        gate.rearm()
                        audio_stream = pa.open(
                            rate=OWW_RATE,
                            channels=1,
                            format=pyaudio.paInt16,
                            input=True,
                            frames_per_buffer=OWW_CHUNK
                        )

            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(0.1)   # Prevent tight spin on persistent errors
                # If the stream crashes, try to reopen it
                if audio_stream is None or not audio_stream.is_active():
                    audio_stream = pa.open(
                        rate=OWW_RATE,
                        channels=1,
                        format=pyaudio.paInt16,
                        input=True,
                        frames_per_buffer=OWW_CHUNK
                    )

    except KeyboardInterrupt:
        print("Keyboard interrupt received. Exiting.")

    finally:
        wifi.shutdown()   
        if audio_stream is not None:
            audio_stream.close()
        if pa is not None:
            pa.terminate()
        print("Cleanup complete.")
        set_led_off()

if __name__ == "__main__":
    main()
