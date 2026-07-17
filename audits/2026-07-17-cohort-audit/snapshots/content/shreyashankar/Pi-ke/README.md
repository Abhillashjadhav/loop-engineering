#Final Project: Pi-ke

Project description: a bike system complete with indicator buttons, indicator lights, deceleration light, display for speed, distance traveled, and time

Project features:

- A left indicator button and right indicator button that flashes the left indicator light or right indicator light when the respective button is pressed
- A display that shows current speed, distance traveled, or time where the display can be switched by the press of a button
- A brake light that lights up when the bike is decelerating
- The ability to automatically stop flashing the corresponding indicator light when a turn has been made

Hardware used:

- Display, provided in class
- Raspberry pi, provided in class
- Jumpers and wire, provided in class
- Buttons, provided in class
- Hall sensor and magnet, provided in class
- Accelerometer/gyroscope/compass, provided in class but only gyroscope is used
- LEDs for indicators and brake lights, bought on Amazon
- 12 volt batteries for the LEDs, bought on Amazon
- Rechargeable battery for the pi, bought on Amazon

Code referenced:
- Dawson's code for accelerometer/gyroscope and hall sensor
- Code for gyroscope with Arduino from https://github.com/pololu/lsm6-arduino, namely the LSM6.cpp file to determine what we should cast our x, y, and z values to (short)

Work performed by team (this is not comprehensive but sufficient):

Everyone worked on majority of the project. Specific tasks performed by people were: Shryea and Ashwin set up the indicator interrupts, Shreya worked on getting the armtimer, hall sensor, and accelerometer to work, Shreya and Ashwin and Guy worked on setting up different parts of the hardware, Ashwin worked on mounting the hardware to the bike and debouncing the buttons, Guy worked on fine tuning the gyroscope code to determine what a complete turn is, Ashwin and Guy worked on decomposing/cleaning up the code, Ashwin and Guy worked on setting up the display, Ashwin and Guy worked on the final parts of the project, including the bootloader and hooking up the Pi to the rechargeable battery, everyone worked on testing everything together -- basically, everyone put in a lot of work

