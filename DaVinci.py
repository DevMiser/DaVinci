# the following program is provided by DevMiser - https://github.com/DevMiser

import boto3
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

import RPi.GPIO as GPIO

from os import environ
environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

from colorama import Fore, Style
from pvleopard import *
from pvrecorder import PvRecorder
from threading import Thread, Event
from time import sleep

GPIO.setwarnings(False)

GPIO.setmode(GPIO.BCM)
led1_pin=18
led2_pin=23

GPIO.setup(led1_pin, GPIO.OUT)
GPIO.output(led1_pin, GPIO.LOW)

GPIO.setup(led2_pin, GPIO.OUT)
GPIO.output(led2_pin, GPIO.LOW)

audio_stream = None
cobra = None
pa = None
polly = boto3.client('polly')
porcupine = None
recorder = None
wav_file = None

GPT_model = "gpt-3.5-turbo" # most capable GPT-3.5 model and optimized for chat
openai.api_key = "put your secret API key between these quotation marks"
pv_access_key= "put your secret access key between these quotation marks"

prompt = ["How may I assist you?",
    "How may I help?",
    "What can I do for you?",
    "Ask me anything.",
    "Yes?",
    "I'm here.",
    "I'm listening.",
    "What would you like me to do?"]

chat_log=[
    {"role": "system", "content": "You are a helpful assistant."},
    ]

def ChatGPT(query):
    chat_log.append ({"role": "user", "content": query})
    response = openai.ChatCompletion.create(
    model=GPT_model,
    messages=chat_log
    )
    return str.strip(response['choices'][0]['message']['content'])
    chat_log.append({"role": "system", "content": response})

def responseprinter(chat):
    for word in chat:
       time.sleep(0.055)
       print(word, end="", flush=True)
    print()

#DaVinci will 'remember' earlier queries so that it has greater continuity in its response
#the following will delete that 'memory' five minutes after the start of the conversation
def append_clear_countdown():
    sleep(300)
    global chat_log
    chat_log.clear()
    chat_log=[
        {"role": "system", "content": "You are a helpful assistant."},
        ]    
    global count
    count = 0
    t_count.join

def voice(chat):
   
    voiceResponse = polly.synthesize_speech(Text=chat, OutputFormat="mp3",
                    VoiceId="Matthew") #other options include Amy, Joey, Nicole, Raveena and Russell
    if "AudioStream" in voiceResponse:
        with voiceResponse["AudioStream"] as stream:
            output_file = "speech.mp3"
            try:
                with open(output_file, "wb") as file:
                    file.write(stream.read())
            except IOError as error:
                print(error)

    else:
        print("did not work")

    pygame.mixer.init()     
    pygame.mixer.music.load(output_file)
#    pygame.mixer.music.set_volume(0.8) # uncomment to control the the playback volume (from 0.0 to 1.0  
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pass
    sleep(0.2)

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
        
def wake_word():

    porcupine = pvporcupine.create(keywords=["computer", "jarvis", "DaVinci",],
                            access_key=pv_access_key,
                            sensitivities=[0.1, 0.1, 0.1], #from 0 to 1.0 - a higher number reduces the miss rate at the cost of increased false alarms
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
            porcupine_audio_stream.stop_stream
            porcupine_audio_stream.close()
            porcupine.delete()         
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
            Detect = False

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
        enable_automatic_punctuation = True,
        )
    
    event = threading.Event()

    count = 0

    while True:
        
        try:
        
            if count == 0:
                t_count = threading.Thread(target=append_clear_countdown)
                t_count.start()
            else:
                pass   
            count += 1
            wake_word()
# comment out the next line if you do not want DaVinci to respond to his name        
            voice(random.choice(prompt))
            recorder = Recorder()
            recorder.start()
            listen()
            detect_silence()
            transcript, words = o.process(recorder.stop())
            t_fade = threading.Thread(target=fade_leds, args=(event,))
            t_fade.start()
            recorder.stop()
            print(transcript)
#            voice(transcript) # uncomment to have DaVinci repeat what it heard
            (res) = ChatGPT(transcript)
            print("\nChatGPT's response is:\n")        
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

        except openai.error.APIError as e:
            print("\nThere was an API error.  Please try again in a few minutes.")
            voice("\nThere was an A P I error.  Please try again in a few minutes.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)
            GPIO.output(led2_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)

        except openai.error.Timeout as e:
            print("\nYour request timed out.  Please try again in a few minutes.")
            voice("\nYour request timed out.  Please try again in a few minutes.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)
            GPIO.output(led2_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)

        except openai.error.Timeout as e:
            print("\nYour request timed out.  Please try again in a few minutes.")
            voice("\nYour request timed out.  Please try again in a few minutes.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)
            GPIO.output(led2_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)

        except openai.error.APIConnectionError as e:
            print("\nI am having trouble connecting to the API.  Please check your network connection and then try again.")
            voice("\nI am having trouble connecting to the A P I.  Please check your network connection and try again.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)
            GPIO.output(led2_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)

        except openai.error.AuthenticationError as e:
            print("\nYour OpenAI API key or token is invalid, expired, or revoked.  Please fix this issue and then restart my program.")
            voice("\nYour Open A I A P I key or token is invalid, expired, or revoked.  Please fix this issue and then restart my program.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)
            GPIO.output(led2_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            break

        except openai.error.ServiceUnavailableError as e:
            print("\nThere is an issue with OpenAI’s servers.  Please try again later.")
            voice("\nThere is an issue with Open A I’s servers.  Please try again later.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)
            GPIO.output(led2_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)
        
except KeyboardInterrupt:
    print("\nExiting ChatGPT Virtual Assistant")
    o.delete
    GPIO.cleanup()
