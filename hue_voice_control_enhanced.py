#!/usr/bin/env python3
import os
import time
import json
import speech_recognition as sr
from phue import Bridge
from dotenv import load_dotenv
import logging
import re
import threading
import queue
from collections import deque
import concurrent.futures
import subprocess
import struct
import pvporcupine
import datetime
import tempfile
from plyer import notification
from fuzzywuzzy import process
import pyaudio
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Bridge configuration
BRIDGE_IP = os.getenv("HUE_BRIDGE_IP")
CONFIG_FILE = "bridge_config.json"
WAKE_WORD = "philips"

# Wake word sensitivity (higher is more sensitive, range 0-1)
WAKE_WORD_SENSITIVITY = float(os.getenv("WAKE_WORD_SENSITIVITY", "0.5"))

# Room definitions for targeting specific rooms
ROOM_DEFINITIONS = {}

# Scene definitions
SCENE_DEFINITIONS = {}

# Command aliases for fuzzy matching
COMMAND_ALIASES = {
    "turn on": ["lights on", "switch on", "power on", "on", "activate lights"],
    "turn off": ["lights off", "switch off", "power off", "off", "deactivate lights"],
    "dim": ["lower", "darker", "reduce brightness", "less bright", "dimmer"],
    "brighten": ["brighter", "increase", "more light", "lighter", "more brightness"],
    "maximum": ["brightest", "full", "hundred percent", "max brightness"],
    "minimum": ["dimmest", "low", "lowest", "min brightness"],
    "undo": ["revert", "go back", "previous", "cancel"],
    "brightness": ["set to", "percent", "level", "intensity"]
}

def send_notification(title, message, timeout=2):
    """Send a desktop notification with fallback to console output"""
    try:
        # Check if we've previously determined notifications aren't working
        if hasattr(send_notification, 'available') and not send_notification.available:
            print(f"\n>>> {title}: {message} <<<\n")
            return
            
        # Try to send the notification
        notification.notify(
            title=title,
            message=message,
            timeout=timeout
        )
    except Exception as e:
        # Only log once
        if not hasattr(send_notification, 'logged_error'):
            logger.error(f"Error providing notification: {str(e)}")
            logger.info("Notifications disabled. Will use console output instead.")
            send_notification.logged_error = True
            
        # Fall back to console output
        print(f"\n>>> {title}: {message} <<<\n")
        send_notification.available = False

def play_sound(sound_type):
    """Play a system sound for audio feedback
    
    sound_type can be:
    - 'wake_word': When wake word is detected
    - 'command_recognized': When a command is successfully recognized
    - 'command_executed': After a command is executed
    - 'error': When there's an error or command not recognized
    """
    try:
        if os.name == 'posix':  # macOS or Linux
            sound_map = {
                'wake_word': '/System/Library/Sounds/Tink.aiff',
                'command_recognized': '/System/Library/Sounds/Morse.aiff',
                'command_executed': '/System/Library/Sounds/Bottle.aiff',
                'error': '/System/Library/Sounds/Basso.aiff',
                'timer': '/System/Library/Sounds/Glass.aiff'
            }
            
            sound_file = sound_map.get(sound_type, '/System/Library/Sounds/Tink.aiff')
            
            subprocess.Popen(['afplay', sound_file], 
                            stdout=subprocess.DEVNULL, 
                            stderr=subprocess.DEVNULL)
        elif os.name == 'nt':  # Windows
            # Import winsound only on Windows
            import winsound
            sound_map = {
                'wake_word': winsound.MB_OK,
                'command_recognized': winsound.MB_ICONASTERISK,
                'command_executed': winsound.MB_ICONINFORMATION,
                'error': winsound.MB_ICONHAND,
                'timer': winsound.MB_ICONEXCLAMATION
            }
            
            sound_type = sound_map.get(sound_type, winsound.MB_OK)
            winsound.MessageBeep(sound_type)
    except Exception as e:
        logger.debug(f"Could not play sound: {str(e)}")

def speak_text(text):
    """Convert text to speech for voice feedback
    
    Uses built-in 'say' command on macOS and pyttsx3 on Windows
    """
    try:
        if os.name == 'posix':  # macOS or Linux
            # Use the built-in 'say' command on macOS
            subprocess.Popen(['say', text], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
        elif os.name == 'nt':  # Windows
            # Try to use the pyttsx3 library on Windows if available
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
            except ImportError:
                logger.info(f"Text-to-speech: {text}")
        else:
            # Just log the text on unsupported platforms
            logger.info(f"Text-to-speech: {text}")
    except Exception as e:
        logger.error(f"Error with text-to-speech: {str(e)}")

class WakeWordListener(threading.Thread):
    """Thread for local wake word detection"""
    
    def __init__(self, command_queue, error_queue):
        threading.Thread.__init__(self)
        self.command_queue = command_queue
        self.error_queue = error_queue
        self.daemon = True
        self.running = True
        self.porcupine = None
        self.audio_stream = None
        self.audio_interface = None
        
    def run(self):
        """Main thread function for wake word detection"""
        try:
            # Try to initialize with custom keyword first
            custom_keyword_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                              f"{WAKE_WORD}_mac.ppn")
            
            if os.path.exists(custom_keyword_path):
                self.porcupine = pvporcupine.create(
                    keyword_paths=[custom_keyword_path],
                    sensitivities=[WAKE_WORD_SENSITIVITY]
                )
                logger.info(f"Using custom wake word model: {WAKE_WORD}")
            else:
                # Fall back to default keywords - handle case where KEYWORDS is a set
                try:
                    # Try to get available keywords
                    keywords = pvporcupine.KEYWORDS
                    
                    # Convert to list if it's a set or other iterable
                    if not isinstance(keywords, list):
                        keywords = list(keywords)
                    
                    # Find a suitable default keyword (prefer jarvis, computer, or porcupine)
                    default_options = ["jarvis", "computer", "porcupine", "hey siri", "alexa"]
                    selected_keyword = None
                    
                    for option in default_options:
                        if option in keywords:
                            selected_keyword = option
                            break
                    
                    # If none of the preferred options are available, use the first available keyword
                    if not selected_keyword and keywords:
                        selected_keyword = keywords[0]
                    
                    if selected_keyword:
                        self.porcupine = pvporcupine.create(
                            keywords=[selected_keyword],
                            sensitivities=[WAKE_WORD_SENSITIVITY]
                        )
                        logger.info(f"Using default wake word '{selected_keyword}' because '{WAKE_WORD}' model not found")
                    else:
                        raise ValueError("No keywords available in Porcupine")
                        
                except Exception as e:
                    # Handle any issues with keyword detection by using a built-in keyword directly
                    logger.error(f"Error setting up wake word: {str(e)}")
                    logger.info("Attempting to use 'porcupine' as fallback wake word")
                    
                    try:
                        self.porcupine = pvporcupine.create(
                            keywords=["porcupine"],
                            sensitivities=[WAKE_WORD_SENSITIVITY]
                        )
                        logger.info("Using 'porcupine' as fallback wake word")
                    except Exception as e2:
                        logger.error(f"Failed to initialize with fallback keyword: {str(e2)}")
                        raise
            
            # Open audio stream
            self.audio_interface = pyaudio.PyAudio()
            self.audio_stream = self.audio_interface.open(
                rate=self.porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.porcupine.frame_length
            )
            
            logger.info(f"Wake word detector started. Listening for wake word...")
            
            # Main detection loop
            while self.running:
                pcm = self.audio_stream.read(self.porcupine.frame_length)
                pcm = struct.unpack_from("h" * self.porcupine.frame_length, pcm)
                
                keyword_index = self.porcupine.process(pcm)
                
                if keyword_index >= 0:
                    # Wake word detected
                    logger.info("Wake word detected!")
                    self.command_queue.put({"type": "wake_word_detected"})
                    # Provide audible feedback
                    self.provide_feedback()
                    
            # Clean up
            if self.audio_stream:
                self.audio_stream.close()
            if self.audio_interface:
                self.audio_interface.terminate()
            if self.porcupine:
                self.porcupine.delete()
                
        except Exception as e:
            logger.error(f"Error in wake word detection: {str(e)}")
            self.error_queue.put(e)
    
    def provide_feedback(self):
        """Provide audible feedback that wake word was detected"""
        try:
            # Play a subtle sound to indicate wake word detection
            play_sound('wake_word')
        except Exception as e:
            logger.error(f"Error providing feedback: {str(e)}")
    
    def stop(self):
        """Stop the thread"""
        self.running = False


class ThreadedMicrophone(threading.Thread):
    """Thread class for handling microphone input after wake word detection"""
    
    def __init__(self, recognizer, audio_queue, error_queue, command_queue):
        threading.Thread.__init__(self)
        self.recognizer = recognizer
        self.audio_queue = audio_queue
        self.error_queue = error_queue
        self.command_queue = command_queue
        self.daemon = True
        self.running = True
        self.listening_active = False
        
    def activate_listening(self):
        """Activate listening after wake word detection"""
        self.listening_active = True
        # Start a timer to automatically deactivate listening after 10 seconds of silence
        threading.Timer(10.0, self.deactivate_listening).start()
        
    def deactivate_listening(self):
        """Deactivate listening if no speech detected"""
        if self.listening_active:
            self.listening_active = False
            logger.info("Listening timeout - returning to wake word detection")
        
    def run(self):
        """Thread function for microphone listening"""
        with sr.Microphone() as source:
            logger.info("Calibrating for ambient noise in microphone thread...")
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
            logger.info("Microphone thread ready and waiting for wake word trigger...")
            
            while self.running:
                try:
                    # Only listen actively after wake word detection
                    if self.listening_active:
                        logger.info("Actively listening for command...")
                        try:
                            audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=5)
                            self.audio_queue.put(audio)
                            # Deactivate listening after getting audio
                            self.listening_active = False
                        except sr.WaitTimeoutError:
                            # Timed out without hearing anything
                            self.deactivate_listening()
                    else:
                        # Don't busy-wait when not actively listening
                        time.sleep(0.1)
                        
                except Exception as e:
                    self.error_queue.put(e)
                    
    def stop(self):
        """Stop the thread"""
        self.running = False


class ThreadedRecognizer(threading.Thread):
    """Thread class for handling speech recognition"""
    
    def __init__(self, recognizer, audio_queue, command_queue, error_queue):
        threading.Thread.__init__(self)
        self.recognizer = recognizer
        self.audio_queue = audio_queue
        self.command_queue = command_queue
        self.error_queue = error_queue
        self.daemon = True
        self.running = True
        
        # Cache recent commands to avoid duplicates (debouncing)
        self.recent_commands = deque(maxlen=5)
        
    def run(self):
        """Thread function for speech recognition"""
        logger.info("Speech recognition thread started")
        
        while self.running:
            try:
                if not self.audio_queue.empty():
                    audio = self.audio_queue.get(block=False)
                    
                    # Process in a separate thread from the thread pool
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(self.process_audio, audio)
                        # Wait for a result but with a timeout to avoid blocking
                        try:
                            result = future.result(timeout=5)
                            if result:
                                text, confidence = result
                                
                                # Only process if confidence is high and not a recent duplicate
                                if confidence > 0.7 and text not in self.recent_commands:
                                    self.recent_commands.append(text)
                                    # No need to check for wake word as that's done by the wake word detector
                                    self.command_queue.put({"type": "command", "text": text})
                                    logger.info(f"Command recognized: {text} (confidence: {confidence:.2f})")
                                    # Provide visual feedback
                                    self.provide_feedback(f"Command: {text}")
                                elif confidence <= 0.7:
                                    logger.info(f"Low confidence recognition: {text} ({confidence:.2f})")
                        except concurrent.futures.TimeoutError:
                            logger.warning("Recognition timed out")
                
                else:
                    # Don't busy-wait, sleep for a short time if no audio
                    time.sleep(0.1)
                    
            except queue.Empty:
                time.sleep(0.1)
            except Exception as e:
                self.error_queue.put(e)
                
    def process_audio(self, audio):
        """Process audio to text with confidence score"""
        try:
            # Use Google's recognizer with show_all=True to get confidence scores
            result = self.recognizer.recognize_google(audio, show_all=True)
            
            if result and 'alternative' in result and len(result['alternative']) > 0:
                best_guess = result['alternative'][0]
                text = best_guess['transcript'].lower()
                
                # Get confidence score if available, otherwise default to 1.0
                confidence = best_guess.get('confidence', 1.0)
                
                # Play sound for command recognition
                play_sound('command_recognized')
                
                # Read back the recognized command
                speak_text(f"I heard: {text}")
                
                return text, confidence
                
            return None
            
        except sr.UnknownValueError:
            logger.info("Could not understand audio")
            play_sound('error')
            speak_text("Sorry, I couldn't understand the command")
            return None
        except sr.RequestError as e:
            logger.error(f"Error with speech recognition service: {str(e)}")
            play_sound('error')
            speak_text("Sorry, I couldn't reach the speech recognition service")
            return None
        except Exception as e:
            logger.error(f"Error processing audio: {str(e)}")
            self.error_queue.put(e)
            return None
    
    def provide_feedback(self, message):
        """Provide visual feedback for recognized commands"""
        send_notification("Hue Voice Control", message)
    
    def stop(self):
        """Stop the thread"""
        self.running = False


class CommandProcessor(threading.Thread):
    """Thread for processing voice commands"""
    
    def __init__(self, command_queue, error_queue, bridge):
        threading.Thread.__init__(self)
        self.command_queue = command_queue
        self.error_queue = error_queue
        self.bridge = bridge
        self.daemon = True
        self.running = True
        
        # Maintain cache of lights to avoid repeated API calls
        self.lights_cache = {}
        self.last_cache_update = 0
        self.cache_ttl = 60  # Cache for 60 seconds
        
        # Store command history
        self.command_history = deque(maxlen=10)
        
        # Store light states for undo functionality
        self.light_state_history = deque(maxlen=5)
        
        # Store active timers
        self.active_timers = {}
        
    def run(self):
        """Thread function for command processing"""
        logger.info("Command processor thread started")
        
        while self.running:
            try:
                if not self.command_queue.empty():
                    command_data = self.command_queue.get(block=False)
                    
                    # Handle different command types
                    if isinstance(command_data, dict):
                        if command_data["type"] == "wake_word_detected":
                            # Wake word detected, nothing to do here as the microphone
                            # thread will be activated separately
                            pass
                        elif command_data["type"] == "command":
                            # Process actual voice command
                            self.process_command(command_data["text"])
                        elif command_data["type"] == "timer":
                            # Process timer expiration
                            self.process_timer_expiration(command_data["timer_id"], command_data["action"])
                    else:
                        # Legacy format, plain text command
                        self.process_command(command_data)
                else:
                    # Don't busy-wait, sleep for a short time if no commands
                    time.sleep(0.1)
                    
            except queue.Empty:
                time.sleep(0.1)
            except Exception as e:
                self.error_queue.put(e)
                
    def get_specific_lights(self, command, refresh_cache=False):
        """Get all available lights with caching"""
        current_time = time.time()
        
        # Refresh cache if needed
        if refresh_cache or not self.lights_cache or (current_time - self.last_cache_update) > self.cache_ttl:
            try:
                all_lights = self.bridge.get_light_objects('name')
                self.lights_cache = all_lights
                self.last_cache_update = current_time
            except Exception as e:
                logger.error(f"Error refreshing lights cache: {str(e)}")
                # If we can't refresh but have a cache, use the old cache
                if not self.lights_cache:
                    raise e
        
        # Return all lights
        logger.info(f"Controlling all available lights ({len(self.lights_cache)} found)")
        return list(self.lights_cache.values())
    
    def save_light_state(self, lights):
        """Save the current state of lights for undo functionality"""
        states = {}
        for light in lights:
            try:
                # Start with basic properties that all lights have
                state = {
                    "on": light.on,
                    "name": light.name
                }
                
                # Get the light type and capabilities from the bridge
                light_id = light.light_id
                light_type = None
                
                # Try to get light details from bridge
                try:
                    light_details = self.bridge.get_light(light_id)
                    if 'type' in light_details:
                        light_type = light_details['type']
                except Exception as e:
                    logger.debug(f"Could not get light type for {light.name}: {str(e)}")
                
                # Check if this is a color-capable light based on type
                is_color_light = False
                if light_type and any(color_type in light_type.lower() for color_type in ['color', 'rgb', 'extended color']):
                    is_color_light = True
                
                # Save brightness if light supports it
                try:
                    # Safely try to access brightness (most lights support this)
                    brightness = light.brightness
                    state["brightness"] = brightness
                except Exception as e:
                    logger.debug(f"Light {light.name} doesn't support brightness: {str(e)}")
                
                # Only try to save color information for lights we know support color
                if is_color_light:
                    try:
                        xy_value = light.xy
                        state["xy"] = xy_value
                    except Exception as e:
                        logger.debug(f"Error accessing xy for {light.name}: {str(e)}")
                
                states[light.name] = state
            except Exception as e:
                logger.error(f"Error saving light state: {str(e)}")
        
        if states:
            self.light_state_history.append(states)
            return True
        return False
                
    def process_command(self, command):
        """Process voice commands and control the lights"""
        if not self.bridge:
            logger.error("Bridge not connected")
            return
            
        # Add to command history
        self.command_history.append(command)
        
        # Check for command chains (commands separated by "and" or "then")
        commands = re.split(r'\s+and\s+|\s+then\s+', command)
        
        if len(commands) > 1:
            logger.info(f"Processing command chain: {commands}")
            for single_command in commands:
                self._process_single_command(single_command.strip())
        else:
            self._process_single_command(command)
    
    def _process_single_command(self, command):
        """Process a single command"""
        try:
            # Get target lights before making any changes
            targeted_lights = self.get_specific_lights(command)
            
            # Save current state for undo functionality
            self.save_light_state(targeted_lights)
            
            # Check for timer command
            timer_match = re.search(r'(in|after)\s+(\d+)\s+(second|minute|hour)s?', command)
            if timer_match:
                amount = int(timer_match.group(2))
                unit = timer_match.group(3)
                
                # Extract what to do after the timer
                action = command.split(timer_match.group(0))[1].strip()
                
                if action:
                    self.start_timer(amount, unit, action)
                    return
            
            # Check for undo command
            if any(word in command for word in COMMAND_ALIASES["undo"]):
                self.undo_last_command()
                return
                
            # Check for brightness percentage command
            brightness_match = re.search(r'(\d+)\s*percent', command)
            if brightness_match:
                brightness_percent = int(brightness_match.group(1))
                brightness_value = int((brightness_percent / 100) * 254)
                logger.info(f"Setting brightness to {brightness_percent}%")
                for light in targeted_lights:
                    light.on = True
                    light.brightness = brightness_value
                return
                
            # Use fuzzy matching for other commands
            matched_command = self.match_command(command)
            if matched_command:
                matched_command(targeted_lights, command)
            else:
                logger.info(f"Command '{command}' not recognized")
                
        except Exception as e:
            logger.error(f"Error processing command: {str(e)}")
            # Refresh the cache on error
            self.lights_cache = {}
    
    def match_command(self, command_text):
        """Match command text to command handlers using fuzzy matching"""
        command_handlers = {
            "turn on": self.turn_on_lights,
            "turn off": self.turn_off_lights,
            "dim": self.dim_lights,
            "brighten": self.brighten_lights,
            "maximum": self.maximum_brightness,
            "minimum": self.minimum_brightness
        }
        
        # Create a dictionary of all commands with their aliases
        all_commands = {}
        for cmd, handler in command_handlers.items():
            all_commands[cmd] = handler
            for alias in COMMAND_ALIASES.get(cmd, []):
                all_commands[alias] = handler
                
        # Find the best match
        best_match = None
        highest_score = 0
        
        for cmd_text in all_commands.keys():
            if cmd_text in command_text:
                # Direct substring match
                return all_commands[cmd_text]
                
        # No direct match, try fuzzy matching
        for cmd_text, handler in all_commands.items():
            # Calculate similarity score
            score = process.extractOne(command_text, [cmd_text])
            if score and score[1] > highest_score and score[1] > 70:
                highest_score = score[1]
                best_match = handler
                
        return best_match
    
    def turn_on_lights(self, lights, command=None):
        """Turn lights on"""
        logger.info("Turning lights ON")
        for light in lights:
            light.on = True
        play_sound('command_executed')
        speak_text("Turning the lights on")
    
    def turn_off_lights(self, lights, command=None):
        """Turn lights off"""
        logger.info("Turning lights OFF")
        for light in lights:
            light.on = False
        play_sound('command_executed')
        speak_text("Turning the lights off")
    
    def dim_lights(self, lights, command=None):
        """Dim the lights by 20%"""
        logger.info("Dimming lights")
        
        for light in lights:
            # Only dim if the light is on
            if light.on:
                current_brightness = getattr(light, 'brightness', 254)
                # Don't go below 1
                new_brightness = max(1, int(current_brightness * 0.8))
                light.brightness = new_brightness
        play_sound('command_executed')
        speak_text("Dimming the lights")
                
    def brighten_lights(self, lights, command=None):
        """Brighten the lights by 20%"""
        logger.info("Brightening lights")
        
        for light in lights:
            # Only brighten if the light is on
            if light.on:
                current_brightness = getattr(light, 'brightness', 128)
                # Don't exceed 254
                new_brightness = min(254, int(current_brightness * 1.2))
                light.brightness = new_brightness
        play_sound('command_executed')
        speak_text("Brightening the lights")
                
    def maximum_brightness(self, lights, command=None):
        """Set lights to maximum brightness"""
        logger.info("Setting lights to maximum brightness")
        
        for light in lights:
            light.on = True
            light.brightness = 254
        play_sound('command_executed')
        speak_text("Setting lights to maximum brightness")
                
    def minimum_brightness(self, lights, command=None):
        """Set lights to minimum brightness"""
        logger.info("Setting lights to minimum brightness")
        
        for light in lights:
            light.on = True
            light.brightness = 1
        play_sound('command_executed')
        speak_text("Setting lights to minimum brightness")
    
    def undo_last_command(self):
        """Undo the last light change"""
        if not self.light_state_history:
            logger.info("No previous state to restore")
            play_sound('error')
            speak_text("Sorry, I don't have any previous state to restore")
            return False
            
        # Get the previous light state
        previous_state = self.light_state_history.pop()
        logger.info("Undoing last command")
        
        # Restore previous state
        for light_name, state in previous_state.items():
            try:
                # Find the light by name
                for name, light in self.lights_cache.items():
                    if name == light_name:
                        # Only set properties that were saved
                        if "on" in state:
                            light.on = state["on"]
                        
                        if "brightness" in state and state["brightness"] is not None:
                            try:
                                light.brightness = state["brightness"]
                            except Exception as e:
                                logger.debug(f"Could not restore brightness for {light_name}: {str(e)}")
                        
                        if "xy" in state and state["xy"] is not None:
                            try:
                                light.xy = state["xy"]
                            except Exception as e:
                                logger.debug(f"Could not restore color for {light_name}: {str(e)}")
                        
                        break
            except Exception as e:
                logger.error(f"Error restoring light state: {str(e)}")
        
        play_sound('command_executed')
        speak_text("Undoing the previous command")
        return True
    
    def start_timer(self, amount, unit, action):
        """Start a timer and execute an action when it expires"""
        # Convert to seconds
        seconds = amount
        if unit == "minute":
            seconds = amount * 60
        elif unit == "hour":
            seconds = amount * 60 * 60
            
        # Generate a unique timer ID
        timer_id = f"timer_{int(time.time())}_{amount}_{unit}"
        
        # Log the timer
        timer_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        logger.info(f"Timer set for {amount} {unit}(s) at {timer_time.strftime('%H:%M:%S')} - Action: {action}")
        
        # Provide feedback
        send_notification("Hue Voice Control", f"Timer set: {amount} {unit}(s) for '{action}'")
        
        # Create and start the timer
        timer = threading.Timer(
            seconds, 
            self.timer_expired,
            args=[timer_id, action]
        )
        self.active_timers[timer_id] = {
            "timer": timer,
            "action": action,
            "expires": timer_time
        }
        timer.daemon = True
        timer.start()
        
        return timer_id
    
    def timer_expired(self, timer_id, action):
        """Handle timer expiration"""
        logger.info(f"Timer {timer_id} expired. Executing: {action}")
        
        # Remove from active timers
        if timer_id in self.active_timers:
            del self.active_timers[timer_id]
            
        # Put the action in the command queue
        self.command_queue.put({
            "type": "timer", 
            "timer_id": timer_id,
            "action": action
        })
        
        # Play timer sound
        play_sound('timer')
        
        # Provide notification
        send_notification("Hue Voice Control - Timer", f"Timer expired: {action}", 5)
    
    def process_timer_expiration(self, timer_id, action):
        """Process a timer expiration by executing the associated action"""
        logger.info(f"Timer expired: {action}")
        
        # Play timer sound
        play_sound('timer')
        
        # Announce timer expiration
        speak_text(f"Timer expired. {action}")
        
        # Process the action as a command
        self.process_command(action)
        
        # Provide notification
        send_notification("Hue Voice Control - Timer", f"Timer expired: {action}", 5)
            
    def stop(self):
        """Stop the thread"""
        self.running = False
        
        # Cancel active timers
        for timer_id, timer_data in list(self.active_timers.items()):
            if timer_data["timer"].is_alive():
                timer_data["timer"].cancel()
                logger.info(f"Canceled timer: {timer_id}")


class MicrophoneThread(threading.Thread):
    """Thread for continuous listening through the microphone"""
    
    def __init__(self, command_queue, error_queue):
        threading.Thread.__init__(self)
        self.command_queue = command_queue
        self.error_queue = error_queue
        self.daemon = True
        self.running = True
        self.recognizer = sr.Recognizer()
        
    def run(self):
        """Main thread function for microphone input"""
        try:
            # Set up speech recognition
            with sr.Microphone() as source:
                logger.info("Calibrating for ambient noise in microphone thread...")
                self.recognizer.adjust_for_ambient_noise(source, duration=2)
                logger.info("Microphone thread ready and waiting for wake word trigger...")
                
                # Continuously listen for commands
                while self.running:
                    try:
                        logger.info("Actively listening for command...")
                        audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=5)
                        self.process_audio(audio)
                    except sr.WaitTimeoutError:
                        # Timeout is normal, just continue
                        continue
        except Exception as e:
            logger.error(f"Error in microphone thread: {str(e)}")
            self.error_queue.put(e)
    
    def process_audio(self, audio):
        """Process captured audio and send to command queue"""
        try:
            # Use Google Speech Recognition as it's more accurate
            text = self.recognizer.recognize_google(audio)
            
            if text:
                # Calculate a basic confidence score (this is approximate)
                confidence = 0.8  # Default confidence value
                
                logger.info(f"Command recognized: {text} (confidence: {confidence})")
                
                # Play sound for command recognition
                play_sound('command_recognized')
                
                # Read back the recognized command
                speak_text(f"I heard: {text}")
                
                # Send the recognized text to the command queue
                self.command_queue.put(text)
                
                # Provide visual feedback
                send_notification("Hue Voice Control", f"Command: {text}")
        except sr.UnknownValueError:
            # This is normal when no speech is detected
            pass
        except sr.RequestError as e:
            logger.error(f"Error with speech recognition service: {str(e)}")
            play_sound('error')
            speak_text("Sorry, I couldn't reach the speech recognition service")
        except Exception as e:
            logger.error(f"Error processing audio: {str(e)}")
            self.error_queue.put(e)
    
    def stop(self):
        """Stop the thread"""
        self.running = False


class SpeechRecognizer(threading.Thread):
    """Dummy thread for compatibility with the fallback mode architecture"""
    
    def __init__(self, command_queue, error_queue):
        threading.Thread.__init__(self)
        self.command_queue = command_queue
        self.error_queue = error_queue
        self.daemon = True
        self.running = True
    
    def run(self):
        """This thread doesn't do much in fallback mode as MicrophoneThread handles recognition"""
        try:
            # Just keep the thread alive
            while self.running:
                time.sleep(1)
        except Exception as e:
            logger.error(f"Error in speech recognizer thread: {str(e)}")
            self.error_queue.put(e)
    
    def stop(self):
        """Stop the thread"""
        self.running = False


class HueVoiceControl:
    """Main controller class for Hue Voice Control"""
    
    def __init__(self):
        """Initialize the controller"""
        self.bridge = None
        self.running = True
        self.mic_thread = None
        self.wake_thread = None
        self.recognizer_thread = None
        self.processor_thread = None
        
        # Initialize queues for inter-thread communication
        self.command_queue = queue.Queue()
        self.error_queue = queue.Queue()
        
        # Connect to the bridge
        self.connect_to_bridge()

    def connect_to_bridge(self):
        """Connect to the Hue Bridge"""
        try:
            ip_address = BRIDGE_IP
            
            # Try to connect using config file first
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    if 'bridge_ip' in config:
                        ip_address = config['bridge_ip']
            
            # Connect to the bridge
            self.bridge = Bridge(ip_address)
            
            # Try to connect with existing username
            try:
                self.bridge.connect()
                logger.info("Connected to Hue Bridge using saved credentials")
                
                # Save the configuration
                if not os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, 'w') as f:
                        json.dump({'bridge_ip': ip_address}, f)
                
                return True
            except Exception as e:
                logger.error(f"Error connecting to Hue Bridge: {str(e)}")
                
                # If first connection, we need to press the link button on the bridge
                logger.info("If this is your first time connecting, press the link button on the Hue Bridge and run the program again.")
                return False
                
        except Exception as e:
            logger.error(f"Error connecting to Hue Bridge: {str(e)}")
            return False

    def start(self):
        """Start all the worker threads"""
        if not self.bridge:
            logger.error("Cannot start - Bridge not connected")
            return False
        
        try:
            # Create and start the wake word detection thread
            self.wake_thread = WakeWordListener(
                self.command_queue,
                self.error_queue
            )
            self.wake_thread.start()
            
            # Create and start the microphone thread
            self.mic_thread = ThreadedMicrophone(
                self.recognizer, 
                self.audio_queue,
                self.error_queue,
                self.command_queue
            )
            self.mic_thread.start()
            
            # Create and start the recognizer thread
            self.recognizer_thread = ThreadedRecognizer(
                self.recognizer,
                self.audio_queue,
                self.command_queue,
                self.error_queue
            )
            self.recognizer_thread.start()
            
            # Create and start the command processor thread
            self.processor_thread = CommandProcessor(
                self.command_queue,
                self.error_queue,
                self.bridge
            )
            self.processor_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Error starting threads: {str(e)}")
            self.stop()
            return False
    
    def stop(self):
        """Stop all threads and cleanup"""
        logger.info("Stopping Hue Voice Control...")
        
        # Stop the threads
        if self.wake_thread and self.wake_thread.is_alive():
            self.wake_thread.stop()
            
        if self.mic_thread and self.mic_thread.is_alive():
            self.mic_thread.stop()
            
        if self.recognizer_thread and self.recognizer_thread.is_alive():
            self.recognizer_thread.stop()
            
        if self.processor_thread and self.processor_thread.is_alive():
            self.processor_thread.stop()
        
        logger.info("All threads stopped")
    
    def run(self):
        """Main run method"""
        logger.info("Starting Enhanced Hue Voice Control")
        logger.info(f"Wake word: '{WAKE_WORD}' (say this to activate voice recognition)")
        
        if not self.start():
            return
            
        # Main thread just monitors for errors and keeps the program running
        try:
            while True:
                # Check for errors from threads
                if not self.error_queue.empty():
                    error = self.error_queue.get(block=False)
                    logger.error(f"Error from thread: {str(error)}")
                
                # Check for wake word detection and activate mic thread
                if not self.command_queue.empty():
                    try:
                        command_data = self.command_queue.get(block=False, timeout=0.1)
                        if isinstance(command_data, dict) and command_data.get("type") == "wake_word_detected":
                            # Wake word detected, activate microphone for command
                            self.mic_thread.activate_listening()
                            # Put the command data back for the processor to handle
                            self.command_queue.put(command_data)
                    except queue.Empty:
                        pass
                    except Exception as e:
                        logger.error(f"Error handling command queue: {str(e)}")
                
                # Check if threads are still running
                if (not self.wake_thread.is_alive() or
                    not self.mic_thread.is_alive() or 
                    not self.recognizer_thread.is_alive() or 
                    not self.processor_thread.is_alive()):
                    logger.error("One or more threads have stopped unexpectedly")
                    # Attempt to restart
                    self.stop()
                    if not self.start():
                        break
                
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()

    def start_fallback_mode(self):
        """Start processing in fallback mode without wake word detection"""
        try:
            # Skip wake word detection completely in fallback mode
            
            # Create speech recognition and command threads
            self.mic_thread = MicrophoneThread(self.command_queue, self.error_queue)
            self.recognizer_thread = SpeechRecognizer(self.command_queue, self.error_queue)
            self.processor_thread = CommandProcessor(self.command_queue, self.error_queue, self.bridge)
            
            # Log status
            logger.info("Initializing fallback mode (without wake word detection)")
            
            # Start threads
            self.processor_thread.start()
            self.recognizer_thread.start()
            self.mic_thread.start()
            
            # Initialize and start threads
            logger.info("Speech recognition thread started")
            logger.info("Command processor thread started")
            
            return True
        except Exception as e:
            logger.error(f"Error starting fallback mode: {str(e)}")
            return False
    
    def run_fallback_mode(self):
        """Run in fallback mode without wake word detection"""
        try:
            logger.info("="*50)
            logger.info("Enhanced Philips Hue Voice Control")
            logger.info("="*50)
            logger.info("FALLBACK MODE - No wake word needed")
            logger.info("Voice commands will be processed continuously")
            logger.info("New features:")
            logger.info("- Audio feedback for commands")
            logger.info("- Voice readback of commands and actions")
            logger.info("- Command chaining (e.g. 'turn on lights and set to 50 percent')")
            logger.info("- Undo functionality (say 'undo' or 'revert')")
            logger.info("- Timer support (e.g. 'in 5 minutes turn off lights')")
            logger.info("- Desktop notifications for feedback")
            logger.info("="*50)
            
            # Connect to the bridge
            if not self.connect_to_bridge():
                logger.error("Could not connect to Hue Bridge. Check your IP address and try again.")
                speak_text("Could not connect to the Hue Bridge. Please check your connection.")
                return False
            
            logger.info("Successfully connected to Hue Bridge!")
            
            # Start processing in fallback mode
            if not self.start_fallback_mode():
                logger.error("Failed to start fallback mode")
                speak_text("Failed to start the system. Please try again.")
                return False
            
            # Play a sound to indicate successful startup
            play_sound('command_executed')
            speak_text("Philips Hue voice control is ready. You can speak commands directly.")
            
            # Keep running until explicitly stopped
            try:
                while self.running:
                    # Check for thread errors
                    if not self.error_queue.empty():
                        error = self.error_queue.get(block=False)
                        logger.error(f"Error from thread: {str(error)}")
                    
                    # Sleep to avoid busy-waiting
                    time.sleep(0.5)
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received, shutting down...")
                speak_text("Shutting down. Goodbye!")
            finally:
                self.stop()
                
            return True
            
        except Exception as e:
            logger.error(f"Error in fallback mode: {str(e)}")
            return False


def main():
    """Main entry point for the application"""
    try:
        # Parse command line arguments
        fallback_mode = "--fallback" in sys.argv
        
        # Define wake word at global scope to avoid reference errors
        global WAKE_WORD
        
        logger.info("="*50)
        logger.info("Enhanced Philips Hue Voice Control")
        logger.info("="*50)
        
        if fallback_mode:
            logger.info("Starting in FALLBACK MODE without wake word detection")
            logger.info("Voice commands will be processed continuously")
            
            # Create controller and run in fallback mode directly
            hue_controller = HueVoiceControl()
            hue_controller.run_fallback_mode()
        else:
            # Only try wake word detection in regular mode
            logger.info(f"Wake word: '{WAKE_WORD}'")
            logger.info("Say the wake word to activate voice recognition")
            logger.info("New features:")
            logger.info("- Local wake word detection")
            logger.info("- Command chaining (e.g. 'turn on lights and set to 50 percent')")
            logger.info("- Undo functionality (say 'undo' or 'revert')")
            logger.info("- Timer support (e.g. 'in 5 minutes turn off lights')")
            logger.info("- Desktop notifications for feedback")
            logger.info("="*50)
            
            try:
                hue_controller = HueVoiceControl()
                hue_controller.run()
            except Exception as e:
                logger.error(f"Error setting up wake word: {str(e)}")
                logger.error("The wake word detection API now requires an access key.")
                logger.info("Running in fallback mode instead...")
                
                # Run in fallback mode as a backup
                hue_controller = HueVoiceControl()
                hue_controller.run_fallback_mode()
                
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        logger.info("Try running with --fallback flag to bypass wake word detection:")
        logger.info("python hue_voice_control_enhanced.py --fallback")
        return 1
                
    return 0


if __name__ == "__main__":
    main() 