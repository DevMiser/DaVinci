# DaVinci
### Voice-Activated AI Assistant for Raspberry Pi 4 - New Version Fall 2026

DaVinci is a voice-activated AI assistant that runs on a Raspberry Pi 4 with a USB speakerphone. Say the wake word **"DaVinci"** to start a conversation. Ask questions (including about current events, news, and sports via built-in web search) request the time or weather, set countdown timers, change the speaker volume, switch between three interaction modes (normal, conversational and strict), and more — all by voice. DaVinci has no display; an optional LED shows when it is listening and when it is responding.

<img width="1920" height="1079" alt="d355b059-f8ae-489e-8713-575a9e3b8ff8" src="https://github.com/user-attachments/assets/65090f0f-b769-4a76-857b-67821b27a292" />


DaVinci uses OpenWakeWord for wake-word detection, OpenAI's GPT-Realtime-2.1 API for speech-to-speech conversational voice AI, OpenAI's built-in web search for current information, and the free [Open-Meteo](https://open-meteo.com/) weather service for current weather conditions and forecasts up to seven days ahead. Wake-word detection runs entirely on the Pi from a custom model file included in this repository. There is no account to create, no access key, and no usage quota.

> **This version replaces the original DaVinci.** The original *DaVinci – The ChatGPT Virtual Assistant* (`DaVinci.py`, `DaVinciAltVoice.py` and `DaVinciItalian.py`) is **deprecated** and no longer maintained. Its scripts, instructions, wake-word file and 3D-printing files are preserved in the [`archive`](https://github.com/DevMiser/DaVinci/tree/main/archive) folder of this repository for anyone who still needs them. New builds should use the new `DaVinci.py` in the main folder and the instructions below (the original program of the same name is now `archive/DaVinci.py`).

### What Changed from the Original DaVinci

- **One account.** Picovoice and Amazon Web Services accounts are no longer needed. You need only an OpenAI API key.
- **Natural conversation.** DaVinci now speaks and listens through OpenAI's speech-to-speech Realtime API instead of separate speech-to-text, ChatGPT and text-to-speech steps, so responses begin much sooner and you can ask follow-up questions without repeating the wake word.
- **New abilities.** Web search for current information, current weather and forecasts, named countdown timers, voice-controlled volume, and three interaction modes.
- **USB speakerphone.** A single USB speakerphone replaces the separate USB microphone and USB speaker.
- **One wake word.** The wake word is **"DaVinci"**. The alternative wake words "computer" and "Jarvis" are no longer supported.
- **New enclosure.** The optional enclosure is a sleeker design the uses a LED filament as its indicator light.
- **One status LED.** The program controls a single optional LED on GPIO 18 (the LED filament it the optional enclosure is used. 
- **Wi-Fi setup without a keyboard or screen.** If DaVinci starts without a Wi-Fi connection (for example, after moving it to a new home) it creates its own setup network and tells you how to connect it to your Wi-Fi from your phone.
- **Current operating system.** DaVinci now runs on the current Raspberry Pi OS (Debian Trixie) rather than the legacy operating system.

---

## How to Run DaVinci on a Raspberry Pi 4

The following steps are required:

- Obtain the necessary hardware — listed below
- Create an OpenAI account and obtain your personal secret API key
- Follow the steps below to prepare your Raspberry Pi 4 and install the software
- Wire the status LED (optional)

---

## Hardware Requirements

**Raspberry Pi 4** — A [Raspberry Pi 4](https://www.adafruit.com/product/4292) is required. The 2 GB RAM model is sufficient. Earlier Raspberry Pis are not supported. DaVinci will also probably run fine on a Raspberry Pi 5, but I have not tested it.

**5V Power Supply** — I recommend the [official Raspberry Pi USB-C power supply](https://www.adafruit.com/product/4298).

**USB Speakerphone** — A USB speakerphone provides both microphone input and speaker output in a single device, and replaces the separate USB microphone and USB speaker used by the original DaVinci. I used the [RayBit USB Speakerphone](https://www.amazon.com/dp/B0B4JTMQ9H/) and have also tested the Jabra Speak 510. Other USB speakerphones with echo noise cancellation should work as well because DaVinci detects the speakerphone and its volume controls automatically, although I cannot say for certain because I have not tested others. The optional enclosure is designed for use with the RayBit speakerphone.

> **Important:** Plug the USB speakerphone into one of the **black USB 2.0 ports** (closest to the sides of the board), not the blue USB 3.0 ports (in the middle). The USB 3.0 controller on the Pi (VL805) generates more RF noise, which can interfere with the speakerphone's mic circuitry. 

**MicroSD Card** — A 32 GB or larger card rated **A2** and **V30** (or U3) from a reputable brand is recommended. Purchase from a reputable retailer to avoid counterfeit cards.

**LED (Optional)** — The program lights an LED when it hears the wake word and pulses it while it is responding. This [LED filament] (https://www.adafruit.com/product/5508) is what I used with the optional enclosure: 

**Resistor (220 ohm) (Optional)** — Only needed if you decide to use the optional LED. I used [these](https://www.adafruit.com/product/2780).

**Heatsinks (Recommended)** — Strongly recommended, and essential if you will put your Raspberry Pi in a case or the optional enclosure. A Raspberry Pi 4 runs warm even when idle, and listening for the wake word adds a few degrees more (see **Keeping the Pi Cool**). I used [these](https://www.amazon.com/dp/B07ZLZRDXZ).

**Enclosure (Optional)** — STLs for 3D printing the optional enclosure are in this repository.

**Angle Adapter (Optional)** — Only needed of you use the optional enclosure.  I used this [one] (https://www.amazon.com/dp/B0FXLWKSSM).

> **Upgrading from the original DaVinci?** You can reuse your Raspberry Pi 4, power supply, one LED, one resistor and heatsinks. The USB microphone and USB speaker are no longer used — replace them with a USB speakerphone.

---

## Optional LED Wiring

DaVinci can light an LED to show the status of the program. The use of the LED is optional and will not otherwise affect how DaVinci works.

Wire the LED as follows:

- **GPIO 18** (physical pin 12) → **220 ohm resistor** → the LED's **long leg** (anode)
- The LED's **short leg** (cathode) → any **GND** pin (physical pin 14 is the nearest)

The LED behaves as follows:

| LED | Meaning |
|---|---|
| Off | DaVinci is idle and waiting for its wake word |
| On | DaVinci heard its wake word and is listening |
| Pulsing | DaVinci is speaking, or is working on a request such as a web search |

> **Note:** The original DaVinci controlled two LEDs, on GPIO 18 and GPIO 24. This version controls only the LED on GPIO 18.

---

## Create an OpenAI Account and Obtain Your API Key

Open a web browser and navigate to https://openai.com/.

Click on the dropdown menu for **Log in** in the upper right-hand corner, then click on **API Platform** and sign up for an account.

Once logged in, click on **Create API key** and follow the instructions. Copy your API key and keep it in a secure location. You will need it in a later step.

> **Note:** Your OpenAI API key is used for both the Realtime conversational API and web search. The OpenAI API requires a paid account with billing enabled. Ensure your account has sufficient credits before running DaVinci.

---

## Prepare Your Raspberry Pi 4

These instructions assume you already have a Raspberry Pi 4 set up and running **Raspberry Pi OS (64-bit, Debian Trixie)**. If not, use the Raspberry Pi Imager to install it, which is available here: https://www.raspberrypi.com/software/. Be sure to use the **64-bit** Debian Trixie version — the 32-bit version may produce memory errors. Unlike the original DaVinci, this version does **not** use the legacy operating system.

DaVinci does not use a display, so either **Raspberry Pi OS with desktop** or **Raspberry Pi OS Lite** will work. If you do not plan to connect a monitor and keyboard, use the Raspberry Pi Imager's settings to set your username to `pi`, enter your Wi-Fi details and enable SSH (or use Raspberry Pi Connect) so that you can reach the Pi from another computer.

> **Note:** Raspberry Pi OS Trixie is based on Debian 13 with kernel 6.12 LTS and Python 3.13. The Raspberry Pi Foundation recommends doing a clean install rather than upgrading in place from a previous release such as Bookworm. The Debian OS also often asks for the Pi's password when asked to take certain actions, including many commands that begin with "sudo". Whenever asked, type the password for your device and press Enter.

### 1. Update Your System

Open a terminal and enter the following commands in order:

```
sudo apt update
sudo apt full-upgrade
```

If asked whether you want to continue, enter **Y** and press Enter. When the upgrade completes, reboot:

```
sudo reboot
```

Log back in after the reboot.

### 2. Install System-Level Dependencies

Some packages must be installed at the system level via `apt` before setting up the Python environment. Open a terminal and enter the following commands in order:

```
sudo apt install git portaudio19-dev
sudo apt install swig liblgpio-dev
sudo apt install pipewire pipewire-alsa wireplumber
```

If asked whether you want to continue, enter **Y** and press Enter.

> **Note:** `portaudio19-dev` is needed to build the audio library that reads the microphone and plays DaVinci's voice. `swig` and `liblgpio-dev` are needed by the library that controls the LED. `pipewire`, `pipewire-alsa` and `wireplumber` make up the audio server described in step 8 — they are already installed on Raspberry Pi OS with desktop, in which case the last command simply reports that they are up to date.

### 3. Clone the DaVinci Repository

Open a terminal and enter the following commands:

```
cd /home/pi
git clone https://github.com/DevMiser/DaVinci.git
cd DaVinci
```

> **Note:** These instructions expect the files to be located at `/home/pi/DaVinci/`. If your username is not `pi`, or your clone creates a differently named folder, adjust the paths in the following steps accordingly.

### 4. Create a Python Virtual Environment

Debian 13 (and therefore Raspberry Pi OS Trixie) ships Python 3.13 and enforces PEP 668, so all Python packages must be installed inside a virtual environment rather than system-wide. Create and activate a virtual environment by entering the following commands:

```
python3 -m venv venv
source venv/bin/activate
```

Your terminal prompt will change to show `(venv)` at the beginning, confirming the virtual environment is active.

### 5. Install Python Dependencies

With the virtual environment active, install all required packages:

```
pip install -r requirements.txt
```

This may take several minutes on a Raspberry Pi 4.

> **Important:** Do **not** install `torch` or the `silero-vad` package. DaVinci already uses the voice-activity detector bundled with OpenWakeWord, and on a 64-bit Raspberry Pi `torch` pulls in several gigabytes of unneeded GPU libraries that can fill your SD card.

> **Note:** Web search requires the `openai` package to be version **1.66 or newer**. If you installed the requirements a while ago, update it with `pip install --upgrade openai`.

### 6. Create Your .env File with Your API Key

DaVinci loads your OpenAI API key from a `.env` file located in the same folder as the script. Create this file by entering the following commands:

```
cd /home/pi/DaVinci
nano .env
```

Add the following line to the file, replacing the placeholder text with your actual key:

```
OPENAI_API_KEY="put your OpenAI API key here between the quotation marks"
```

Press **Ctrl + X**, then **Y**, then **Enter** to save the file.

> **Important:** Never share your `.env` file or commit it to a public repository.

### 7. Turn Off the Pi's Built-In Audio

The Raspberry Pi 4 has audio outputs of its own — two HDMI ports and a headphone jack. DaVinci does not use them, and they can get in the way of the USB speakerphone, so turn them off. The speakerphone then becomes the Pi's only sound device.

Open the configuration file:

```
sudo nano /boot/firmware/config.txt
```

Make the following two changes:

1. Find the line `dtparam=audio=on` and change it to:

```
dtparam=audio=off
```

2. Find the line `dtoverlay=vc4-kms-v3d` and change it to:

```
dtoverlay=vc4-kms-v3d,noaudio
```

Press **Ctrl + X**, then **Y**, then **Enter** to save, then reboot:

```
sudo reboot
```

> **Note:** This turns off only the sound from the HDMI ports. If you connect a monitor to the Pi, the picture still works.

After rebooting, with your speakerphone plugged in, open a terminal and enter:

```
cat /proc/asound/cards
```

You should see your USB speakerphone and nothing else, similar to:

```
 0 [Device         ]: USB-Audio - USB Audio Device
                      Generic USB Audio Device at usb-0000:01:00.0-1.4, full speed
```

The name shown depends on your speakerphone. If nothing is listed, the speakerphone is not being detected — check that it is plugged into one of the black USB 2.0 ports.

DaVinci finds the speakerphone and its volume controls automatically each time it starts, so there is nothing to configure for your particular model. You can swap one USB speakerphone for another without changing any settings.

### 8. Configure PipeWire Audio

Raspberry Pi OS Trixie uses **PipeWire** as its audio server. PipeWire handles all audio routing — including USB speakerphone access and sample-rate conversion between the speakerphone and the rates DaVinci uses — so no `~/.asoundrc` file is needed.

First, enable and start the PipeWire services for your user session:

```
systemctl --user enable pipewire wireplumber
systemctl --user start pipewire wireplumber
```

Verify PipeWire is running:

```
wpctl status
```

You should see a line near the top similar to `PipeWire 'pipewire-0'`, followed by an **Audio** section. Your USB speakerphone should be listed under both **Sinks** (speaker) and **Sources** (microphone), each marked with an asterisk (`*`) showing that it is the default device.

With the Pi's built-in audio turned off in step 7, the speakerphone is the only device, so it is the default automatically. If the asterisk is next to a different device, note the number shown beside your speakerphone under **Sinks** and under **Sources**, and make each the default by entering the following command once for each number:

```
wpctl set-default 55
```

Replace `55` with the number shown on your system.

> **Note:** `wpctl` is PipeWire's own control tool and is installed with `wireplumber`. DaVinci does not use PipeWire's PulseAudio compatibility layer, so you do not need `pipewire-pulse`, `pulseaudio-utils` or the `pactl` command.

Next, create a PipeWire configuration file to increase the audio buffer size. This prevents clicking and stuttering that can occur when the AI voice audio arrives over the network in bursts:

```
mkdir -p ~/.config/pipewire/pipewire.conf.d
nano ~/.config/pipewire/pipewire.conf.d/fix-clicks.conf
```

Paste the following into the file:

```
context.properties = {
    default.clock.rate        = 48000
    default.clock.quantum     = 2048
    default.clock.min-quantum = 1024
    default.clock.max-quantum = 8192
}
```

Press **Ctrl + X**, then **Y**, then **Enter** to save. Then restart PipeWire to apply the change:

```
systemctl --user restart pipewire wireplumber
```

> **Note:** Do **not** create a `~/.asoundrc` file. PipeWire manages ALSA routing automatically, and an `~/.asoundrc` file will conflict with it.

### 9. Verify the Wake-Word Model

Wake-word detection uses a custom OpenWakeWord model that is included in this repository, so there is nothing to download or move — step 3 already put it in place. Confirm it is there by opening a terminal and entering:

```
ls /home/pi/DaVinci/*.onnx
```

You should see:

```
/home/pi/DaVinci/DaVinci_20261008_030815.onnx
```

The script looks for this file in its own folder, so it must sit alongside `DaVinci.py`. If you move the script elsewhere, move the `.onnx` file with it. If the file is missing, the program will stop at startup and tell you exactly which file it expected and where.

---

## Run the Program

Make sure your USB speakerphone is plugged into one of the black USB 2.0 ports. Then open a terminal, navigate to the DaVinci folder, and activate the virtual environment:

```
cd /home/pi/DaVinci
source venv/bin/activate
```

Then run the program:

```
python DaVinci.py
```

While it starts, the terminal shows a few lines that are useful for checking your setup:

- `Loading OpenWakeWord model: DaVinci_20261008_030815.onnx ...` and `Model key: ...` — the wake-word model loaded successfully.
- `ALSA mixer: card ..., playback volume control = PCM, capture volume control = Mic` — the speakerphone DaVinci found and the volume controls it will use. The names vary between speakerphones.
- `Network: online.` — DaVinci is connected to the internet. If it starts without a connection, see **Setting Up Wi-Fi**.
- `IP geolocation: default location set to '...'` — the location DaVinci will use for weather requests that do not name a place.
- `Setup audio: recorded the '...' message.` — printed only the first time DaVinci runs with internet. It records its spoken Wi-Fi setup instructions so it can still give them when it has no internet (see **Setting Up Wi-Fi**).
- `Microphone background level: RMS ...` — how much sound the speakerphone hears in the room. **0** means the microphone is muted or not delivering audio.
- `Quiet-room gate: RMS ... (background ...)` — how loud a sound must be to wake the wake-word detector. See **Keeping the Pi Cool**.
- `Listening for wake word ('DaVinci')...` — DaVinci is ready.

> **Tip:** Keep the room quiet for the first few seconds after starting DaVinci. It measures the room's background noise then, and sets the quiet-room gate from it.

---

## Using DaVinci

### Waking DaVinci

Say the wake word:

> **"DaVinci"**

When DaVinci detects its wake word, the LED turns on and it begins listening. The LED pulses while DaVinci responds. In **normal** and **strict** modes you can also say **"DaVinci"** at any time to interrupt it mid-response and ask a new question. In **conversational** mode you can interrupt simply by speaking — no wake word required. See **Interaction Modes** below for details.

You do not need to pause after the wake word. DaVinci keeps recording continuously while the connection to the AI is being established, so you can run your request straight on from the wake word — *"DaVinci, what's the weather today?"* — without losing the first few words.

After DaVinci finishes answering, you can ask a follow-up question without the wake word (except in strict mode). If you say nothing for a few seconds, the LED turns off and DaVinci goes back to waiting for its wake word.

### Talking to DaVinci

Once awake, speak naturally. DaVinci will respond conversationally. For example:

*What time is it?*

*What's the weather like today?*

*What will the weather be like on Friday?*

*What is the difference between pumas and leopards?*

*Write a short poem about artificial intelligence.*

*Explain entropy.*

### Asking About Current Events (Web Search)

DaVinci can answer questions about things that happened after its AI model's knowledge cutoff — news, sports schedules and scores, election results, prices, product releases, and other current information. When you ask a time-sensitive question, DaVinci says a brief acknowledgment like *"Let me check on that,"* searches the web, and speaks a concise current answer. The LED pulses while the search is running. For example:

*What teams are playing in the next FIFA World Cup game?*

*How did the stock market do today?*

*Who won last night's Yankees game?*

*What's the latest news about the hurricane?*

No extra setup is required — web search uses your OpenAI API key. DaVinci answers timeless questions from its own knowledge without searching, and uses the dedicated weather tools for weather questions.

> **Note:** Searches take a few seconds, which is why DaVinci says "Let me check on that" first.

### Interaction Modes

DaVinci supports three interaction modes that change how turns are gated between you and DaVinci. You can switch modes at any time by voice, and the selected mode persists across sessions until you change it again or restart the program.

**Normal mode** *(default at startup)*

- DaVinci's microphone is guarded while it is speaking. To interrupt mid-response, say **"DaVinci"**.
- Between turns you can speak freely without the wake word.
- Best general-purpose mode.

**Conversational mode**

- You can interrupt DaVinci mid-sentence simply by speaking — no wake word required.
- OpenAI's voice activity detector decides when you have started and stopped speaking, so DaVinci's mic stays active during its own responses.
- Best for free-flowing back-and-forth dialog in a quiet room.

**Strict mode** *(also called wake-word-only mode)*

- You must say **"DaVinci"** before **every** new request, including short follow-ups.
- The session and conversation history stay intact between turns, so DaVinci can still reference what you just discussed.
- Between turns the LED turns off.
- Useful in noisy rooms

**Switching modes by voice:**

*Switch to conversational mode.*

*Turn on strict mode.* (or *Only respond to the wake word.* / *Wake-word only mode.*)

*Go back to normal mode.*

DaVinci will briefly confirm the change.

> **Note:** The startup default is set by the `INTERACTION_MODE` constant near the top of the script. Change it from `"normal"` to `"conversational"` or `"strict"` if you want a different default at boot.

### Setting Timers

DaVinci supports multiple named countdown timers. For example:

*Set a ten-minute timer.*

*Set a pasta timer for twelve minutes.*

*How much time is left on the pasta timer?*

*Cancel the pasta timer.*

When a timer finishes, DaVinci will announce it. If no conversation is active when the timer finishes, DaVinci plays a chime three times instead.

### Changing the Volume

To change how loudly DaVinci speaks, say:

*Turn it up.*

*Turn the volume down.*

*Set the volume to fifty percent.*

"Up" and "down" change the volume in steps of 10 percent. The volume can be set anywhere from 10 to 100 percent, and DaVinci confirms the new level. The volume returns to its startup level (80 percent) each time the program is restarted.

### Exiting the Program

Wake DaVinci first, then ask it to quit:

> **"DaVinci"** … *"Exit the program."*

DaVinci will say a brief goodbye, finish speaking, and then shut down cleanly. Other phrasings work too — *"shut down,"* *"quit,"* or *"close the program."*

You can also press **Ctrl + C** in the terminal.

---

## Setting Up Wi-Fi

DaVinci normally uses the Wi-Fi network you set up when you installed Raspberry Pi OS. If you move DaVinci somewhere that network can't be found, or your network's name or password changes, you can connect it to a new network from your mobile device.

When DaVinci starts without a connection, it waits briefly in case the network is only slow to come up, and then switches to setup mode:

- If your saved network can't be found at all, DaVinci switches after about two minutes.
- If your saved network can be seen but DaVinci can't connect to it, it keeps trying for an hour before switching, in case the problem is temporary.

In setup mode, DaVinci creates its own open Wi-Fi network called **DaVinci-Setup**, the LED gives a short blink every two seconds, and DaVinci tells you what to do. To hear the instructions again, say **"DaVinci"**.

To connect DaVinci to your Wi-Fi:

1. On your phone, open the Wi-Fi settings and join the network **DaVinci-Setup**. Your phone may warn that the network has no internet connection; stay connected anyway.
2. Open your web browser and go to **http://10.42.0.1:8080**.
3. Tap your home network in the list (or type its name if it isn't listed), enter its password, and tap **Connect**.

Your phone will drop the DaVinci-Setup network and return to your usual Wi-Fi on its own. Within about a minute, DaVinci will say that it is connected and ready. If the password was wrong, DaVinci says so and the DaVinci-Setup network comes back, so you can join it and try again.

While DaVinci is in setup mode, it checks every five minutes whether your saved network has come back. If it has — for example, after a power cut that took your router down for a while — DaVinci reconnects and leaves setup mode by itself.

> **Note:** DaVinci records its spoken setup instructions the first time it runs with an internet connection, using your OpenAI account, and keeps them in the `setup_audio` folder. If the recordings are missing, the blinking LED is the only sign that DaVinci is in setup mode.

> **Note:** A Raspberry Pi connected to your network by an Ethernet cable is already online, so it never enters setup mode.

---

## Keeping the Pi Cool

Listening for "DaVinci" means running several small neural networks on every 80 milliseconds of audio. To avoid paying that price in an empty room, DaVinci measures each slice of audio's loudness first and only runs the wake-word detector once sound crosses a threshold. In a quiet room the detector sleeps. DaVinci keeps the last two seconds of audio while it sleeps, so when a sound does arrive, the detector hears the run-up as well and a wake word already under way is not missed. After three seconds of quiet, it goes back to sleep.

The threshold is set automatically from the background noise DaVinci measures at startup, and both numbers are printed:

```
Quiet-room gate: RMS 62 (background 25) — the wake-word engine sleeps while the room is quiet
```

Once a minute DaVinci also prints a health line so you can see what this is costing:

```
Health: CPU 63°C, process CPU 1% of one core, wake-word engine active 0% of the time, throttled=0x0
```

- **CPU** is the Pi's temperature. The Raspberry Pi 4 only starts slowing itself down at about 80°C.
- **process CPU** is DaVinci's own share of one of the Pi's four cores. In a quiet room this should be a few percent. With the detector awake the whole time it is roughly a third of one core.
- **wake-word engine active** is how much of the time the detector was awake. A television, music or conversation keeps it awake by design, because DaVinci has to listen whenever there is sound.
- **throttled** comes from the Pi's firmware. Anything other than `0x0` means it has throttled or seen an undervoltage event — check your cooling and power supply.

**What to expect.** On my Raspberry Pi 4, the Pi sat at about 61.5°C with DaVinci stopped. With DaVinci running, it was about 63–64°C in a quiet room and about 66°C in a noisy one; before the quiet-room gate was added it ran a little above 68°C all the time. In other words, DaVinci itself now adds only a few degrees — most of the temperature is the Pi's own baseline. 

**If the wake word is missed** — for example when speaking quietly or from across the room — the gate's threshold may be too high for your room. You can lower it by setting `GATE_RMS` to a fixed number such as `40`, or set it to `0` to turn the gate off and run the detector all the time.

---

## Running DaVinci Automatically at Startup (Optional)

After everything is working, you may want DaVinci to launch automatically when you plug in its power. Because DaVinci has no display, the most reliable way to do this is with a **systemd user service**. It starts DaVinci at boot without anyone logging in and without a monitor attached, starts it after the PipeWire audio server is ready, restarts it if it ever stops unexpectedly, and keeps a log of its output that you can read later.

Open a terminal and enter:

```
mkdir -p ~/.config/systemd/user
nano ~/.config/systemd/user/davinci.service
```

Add the following content:

```
[Unit]
Description=DaVinci Voice Assistant
After=pipewire.service wireplumber.service
Wants=pipewire.service wireplumber.service

[Service]
WorkingDirectory=/home/pi/DaVinci
ExecStart=/home/pi/DaVinci/venv/bin/python -u /home/pi/DaVinci/DaVinci.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Press **Ctrl + X**, then **Y**, then **Enter** to save. Then enable the service, start it, and allow it to run at boot without anyone logging in:

```
systemctl --user daemon-reload
systemctl --user enable --now davinci
sudo loginctl enable-linger pi
```

DaVinci will now launch automatically each time the Raspberry Pi boots. Allow up to a minute after plugging in the power before saying the wake word. If it can't connect to Wi-Fi, it will switch to setup mode (see **Setting Up Wi-Fi**).

To check whether DaVinci is running:

```
systemctl --user status davinci
```

To watch DaVinci's output as it runs (press **Ctrl + C** to stop watching):

```
journalctl --user -u davinci -f
```

> **Note:** If you ask DaVinci to "exit the program," it stays stopped until the next reboot. To start it again sooner, enter `systemctl --user start davinci`.

> **Note:** If you ever need to stop DaVinci from launching at startup, enter `systemctl --user disable --now davinci`.

> **Note:** Before running `python DaVinci.py` by hand in a terminal, stop the service with `systemctl --user stop davinci`. Otherwise two copies of DaVinci will compete for the speakerphone.

---

## Configuration Reference

The following constants near the top of `DaVinci.py` can be adjusted to suit your setup:

| Constant | Default | Description |
|---|---|---|
| `INACTIVITY_TIMEOUT` | `3` seconds | How long DaVinci waits after silence before ending a session |
| `STRICT_INACTIVITY_TIMEOUT` | `30` seconds | How long a strict-mode session stays alive waiting for the next wake-word turn before closing |
| `OWW_THRESHOLD` | `0.5` | Wake-word confidence gate (0.0–1.0). Raise it if DaVinci wakes on background speech; lower it if it misses the wake word. |
| `OWW_VAD_THRESHOLD` | `0.4` | Voice-activity gate applied before wake-word scoring, which suppresses false wakes from non-speech noise |
| `GATE_RMS` | `None` | Loudness that wakes the wake-word detector. `None` sets it automatically from the measured background level; a number sets it directly; `0` turns the gate off. |
| `GATE_MIN_RMS` | `60` | The automatic threshold is never set below this |
| `GATE_FLOOR_FACTOR` | `2.5` | The automatic threshold is this many times the measured background level |
| `GATE_PREROLL_FRAMES` | `25` | Slices of audio (80 ms each) kept while the detector sleeps, so it hears the start of a wake word |
| `GATE_HANG_SECONDS` | `3.0` seconds | How long the room must stay quiet before the detector sleeps again |
| `GATE_KEEP_AWAKE_SCORE` | `0.05` | A wake-word score at least this high also keeps the detector awake |
| `STATS_INTERVAL` | `60.0` seconds | How often the `Health:` line is printed (`0` turns it off) |
| `WIFI_SETUP_ENABLED` | `True` | Whether DaVinci switches to Wi-Fi setup mode when it starts without a connection |
| `HOTSPOT_SSID` | `"DaVinci-Setup"` | Name of the setup network DaVinci creates |
| `WEB_PORT` | `8080` | Port of the setup page at `http://10.42.0.1` |
| `NO_WIFI_GRACE_SECONDS` | `30` seconds | With no saved Wi-Fi network at all, how long DaVinci waits before setup mode |
| `UNDETECTED_GRACE_SECONDS` | `90` seconds | How long the saved network must be missing from Wi-Fi scans before setup mode |
| `STUCK_BACKSTOP_SECONDS` | `3600` seconds | How long DaVinci keeps trying a saved network that is visible but won't connect before setup mode |
| `HOTSPOT_RETRY_INTERVAL` | `300` seconds | While in setup mode, how often DaVinci checks whether the saved network has come back |
| `WAKE_MODEL_FILE` | `"DaVinci_20261008_030815.onnx"` | Filename of the OpenWakeWord model, expected in the same folder as the script |
| `WAKE_LABEL` | `"DaVinci"` | The wake word as shown in the terminal output |
| `BRIDGE_MAX_SECONDS` | `5` | Safety cap on how much speech is buffered while the AI connection is opening |
| `INTERACTION_MODE` | `"normal"` | Startup interaction mode. One of `"normal"`, `"conversational"`, or `"strict"`. Can be changed by voice at runtime. |
| `USE_IP_LOCATION` | `True` | Whether to auto-detect your location via IP for weather queries |
| `DEFAULT_LATITUDE` | `40.7128` | Latitude of the fallback weather location (used if IP geolocation fails) |
| `DEFAULT_LONGITUDE` | `-74.0060` | Longitude of the fallback weather location. Use a negative number for locations west of Greenwich, such as the Americas. |
| `DEFAULT_LOCATION_DISPLAY` | `"New York, New York"` | Fallback location name spoken in weather responses |
| `FORECAST_MAX_DAYS` | `7` | How many days ahead DaVinci will give a weather forecast |
| `current_volume` | `80` | Speaker volume (percent) applied each time the program starts |
| `led1_pin` | `18` | GPIO pin (BCM numbering) that controls the status LED |

If `USE_IP_LOCATION` is `True`, DaVinci will attempt to determine your location automatically from your device's public IP address at startup. If geolocation fails, it will fall back to the hardcoded `DEFAULT_LATITUDE`, `DEFAULT_LONGITUDE` and `DEFAULT_LOCATION_DISPLAY` values.

Two further settings are found lower in the script. DaVinci's voice is set by `"voice": "cedar"` in the `_send_session_update()` function, and the OpenAI Realtime model is set by the `url` line at the top of the `main()` function.

---

## Project Structure

```
DaVinci/
├── DaVinci.py                       # Main program
├── DaVinci_20261008_030815.onnx     # OpenWakeWord wake-word model
├── davinci_setup.html               # Wi-Fi setup page
├── requirements.txt                 # Python dependencies
├── .env                             # Your API key (you create this — never commit it)
├── setup_audio/                     # Spoken Wi-Fi setup instructions (recorded automatically)
├── README.md
└── archive/                         # The original, deprecated DaVinci
    ├── README.md                                                    # Original README
    ├── DaVinci.py                                                   # Original program (Amazon Polly voice)
    ├── DaVinciAltVoice.py                                           # Original program (OpenAI voice)
    ├── DaVinciItalian.py                                            # Original program (Italian)
    ├── DaVinci_raspberry-pi.ppn                                     # Picovoice Porcupine wake-word file
    ├── DaVinci - The ChatGPT Virtual Assistant Instructions.pdf
    ├── DaVinci 3D Priting Instructions.pdf
    ├── Important - Please Read.pdf
    ├── DaVinci-Body.stl                                             # 3D-printable enclosure
    ├── DaVinci-BasePlate.stl
    └── DaVinci - EyeSocket.stl
```

---

## The Original DaVinci Enclosure

The STL files for the original DaVinci enclosure are in the [`archive`](https://github.com/DevMiser/DaVinci/tree/main/archive) folder. That enclosure was designed around the original USB microphone and USB speaker. It has no mount for a USB speakerphone, so if you use it with this version, the speakerphone sits outside the enclosure and plugs into the Pi with its USB cable.

## The New Enclosure

The STL files for the new enclosure are in this repository. When printing, make certain that your supports do not fill in the holes at the ends of the grooves on the top front of the enclosure where the LED filament goes.

---

## Troubleshooting

**DaVinci does not respond to its wake word.**
Check that your USB speakerphone is recognized using `arecord -l`, and that `wpctl status` shows it as the default device under **Sources**. Confirm the wake-word model is present next to the script with `ls /home/pi/DaVinci/*.onnx`. Run the program from a terminal and watch the console: every detection prints its confidence, for example `Wake word detected  (confidence: 0.93)`. If nothing prints when you speak, lower `OWW_THRESHOLD` from `0.5` toward `0.4`; if it wakes on background conversation or the television, raise it instead. If DaVinci only misses quiet or distant speech, the quiet-room gate may be set too high for your room — see **Keeping the Pi Cool**.

**DaVinci stops at startup with `Wake word model not found`.**
The message names the file it expected and where. Re-copy the `.onnx` file into `/home/pi/DaVinci/`, or confirm that `WAKE_MODEL_FILE` near the top of the script matches the name of your `.onnx` file exactly.

**DaVinci stops at startup with a `FATAL` message saying it failed to load the OpenWakeWord model.**
The message lists the openwakeword build that is installed and the support models it found, so start there. If support models (`melspectrogram.onnx`, `embedding_model.onnx`) are reported missing, confirm the Pi is connected to the internet and reinstall openwakeword inside the virtual environment: `pip install --force-reinstall openwakeword`.


**DaVinci stops at startup with `KeyError: 'OPENAI_API_KEY'`.**
Confirm the `.env` file exists in `/home/pi/DaVinci/` and contains your key (see step 6 of **Prepare Your Raspberry Pi 4**).

**Audio device errors on startup (`Invalid sample rate` or `Device unavailable`).**
Confirm PipeWire is running: `wpctl status` should begin with a line similar to `PipeWire 'pipewire-0'` and list your speakerphone under both **Sinks** and **Sources**. If it reports that it could not connect to PipeWire, start it with `systemctl --user start pipewire wireplumber` and check it with `systemctl --user status pipewire wireplumber`. Also confirm there is **no** `~/.asoundrc` file in your home directory (`ls -la ~`). If one exists, delete it with `rm ~/.asoundrc` and restart PipeWire.

**DaVinci hears me but I cannot hear it, or the sound comes from the wrong device.**
Run `wpctl status` and confirm the asterisk (`*`) under **Sinks** is next to your USB speakerphone. If it is not, set the speakerphone as the default as described in step 8 of **Prepare Your Raspberry Pi 4**.

**Clicking or stuttering when DaVinci speaks.**
Confirm the PipeWire configuration file exists at `~/.config/pipewire/pipewire.conf.d/fix-clicks.conf` and that `default.clock.quantum` is set to `2048`. Restart PipeWire after any changes: `systemctl --user restart pipewire wireplumber`.

**The speakerphone does not appear in `cat /proc/asound/cards`, or `wpctl status` does not list it.**
Confirm the speakerphone is plugged into one of the black USB 2.0 ports and that `lsusb` lists it. If `lsusb` shows the speakerphone but `cat /proc/asound/cards` does not, confirm you made both changes in step 7 of **Prepare Your Raspberry Pi 4** and rebooted. Also check for a file left over from other instructions that assigns the speakerphone a fixed card number: enter `cat /etc/modprobe.d/alsa-base.conf`, and if it contains a line beginning `options snd-usb-audio index=`, delete that line and reboot.

**DaVinci says it failed to adjust the volume.**
Run the program from a terminal and look for the line beginning `ALSA mixer: card` near the top of the output. It shows the sound card DaVinci found and the volume controls it will use. If it reports `no USB audio device found`, the speakerphone was not detected when the program started — see the next entry. If it reports `playback volume control = NONE`, your speakerphone does not offer a volume control the Pi can adjust; use the volume buttons on the speakerphone instead.

**DaVinci does not respond to follow-up questions without the wake word.**
This is expected behavior in strict mode. Say "DaVinci" before each new request, or ask DaVinci to switch to normal or conversational mode. In the other modes, DaVinci stops listening after a few seconds of silence — say "DaVinci" to wake it again, or increase `INACTIVITY_TIMEOUT`.

**Speaker audio causes DaVinci to interrupt itself.**
In **normal** and **strict** modes, the program uses a guarded mic that suppresses speaker bleed during AI speech, so self-interruption should be rare. In **conversational** mode, the mic stays active during AI speech, which makes self-interruption more likely. If it occurs, lower the volume, try increasing the threshold value in the `server_vad` section of the session configuration in the script, or ask DaVinci to switch to normal or strict mode.

**Weather queries fail or return errors.**
Weather needs no API key, so confirm your network connection is working. Run the program from a terminal and ask again — the reason is printed on a line beginning `Weather error:` or `Forecast error:`. If DaVinci says it couldn't find a place, name it more fully, for example *"Springfield, Illinois"* rather than *"Springfield"*. Forecasts are available up to seven days ahead.

**DaVinci gives the weather for the wrong city.**
When you do not name a place, DaVinci uses the location it detected from your internet connection at startup, which is not always accurate. Set `USE_IP_LOCATION` to `False` and enter your own location in `DEFAULT_LATITUDE`, `DEFAULT_LONGITUDE` and `DEFAULT_LOCATION_DISPLAY`. You can find the latitude and longitude of any place by right-clicking it in Google Maps.

**Web search fails or DaVinci says it couldn't find current information.**
The script automatically tries a list of search models and reports each attempt in the terminal, so watch the console output when you ask a current-events question. If you see model-availability errors, ensure the `openai` package is version 1.66 or newer (`pip install --upgrade openai`). If every model candidate is rejected, the candidate list is defined in `SEARCH_MODEL_CANDIDATES` in the script and can be updated to newer model names. Also verify your OpenAI account has billing enabled and sufficient credits.

**Timers fire but DaVinci doesn't announce them.**
If no conversation is active when a timer expires, the program plays a chime three times instead. This is expected behavior.

**The LED does not light.**
Confirm the LED is wired to GPIO 18 (physical pin 12) through the resistor and to a GND pin, and that the LED is the right way around — the long leg goes toward the resistor. If you are upgrading from the original DaVinci, note that the LED on GPIO 24 is no longer used.

**The program fails at startup with an error mentioning `RPi.GPIO` or `lgpio`.**
Confirm `swig` and `liblgpio-dev` are installed (step 2 of **Prepare Your Raspberry Pi 4**), then reinstall the library inside the virtual environment: `pip install --force-reinstall rpi-lgpio`.

**DaVinci does not switch to Wi-Fi setup mode, or the DaVinci-Setup network does not appear.**
Allow at least two minutes after startup — longer if your saved network is still visible (see **Setting Up Wi-Fi**). Make sure no Ethernet cable is plugged in. Then check DaVinci's output (`journalctl --user -u davinci -n 100` if it runs as a service). A line beginning `Wi-Fi setup hotspot failed:` gives the reason. If it mentions `Not authorized`, NetworkManager refused the change and DaVinci's fallback through `sudo` also failed — confirm that `sudo -n true` runs without asking for a password.

**DaVinci is in setup mode but says nothing.**
It has no recording of its setup instructions yet. These are recorded the first time DaVinci runs with an internet connection (look for `Setup audio: recorded ...` lines). Follow the steps in **Setting Up Wi-Fi** using the blinking LED as your guide; once DaVinci is online again, the recordings will be made.

**The setup page does not open.**
Confirm your phone is still connected to **DaVinci-Setup** — some phones switch back to mobile data or another network when they find no internet. Type the address exactly, including `http://` and `:8080`: **http://10.42.0.1:8080**.

**DaVinci does not launch at startup (if you have set it to do so).**
Check the service with `systemctl --user status davinci` and read its output with `journalctl --user -u davinci -n 50`. Confirm lingering is enabled: `loginctl show-user pi --property=Linger` should report `Linger=yes`. If you changed the service file, enter `systemctl --user daemon-reload` and then `systemctl --user restart davinci`.

---

*Weather data by [Open-Meteo.com](https://open-meteo.com/), whose free service is offered for non-commercial use.*

*Provided by DevMiser — https://github.com/DevMiser*
