#######################
#      LIBRARIES      #
#######################

import os, urlparse
import time
import RPi.GPIO as GPIO # for the GPIO pins
import paho.mqtt.client as paho #get the broker - mosquitto
  

######################
#     FUNCTIONS      #
######################

# Define event callbacks
def on_connect(mosq, obj, rc):
    print("rc: " + str(rc))
	
def on_message(mosq, obj, msg): # here, we're reading the message we published
	print(msg.topic + " " + str(msg.qos) + " " + str(msg.payload))
	mymessage = msg.payload ## here we get the message
	mytopic = msg.topic	## here we store the topic of the message
	if(mytopic == 'Over'): # end the program and clean the GPIO pins
		STATE[3] = 1
	if(mytopic == 'SOS'): # turn on or of the light
		if(mymessage == '1'):
			GPIO.output(PIN[1],True)
		if(mymessage == '0'):
			GPIO.output(PIN[1], False)
	if (mytopic == 'Sense'): # exit the mqtt loop and beging using sensors
		STATE[4] = 0
		

def on_publish(mosq, obj, mid):
    print("mid: " + str(mid))

def on_subscribe(mosq, obj, mid, granted_qos):
    print("Subscribed: " + str(mid) + " " + str(granted_qos))
	
# read SPI data from MCP3008 chip, 8 possible adc's (0 thru 7)
def readadc(adcnum, clockpin, mosipin, misopin, cspin):
        if ((adcnum > 7) or (adcnum < 0)):
                return -1
        GPIO.output(cspin, True)
        GPIO.output(clockpin, False) # start clock low
        GPIO.output(cspin, False) # bring CS low
        commandout = adcnum
        commandout |= 0x18 # start bit + single-ended bit
        commandout <<= 3 # we only need to send 5 bits here
        for i in range(5):
               if (commandout & 0x80):
                       GPIO.output(mosipin, True)
               else:
                       GPIO.output(mosipin, False)
               commandout <<= 1
               GPIO.output(clockpin, True)
               GPIO.output(clockpin, False)
        adcout = 0
        # read in one empty bit, one null bit and 10 ADC bits
        for i in range(12):
                GPIO.output(clockpin, True)
                GPIO.output(clockpin, False)
                adcout <<= 1
                if (GPIO.input(misopin)):
                        adcout |= 0x1
        GPIO.output(cspin, True)
        adcout >>= 1 # first bit is 'null' so drop it
        return adcout

		
#########################
#     CONFIGURATIONS    #
######################### 	
	
# configure the breakout board
GPIO.setmode(GPIO.BCM)

## let's define the pin numbers and the state variables for the sensors 
PIN = [16,12,18,23,24,25,20] # added SPI interface pins
STATE = [0, 0, 0, 0, 0] # initial states for sensors and dummy variables

##Configure the gpio pins as outputs or inputs depending on each
GPIO.setup(PIN[0], GPIO.IN) ## pin 16 will be for the PIR Motion sensor input
GPIO.setup(PIN[1], GPIO.OUT) ## pin 12 will be for the relay
GPIO.setup(PIN[2], GPIO.OUT) ## pin SPICLK
GPIO.setup(PIN[3], GPIO.IN)  ## pin SPIMISO
GPIO.setup(PIN[4], GPIO.OUT) ## pin SPIMOSI
GPIO.setup(PIN[5], GPIO.OUT) ## pin SPICS
GPIO.setup(PIN[6], GPIO.IN) ## pin 20 for the state switch

# definition of variables for sensors
motion = 0 # initialize the movement variable
light = 0 # initialize the light variable
state = 0 # dummy variable to create delays in for loops
switch = 0 # variable for the switch (mqtt/sensors back and forth)


#########################
#         MQTT          #
#########################
				
mqttc = paho.Client()

# Assign event callbacks
mqttc.on_message = on_message
mqttc.on_connect = on_connect
mqttc.on_publish = on_publish
mqttc.on_subscribe = on_subscribe

# Parse CLOUDMQTT_URL (or fallback to localhost)
url_str = os.environ.get('CLOUDMQTT_URL', 'mqtt://localhost:1883')
url = urlparse.urlparse(url_str)

# Connect
mqttc.username_pw_set('jshdkcnv', '6tjYL9p_bl6Q')
mqttc.connect('m12.cloudmqtt.com', 19289)


#########################
#      SUBSCRIBE        #
#########################

# Start subscribe, with QoS level 0
mqttc.subscribe('Movement', 0) # Topic for the motion sensor
mqttc.subscribe('Light',0) # Topic for the light sensor
mqttc.subscribe('Light_raw',0)
mqttc.subscribe('SOS',0) # topic for emergency - relay 
mqttc.subscribe('Over',0) # topic to clean pins and end program
mqttc.subscribe('Sense',0) # to start sensing again

while True:

	while (STATE[4] == 0): # while we're sensing and not checking the server

		switch = GPIO.input(PIN[6]) # we check the switch

		for i in range(0,1000): # initial delay for the sensors, not to sense immediately
			for k in range(0,2500):
				state = 1

		##########################
                #          PIR           #
                ########################## 

		motion = GPIO.input(PIN[0]) ## input 16 for the motion sensor
		if (motion == 1):
			STATE[0] = 1
		if (motion == 0):
			STATE[0] = 0 
		mqttc.publish('Movement', str(motion)) #report what it's sensing

		
		###########################
		#  READ THE LIGHT SENSOR  #
		###########################

		light = readadc(0, PIN[2], PIN[4], PIN[3], PIN[5]) #we'll be reading from channel 0
	 	mqttc.publish('Light_raw', str(light))
		if ( light < 800 ): ## we set this treshold - light sensor previously tested
			mqttc.publish('Light', '1')
			STATE[1] = 1
		if (light > 800):
			mqttc.publish('Light','0')
			STATE[1] = 0
		time.sleep(0.5)

		##########################
       	 	#      LIGHT BULB        #
        	##########################

		if (STATE[0] == 1 and STATE[1] == 0):
			GPIO.output(PIN[1],True)
			for i in range(0,5000): # create delay to leave it on for 30 seconds
				for j in range(0,15000):
					state = 1
		else:
			GPIO.output(PIN[1],False)

		if (switch == 1 and STATE[4] == 0): # if the switch was pressed -> go to MQTT
			STATE[4] = 1 # use this variable as a 'lock'
			rc = 0 
			switch = 0 #restore this to trick it into going back to the main loop
			while (rc == 0 and STATE[4] == 1): #condition for MQTT loop - if STATE[4] changes we go 
				rc = mqttc.loop() # back to the beginning -> back to sensing
				if (STATE[3] == 1): # happens when we want to end the program
					break	

		if (STATE[3] == 1):
			break
	
	if (STATE[3] == 1):
		break

GPIO.cleanup()
