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

class ThreadedMicrophone(threading.Thread):
    """Thread class for handling microphone input"""
    
    def __init__(self, recognizer, audio_queue, error_queue):
        threading.Thread.__init__(self)
        self.recognizer = recognizer
        self.audio_queue = audio_queue
        self.error_queue = error_queue
        self.daemon = True
        self.running = True
        
    def run(self):
        """Thread function for microphone listening"""
        with sr.Microphone() as source:
            logger.info("Calibrating for ambient noise in microphone thread...")
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
            logger.info("Microphone thread listening for commands...")
            
            while self.running:
                try:
                    audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=5)
                    self.audio_queue.put(audio)
                except sr.WaitTimeoutError:
                    pass
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
        logger.info(f"Wake word activated: Say '{WAKE_WORD}' before commands")
        
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
                                
                                # Check if wake word is present at the beginning of the command
                                if text.lower().startswith(WAKE_WORD):
                                    # Extract the actual command (everything after the wake word)
                                    command = text[len(WAKE_WORD):].strip()
                                    
                                    # Only process if there's an actual command after the wake word
                                    # and confidence is high and not a recent duplicate
                                    if command and confidence > 0.7 and command not in self.recent_commands:
                                        self.recent_commands.append(command)
                                        self.command_queue.put(command)
                                        logger.info(f"Wake word detected! Processing: {command} (confidence: {confidence:.2f})")
                                    elif confidence <= 0.7:
                                        logger.info(f"Low confidence recognition: {text} ({confidence:.2f})")
                                    elif not command:
                                        logger.info(f"Wake word detected, but no command followed")
                                else:
                                    # Wake word not detected, log but don't process
                                    logger.info(f"Ignored (no wake word): {text}")
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
                
                return text, confidence
                
            return None
            
        except sr.UnknownValueError:
            logger.info("Could not understand audio")
            return None
        except sr.RequestError as e:
            logger.error(f"Error with speech recognition service: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error processing audio: {str(e)}")
            return None
                
    def stop(self):
        """Stop the thread"""
        self.running = False


class CommandProcessor(threading.Thread):
    """Thread class for processing voice commands"""
    
    def __init__(self, bridge, command_queue, error_queue):
        threading.Thread.__init__(self)
        self.bridge = bridge
        self.command_queue = command_queue
        self.error_queue = error_queue
        self.daemon = True
        self.running = True
        
        # Cache light states to reduce Bridge API calls
        self.lights_cache = {}
        self.last_cache_update = 0
        self.cache_ttl = 5  # Seconds
        
    def run(self):
        """Thread function for command processing"""
        logger.info("Command processor thread started")
        
        while self.running:
            try:
                if not self.command_queue.empty():
                    command = self.command_queue.get(block=False)
                    self.process_command(command)
                else:
                    # Don't busy-wait, sleep for a short time if no commands
                    time.sleep(0.1)
                    
            except queue.Empty:
                time.sleep(0.1)
            except Exception as e:
                self.error_queue.put(e)
                
    def get_specific_lights(self, command, refresh_cache=False):
        """Get living room lights with caching"""
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
        
        # Find all living room lights
        living_room_lights = [light for name, light in self.lights_cache.items() 
                             if 'living' in name.lower() or 'room' in name.lower()]
        
        if not living_room_lights:
            # If no living room lights found, use all lights
            logger.info("No living room lights found, using all available lights")
            return list(self.lights_cache.values())
        
        logger.info(f"Using living room lights ({len(living_room_lights)} found)")
        return living_room_lights
                
    def process_command(self, command):
        """Process voice commands and control the lights"""
        if not self.bridge:
            logger.error("Bridge not connected")
            return
            
        # Process the command
        try:
            targeted_lights = self.get_specific_lights(command)
            
            # Check for brightness percentage command
            brightness_match = re.search(r'(\d+)\s*percent', command)
            if brightness_match:
                brightness_percent = int(brightness_match.group(1))
                brightness_value = int((brightness_percent / 100) * 254)
                logger.info(f"Setting brightness to {brightness_percent}%")
                for light in targeted_lights:
                    light.brightness = brightness_value
                return
                
            # Process the command
            if any(phrase in command for phrase in ["turn on", "lights on", "switch on", "power on"]):
                logger.info("Turning lights ON")
                for light in targeted_lights:
                    light.on = True
                    
            elif any(phrase in command for phrase in ["turn off", "lights off", "switch off", "power off"]):
                logger.info("Turning lights OFF")
                for light in targeted_lights:
                    light.on = False
                    
            elif any(phrase in command for phrase in ["dim", "lower", "darker", "reduce brightness", "less bright"]):
                logger.info("Dimming lights")
                # Determine intensity of dimming
                dim_amount = 64  # Default amount
                
                if "little" in command or "bit" in command or "slightly" in command:
                    dim_amount = 25
                elif "lot" in command or "much" in command or "significantly" in command:
                    dim_amount = 100
                
                for light in targeted_lights:
                    if light.on:
                        light.brightness = max(light.brightness - dim_amount, 1)
                    
            elif any(phrase in command for phrase in ["brighten", "brighter", "increase", "more light", "lighter"]):
                logger.info("Brightening lights")
                # Determine intensity of brightening
                brighten_amount = 64  # Default amount
                
                if "little" in command or "bit" in command or "slightly" in command:
                    brighten_amount = 25
                elif "lot" in command or "much" in command or "significantly" in command:
                    brighten_amount = 100
                
                for light in targeted_lights:
                    if light.on:
                        light.brightness = min(light.brightness + brighten_amount, 254)
                    else:
                        # If light is off, turn it on at low brightness
                        light.on = True
                        light.brightness = brighten_amount
                    
            elif "maximum" in command or "brightest" in command or "full" in command:
                logger.info("Setting lights to maximum brightness")
                for light in targeted_lights:
                    light.on = True
                    light.brightness = 254
                    
            elif "minimum" in command or "dimmest" in command:
                logger.info("Setting lights to minimum brightness")
                for light in targeted_lights:
                    light.on = True
                    light.brightness = 1
                
            else:
                logger.info(f"Command '{command}' not recognized")
                
        except Exception as e:
            logger.error(f"Error processing command: {str(e)}")
            # Refresh the cache on error
            self.lights_cache = {}
            
    def stop(self):
        """Stop the thread"""
        self.running = False


class HueVoiceControl:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.bridge = None
        self.connect_to_bridge()
        
        # Create queues for thread communication
        self.audio_queue = queue.Queue()
        self.command_queue = queue.Queue()
        self.error_queue = queue.Queue()
        
        # Create and start threads
        self.mic_thread = None
        self.recognizer_thread = None
        self.processor_thread = None
        
    def connect_to_bridge(self):
        """Connect to the Philips Hue Bridge"""
        try:
            # If we already have a config file with username, use it
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    username = config.get('username')
                    if username:
                        self.bridge = Bridge(BRIDGE_IP, username=username)
                        logger.info("Connected to Hue Bridge using saved credentials")
                        return
            
            # Otherwise, connect and save new credentials
            if not BRIDGE_IP:
                logger.error("No Bridge IP provided. Set HUE_BRIDGE_IP in .env file")
                return
                
            logger.info(f"Connecting to Hue Bridge at {BRIDGE_IP}")
            logger.info("Press the link button on the Hue Bridge now...")
            
            # Wait for the user to press the link button
            time.sleep(5)
            
            self.bridge = Bridge(BRIDGE_IP)
            self.bridge.connect()
            
            # Save the username for future use
            with open(CONFIG_FILE, 'w') as f:
                json.dump({'username': self.bridge.username}, f)
                
            logger.info("Successfully connected to Hue Bridge")
            
        except Exception as e:
            logger.error(f"Error connecting to Hue Bridge: {str(e)}")
            raise
    
    def start(self):
        """Start all the worker threads"""
        if not self.bridge:
            logger.error("Cannot start - Bridge not connected")
            return False
        
        try:
            # Create and start the microphone thread
            self.mic_thread = ThreadedMicrophone(
                self.recognizer, 
                self.audio_queue,
                self.error_queue
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
                self.bridge,
                self.command_queue,
                self.error_queue
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
        if self.mic_thread and self.mic_thread.is_alive():
            self.mic_thread.stop()
            
        if self.recognizer_thread and self.recognizer_thread.is_alive():
            self.recognizer_thread.stop()
            
        if self.processor_thread and self.processor_thread.is_alive():
            self.processor_thread.stop()
        
        logger.info("All threads stopped")
    
    def run(self):
        """Main run method"""
        logger.info("Starting Hue Voice Control")
        logger.info(f"Wake word: '{WAKE_WORD}' (say this before every command)")
        
        if not self.start():
            return
            
        # Main thread just monitors for errors and keeps the program running
        try:
            while True:
                # Check for errors from threads
                if not self.error_queue.empty():
                    error = self.error_queue.get(block=False)
                    logger.error(f"Error from thread: {str(error)}")
                
                # Check if threads are still running
                if (not self.mic_thread.is_alive() or 
                    not self.recognizer_thread.is_alive() or 
                    not self.processor_thread.is_alive()):
                    logger.error("One or more threads have stopped unexpectedly")
                    # Attempt to restart
                    self.stop()
                    if not self.start():
                        break
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()


def main():
    try:
        controller = HueVoiceControl()
        controller.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received in main thread")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")


if __name__ == "__main__":
    main() 