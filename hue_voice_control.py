#!/usr/bin/env python3
import os
import time
import json
import speech_recognition as sr
from phue import Bridge
from dotenv import load_dotenv
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Bridge configuration
BRIDGE_IP = os.getenv("HUE_BRIDGE_IP")
CONFIG_FILE = "bridge_config.json"

class HueVoiceControl:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.bridge = None
        self.connect_to_bridge()
        
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
    
    def listen(self):
        """Listen for voice commands"""
        with sr.Microphone() as source:
            logger.info("Calibrating for ambient noise... Please wait")
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
            logger.info("Listening for commands...")
            
            while True:
                try:
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=5)
                    logger.info("Processing speech...")
                    
                    text = self.recognizer.recognize_google(audio).lower()
                    logger.info(f"Recognized: {text}")
                    
                    self.process_command(text)
                    
                except sr.WaitTimeoutError:
                    pass
                except sr.UnknownValueError:
                    logger.info("Could not understand audio")
                except sr.RequestError as e:
                    logger.error(f"Error with speech recognition service: {str(e)}")
                except Exception as e:
                    logger.error(f"Unexpected error: {str(e)}")
                    
                time.sleep(0.5)
    
    def get_specific_lights(self, command, all_lights):
        """Get living room lights since those are the only ones available"""
        # Find all living room lights
        living_room_lights = [light for name, light in all_lights.items() 
                             if 'living' in name.lower() or 'room' in name.lower()]
        
        if not living_room_lights:
            # If no living room lights found, use all lights
            logger.info("No living room lights found, using all available lights")
            return list(all_lights.values())
        
        logger.info(f"Using living room lights ({len(living_room_lights)} found)")
        return living_room_lights
    
    def process_command(self, command):
        """Process voice commands and control the lights"""
        if not self.bridge:
            logger.error("Bridge not connected")
            return
            
        # Get all lights
        try:
            lights = self.bridge.get_light_objects('name')
            targeted_lights = self.get_specific_lights(command, lights)
            
            logger.info(f"Found {len(targeted_lights)} living room lights to control")
            
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
                    
            elif "blue" in command:
                logger.info("Setting lights to blue")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.1691, 0.0441]
                    
            elif "red" in command:
                logger.info("Setting lights to red")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.6750, 0.3224]
                    
            elif "green" in command:
                logger.info("Setting lights to green")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.4091, 0.5180]
                    
            elif "yellow" in command:
                logger.info("Setting lights to yellow")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.5, 0.5]
                
            elif "purple" in command or "violet" in command:
                logger.info("Setting lights to purple")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.3, 0.1]
                    
            elif "pink" in command:
                logger.info("Setting lights to pink")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.45, 0.2]
                    
            elif "orange" in command:
                logger.info("Setting lights to orange")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.6, 0.4]
                    
            elif any(phrase in command for phrase in ["white", "normal", "neutral", "reset color"]):
                logger.info("Setting lights to white")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.3227, 0.3290]
                    
            elif "warm" in command:
                logger.info("Setting lights to warm white")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.4, 0.4]
                    light.brightness = 200
                    
            elif "cool" in command or "cold" in command:
                logger.info("Setting lights to cool white")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.3, 0.3]
                    light.brightness = 200
                    
            elif "reading" in command or "read" in command:
                logger.info("Setting lights to reading mode")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.35, 0.35]
                    light.brightness = 240
                    
            elif "movie" in command or "film" in command or "cinema" in command:
                logger.info("Setting lights to movie mode")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.5, 0.4]
                    light.brightness = 40
                    
            elif "romantic" in command or "romance" in command:
                logger.info("Setting lights to romantic mode")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.5, 0.2]
                    light.brightness = 50
                    
            elif "relax" in command or "chill" in command:
                logger.info("Setting lights to relaxed mode")
                for light in targeted_lights:
                    light.on = True
                    light.xy = [0.4, 0.4]
                    light.brightness = 100
                
            else:
                logger.info(f"Command '{command}' not recognized")
                
        except Exception as e:
            logger.error(f"Error processing command: {str(e)}")

def main():
    try:
        controller = HueVoiceControl()
        controller.listen()
    except KeyboardInterrupt:
        logger.info("Stopping Hue Voice Control")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")

if __name__ == "__main__":
    main() 