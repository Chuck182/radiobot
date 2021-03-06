# External imports
import sys
import json
import serial
import RPi.GPIO as GPIO
import time
import signal
from netifaces import AF_INET, AF_INET6, AF_LINK, AF_PACKET, AF_BRIDGE
import netifaces as ni
import subprocess

# Internal modules
from displayManager import DisplayManager
from configLoader import ConfigLoader
from configLoader import ConfigurationFileException
from radioManager import RadioManager
from playerManager import PlayerManager
from radio import Radio

##############################
### GLOBAL VARS
##############################

# Modules
displayManager = None
configLoader = None
radioManager = None
playerManager = None
ip_timer = 0

##############################
### STARTUP FUNCTIONS
##############################

# Raspberry pi GPIO initialization
def configure_GPIO():
    """
        Initialize the used GPIO pins and set listeners for these pins.
        Those GPIO pins are used to connect buttons 
        (volume up/down and radio previous/next)
    """
    GPIO.setmode(GPIO.BCM) # we are using gpio BCM notation
    GPIO.setup(27, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) # Set this gpio pin as input, with a pull-down resistor
    GPIO.setup(23, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(24, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(25, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.add_event_detect(27, GPIO.RISING, callback=volume_up_callback, bouncetime=200) # Adding listener on PIN state change, triggered by falling signal  and 200 ms of pause to prevent bouncing effects)
    GPIO.add_event_detect(23, GPIO.RISING, callback=volume_down_callback, bouncetime=200)
    GPIO.add_event_detect(24, GPIO.RISING, callback=next_radio_callback, bouncetime=200)
    GPIO.add_event_detect(25, GPIO.RISING, callback=previous_radio_callback, bouncetime=200)

def set_as_ready():
    GPIO.setup(4, GPIO.OUT)
    GPIO.output(4, GPIO.LOW)
    time.sleep(0.5)
    GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(4, GPIO.FALLING, callback=halt_callback, bouncetime=200)


# Global initialisation method
def init_radiobot(config_file):
    """
        Initialize the different radiobot components :
        - Configuration loader, which will parse the json conf file and check
          attributes conformity
        - Display Manager, which is in charge of controling the LCD screen 
          and all the display behaviors (timers and so on)
        - Player manager, which is in charge of controlling VLC and Alsa 
          (starting and stoping network streams, applying volume modifications)
        - Radio manager, which is the overall manager, in charge of radio 
          selection and communication between the display and the player. 
    """
    global displayManager,configLoader,radioManager,playerManager
    
    # Loading GPIO configuration
    configure_GPIO()

    try: # Trying to load configuration file
        configLoader = ConfigLoader(config_file)
        configLoader.parse_config_file()
        print ("Configuration file loaded successfully")
    except Exception as e:
        print ("Invalid configuration : " + str(e))
        print ("Exciting.")
        sys.exit(2)

    # Loading display manager
    displayManager = DisplayManager(serial.Serial(configLoader.serial_device,configLoader.serial_baud_rate,timeout=1), configLoader.name, configLoader.halt_message, configLoader.volume_timer, configLoader.scroll_time_interval, configLoader.scroll_time_pause)
    displayManager.start()

    # Loading player
    playerManager = PlayerManager(configLoader.volume)

    # Loading the radio manager
    radioManager = RadioManager(configLoader.radios, configLoader.volume, configLoader.volume_step, configLoader.radio_info_check_interval, configLoader.full_radio_name_pause, configLoader.radio_indice, playerManager, displayManager)
    
    # Declare radiobot "ready"
    set_as_ready()
    
    # Starting first radio
    radioManager.play_radio()


##############################
### CALLBACK FUNCTIONS
##############################

def volume_up_callback(channel):
    """"
        Callback function, called when the volume UP button is pressed
        If a user press down then up immediatly, it display ip address
    """
    if time.time()-ip_timer < 0.4:
        try:
            ip = ni.ifaddresses('wlan0')[AF_INET][0]['addr']
            print ("IP address : "+str(ip))
            displayManager.on_thread(displayManager.display_ip_address, str(ip))
        except:
            pass # Do not generate error for this
    else:
        radioManager.volume_up()

def volume_down_callback(channel):
    global ip_timer
    """"
        Callback function, called when the volume DOWN button is pressed
    """
    ip_timer = time.time()
    radioManager.volume_down()

def next_radio_callback(channel):
    """"
        Callback function, called when the radio NEXT button is pressed
    """
    radioManager.next()

def previous_radio_callback(channel):
    """"
        Callback function, called when the radio PREVIOUS button is pressed
    """
    radioManager.previous()

def halt_callback(channel):
    """"
        Callback function, called when the halt button is pressed
    """
    print ("Shutdown requested !")
    clean_exit_and_shutdown()


##############################
### MAIN FUNCTION
##############################

def clean_exit_and_shutdown():
    """
        This function closes the program in a proper way and shutdown the rpi.
        It stop GPIO and LCD and saves volume and radio settings.
    """
    print()
    print("Cleaning GPIO")
    GPIO.cleanup()
    print("Cleaning LCD")
    displayManager.on_thread(displayManager.terminate)
    # Saving settings
    print("Saving current settings to cache")
    configLoader.save_settings(radioManager.get_current_volume(), radioManager.get_current_radio_indice())
    print("Exiting.")
    subprocess.call(['sudo', 'shutdown', '-h', 'now'], shell=False)
    sys.exit(0)

def clean_exit():
    """
        This function closes the program in a proper way.
        It stop GPIO and LCD and saves volume and radio settings.
    """
    print()
    print("Cleaning GPIO")
    GPIO.cleanup()
    print("Cleaning LCD")
    displayManager.on_thread(displayManager.terminate)
    # Saving settings
    print("Saving current settings to cache")
    configLoader.save_settings(radioManager.get_current_volume(), radioManager.get_current_radio_indice())
    print("Exiting.")
    sys.exit(0)

def sigterm_callback(signal, frame):
    """
        Callback function, called when SIGTERM is triggered
    """
    clean_exit()


def main(config_file):
    """
        Main method called on program startup. 
        Takes the config file path (program arguement)
        This method run the init function and then 
        loop on refresh methods until program termination.
    """
    print("Radiobot (v1.0)")
    print("Written by Chuck182")
    print()

    # Setting signal listener (SIGTERM)
    signal.signal(signal.SIGTERM, sigterm_callback)

    # Initializing radiobot 
    init_radiobot(config_file)

    # While there are no process interruptions, loop on display update functions 
    try:
        while True:
            radioManager.check_radio_info() # Check if new radio info is available, and notify display if needed
            playerManager.update_player()
            time.sleep(0.05)
    except KeyboardInterrupt:
        clean_exit()

if __name__== "__main__":
    if len(sys.argv) <= 1:
        print ("Missing configuration file path")
        print ("Exiting.")
        sys.exit(2)
    main(sys.argv[1])
