# the following program is provided by DevMiser - https://github.com/DevMiser

# to use this file, you must download the file porcupine_params_it.pv from
# https://github.com/Picovoice/porcupine/tree/master/lib/common and place it
# in the/home/pi/.local/lib/python3.9/site-packages/pvleopard/lib/common folder 
# on your Raspberry Pi
# You must also download the file leopard_params_it.pv from
# https://github.com/Picovoice/leopard/tree/master/lib/common and place it
# in the /home/pi/.local/lib/python3.9/site-packages/pvleopard/lib/common folder
# on your Raspberry Pi
# You must also create a new wake word in Italian using the Picovoice console
# (https://console.picovoice.ai/), choose Raspberry Pi as the Platform, download the file,
# and put it in the /home/pi/.local/lib/python3.9/site-packages/pvporcupine/resources/keyword_files/raspberry-pi 
# folder on your Raspberry Pi
# In the wake_word() function below, replace "DaVinci" with your new wake word

import datetime
import io
import openai
import os
import pvcobra
import pvleopard
import pvporcupine
import pyaudio
import random
import struct
import sys
import textwrap
import threading
import time

from os import environ
environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

from colorama import Fore, Style
from openai import OpenAI
from PIL import Image,ImageDraw,ImageFont,ImageOps,ImageEnhance
from pvleopard import *
from pvrecorder import PvRecorder
from threading import Thread, Event
from time import sleep

import RPi.GPIO as GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
led1_pin=18
led2_pin=24
GPIO.setup(led1_pin, GPIO.OUT)
GPIO.output(led1_pin, GPIO.LOW)
GPIO.setup(led2_pin, GPIO.OUT)
GPIO.output(led2_pin, GPIO.LOW)

audio_stream = None
cobra = None
pa = None
porcupine = None
recorder = None
wav_file = None

GPT_model = "gpt-4"
openai.api_key = "put your secret API key between these quotation marks"
pv_access_key= "put your secret access key between these quotation marks"

client = OpenAI(api_key=openai.api_key)

prompt = ["See"]

chat_log=[
    {"role": "system", "content": "Your name is DaVinci. You do not have a namesake. You are a helpful AI-based assistant.  You always respond in Italian."},
    ]

#DaVinci will 'remember' earlier queries so that it has greater continuity in its response
#the following will delete that 'memory' three minutes after the start of the conversation
def append_clear_countdown():
    sleep(180)
    global chat_log
    chat_log.clear()
    chat_log=[
        {"role": "system", "content": "Your name is DaVinci. You do not have a namesake. You are a helpful assistant.  You always respond in Italian."},
        ]    
    global count
    count = 0
    t_count.join

def ChatGPT(query):
    user_query = [
        {"role": "user", "content": query},
        ]         
    send_query = (chat_log + user_query)
    response = client.chat.completions.create(
    model=GPT_model,
    messages=send_query
    )
    answer = response.choices[0].message.content
    chat_log.append({"role": "assistant", "content": answer})
    return answer

def current_time():

    time_now = datetime.datetime.now()
    formatted_time = time_now.strftime("%m-%d-%Y %I:%M %p\n")
    print("The current date and time is:", formatted_time)  

def detect_silence():

    cobra = pvcobra.create(access_key=pv_access_key)

    silence_pa = pyaudio.PyAudio()

    cobra_audio_stream = silence_pa.open(
                    rate=cobra.sample_rate,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=cobra.frame_length)

    last_voice_time = time.time()

    while True:
        cobra_pcm = cobra_audio_stream.read(cobra.frame_length)
        cobra_pcm = struct.unpack_from("h" * cobra.frame_length, cobra_pcm)
           
        if cobra.process(cobra_pcm) > 0.2:
            last_voice_time = time.time()
        else:
            silence_duration = time.time() - last_voice_time
            if silence_duration > 1.3:
                print("End of query detected\n")
                GPIO.output(led1_pin, GPIO.LOW)
                GPIO.output(led2_pin, GPIO.LOW)
                cobra_audio_stream.stop_stream                
                cobra_audio_stream.close()
                cobra.delete()
                last_voice_time=None
                break

def fade_leds(event):
    pwm1 = GPIO.PWM(led1_pin, 200)
    pwm2 = GPIO.PWM(led2_pin, 200)

    event.clear()

    while not event.is_set():
        pwm1.start(0)
        pwm2.start(0)
        for dc in range(0, 101, 5):
            pwm1.ChangeDutyCycle(dc)  
            pwm2.ChangeDutyCycle(dc)
            time.sleep(0.05)
        time.sleep(0.75)
        for dc in range(100, -1, -5):
            pwm1.ChangeDutyCycle(dc)                
            pwm2.ChangeDutyCycle(dc)
            time.sleep(0.05)
        time.sleep(0.75)
        
def listen():

    cobra = pvcobra.create(access_key=pv_access_key)

    listen_pa = pyaudio.PyAudio()

    listen_audio_stream = listen_pa.open(
                rate=cobra.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=cobra.frame_length)

    print("Listening...")

    while True:
        listen_pcm = listen_audio_stream.read(cobra.frame_length)
        listen_pcm = struct.unpack_from("h" * cobra.frame_length, listen_pcm)
           
        if cobra.process(listen_pcm) > 0.3:
            print("Voice detected")
            listen_audio_stream.stop_stream
            listen_audio_stream.close()
            cobra.delete()
            break

def responseprinter(chat):
    wrapper = textwrap.TextWrapper(width=70)  # Adjust the width to your preference
    paragraphs = res.split('\n')
    wrapped_chat = "\n".join([wrapper.fill(p) for p in paragraphs])
    for word in wrapped_chat:
       time.sleep(0.055)
       print(word, end="", flush=True)
    print()

def voice(chat):

    response = client.audio.speech.create(
        model="tts-1",
        voice="echo",
        input=chat
    )

    response.stream_to_file("speech.mp3")
             
    pygame.mixer.init()
    pygame.mixer.music.load("speech.mp3")
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        pass
    sleep(0.2)

def wake_word():

    porcupine = pvporcupine.create(keywords=["DaVinci",],
                            access_key=pv_access_key,
                            model_path="/home/pi/.local/lib/python3.9/site-packages/pvporcupine/lib/common/porcupine_params_it.pv", 
                            sensitivities=[0.1,], #from 0 to 1.0 - a higher number reduces the miss rate at the cost of increased false alarms
                                   )
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    sys.stderr.flush()
    os.dup2(devnull, 2)
    os.close(devnull)
    
    wake_pa = pyaudio.PyAudio()

    porcupine_audio_stream = wake_pa.open(
                    rate=porcupine.sample_rate,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=porcupine.frame_length)
    
    Detect = True

    while Detect:
        porcupine_pcm = porcupine_audio_stream.read(porcupine.frame_length)
        porcupine_pcm = struct.unpack_from("h" * porcupine.frame_length, porcupine_pcm)

        porcupine_keyword_index = porcupine.process(porcupine_pcm)

        if porcupine_keyword_index >= 0:

            GPIO.output(led1_pin, GPIO.HIGH)
            GPIO.output(led2_pin, GPIO.HIGH)

            print(Fore.GREEN + "\nWake word detected\n")
            current_time()
            porcupine_audio_stream.stop_stream
            porcupine_audio_stream.close()
            porcupine.delete()         
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
            Detect = False

class Recorder(Thread):
    def __init__(self):
        super().__init__()
        self._pcm = list()
        self._is_recording = False
        self._stop = False

    def is_recording(self):
        return self._is_recording

    def run(self):
        self._is_recording = True

        recorder = PvRecorder(device_index=-1, frame_length=512)
        recorder.start()

        while not self._stop:
            self._pcm.extend(recorder.read())
        recorder.stop()

        self._is_recording = False

    def stop(self):
        self._stop = True
        while self._is_recording:
            pass

        return self._pcm

try:

    o = create(
        access_key=pv_access_key,
        model_path="/home/pi/.local/lib/python3.9/site-packages/pvleopard/lib/common/leopard_params_it.pv", 
        )
    
    event = threading.Event()

    count = 0

    while True:
        
        try:
        
            Chat = 1
            if count == 0:
                t_count = threading.Thread(target=append_clear_countdown)
                t_count.start()
            else:
                pass   
            count += 1
            wake_word()
# comment out the next line if you do not want DaVinci to verbally respond to his name        
            voice(random.choice(prompt))
            recorder = Recorder()
            recorder.start()
            listen()
            detect_silence()
            transcript, words = o.process(recorder.stop())
            t_fade = threading.Thread(target=fade_leds, args=(event,))
            t_fade.start()
            recorder.stop()
            print("You said: " + transcript)
            if Chat == 1:        
                (res) = ChatGPT(transcript)
                print("\nDaVinci's response is:\n")        
                t1 = threading.Thread(target=voice, args=(res,))
                t2 = threading.Thread(target=responseprinter, args=(res,))
                t1.start()
                t2.start()
                t1.join()
                t2.join()
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)
            GPIO.output(led2_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            
        except openai.APIError as e:
            print("\nThere was an API error.  Please try again in a few minutes.")
            voice("\nThere was an A P I error.  Please try again in a few minutes.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)
            GPIO.output(led2_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)

        except openai.RateLimitError as e:
            print("\nYou have hit your assigned rate limit.")
            voice("\nYou have hit your assigned rate limit.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)
            GPIO.output(led2_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            break

        except openai.APIConnectionError as e:
            print("\nI am having trouble connecting to the API.  Please check your network connection and then try again.")
            voice("\nI am having trouble connecting to the A P I.  Please check your network connection and try again.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)
            GPIO.output(led2_pin,
                        GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)

        except openai.AuthenticationError as e:
            print("\nYour OpenAI API key or token is invalid, expired, or revoked.  Please fix this issue and then restart my program.")
            voice("\nYour Open A I A P I key or token is invalid, expired, or revoked.  Please fix this issue and then restart my program.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)
            GPIO.output(led2_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            break
   
except KeyboardInterrupt:
    print("\nExiting ChatGPT Virtual Assistant")
    o.delete
    GPIO.cleanup()

